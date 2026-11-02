#!/usr/bin/env python3
"""Generic open-source library-match tool for MCU RE passes (issue #41, reusable for any module:
m0400, m0306, m0900, m1400, ...).

Dan's rule: when a FUN_* / shape-named function looks like libm/CMSIS-DSP/libgcc soft-float, do not
just label it by shape - COMPILE (or extract from the toolchain's own prebuilt archive) the real
candidate source with the project's arm-none-eabi toolchain and diff the result against the firmware
bytes at the real address. This script does that diff, generically:

  - --ref-archive/--ref-member/--ref-symbol : pull a symbol straight out of a prebuilt .a (libgcc.a,
    libm.a, libc.a, or ARM Compiler 6's libclang_rt.builtins.a) - fastest, "the exact binary the
    vendor likely linked" when it matches. Toolchain-agnostic: GNU ar/readelf/objcopy (the
    --toolchain-prefix tools) read any of these archive formats fine.
  - --source/--ref-symbol (+ --cpu/--fpu/--float-abi/--opt-levels/--define/--include) : compile a
    candidate .c at several -O levels and diff each. Backend picked by --toolchain:
      gcc (default)    : arm-none-eabi-gcc flag syntax (-mcpu=/-mfpu=/-mfloat-abi=).
      armclang         : ARM Compiler 6 / clang flag syntax (--target=/-mcpu=/-mfpu=/-mfloat-abi=),
                          needs --armclang-bin (e.g. ST's repackaged armclang, "starm-clang") and
                          optionally --clang-target (default arm-none-eabi). Disassembly/extraction
                          of the clang-produced .o still goes through the GNU --toolchain-prefix
                          tools (readelf/objcopy/objdump) - verified compatible, see
                          docs/toolchain-inventory.md.
      armcc            : ARM Compiler 5 / Keil flag syntax (--cpu=/--apcs=/-O0.. /-Ospace/-Otime),
                          needs --armcc-bin (path to armcc.exe) and --wineprefix (the WINEPREFIX
                          armcc.exe was installed into, e.g. ~/.wine-keil) - invoked as
                          `wine <armcc-bin> ...`. UNLIKE armclang, the compiled .o does NOT go
                          through the GNU --toolchain-prefix tools: ARM Compiler 5's eval/Lite
                          license tags its default object output with a non-standard magic
                          ("\\xf7ORC" in place of "\\x7fELF" - otherwise byte-identical ELF32
                          layout) that GNU readelf/objdump refuse to parse, and the license-gated
                          `fromelf --elf` conversion that would produce a conforming ELF is NOT
                          available on the eval/Lite tier ("Option '--elf' not available with your
                          license"). Extraction instead parses `fromelf --text -c -s` output
                          directly (also via wine) - see docs/toolchain-inventory.md "ARM Compiler
                          5 object format" for the byte-reconstruction rule. --ref-archive against
                          ARM Compiler 5's OWN prebuilt runtime library (ARMCC/lib/armlib/*.l) does
                          NOT need any of this: confirmed those .l archives and the standard-ELF
                          .o members inside them (unlike a locally-compiled .o) are byte-identical
                          and directly readable by the existing GNU ar/readelf/objcopy tools - no
                          --toolchain armcc needed there, just point --ref-archive at the .l file.

Always logs to ./tmp/logs/mcu_libmatch.log. Never executes the firmware or the compiled reference -
static byte/instruction comparison only.

Usage (prebuilt archive, e.g. newlib sqrtf against m0400 Cortex-M4F):
  python3 scripts/re/mcu_libmatch.py --image firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin \\
    --base 0x08008000 --addr 0x080133d8 --size 58 \\
    --ref-archive /usr/arm-none-eabi/lib/thumb/v7e-m+fp/hard/libm.a \\
    --ref-member libm_a-wf_sqrt.o --ref-symbol sqrtf

Usage (compile CMSIS-DSP source, Cortex-M4F, GCC backend):
  python3 scripts/re/mcu_libmatch.py --image firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin \\
    --base 0x08008000 --addr 0x08008360 --size 836 \\
    --source /path/to/cmsis-dsp/Source/TransformFunctions/arm_cfft_radix4_f32.c \\
    --ref-symbol arm_radix4_butterfly_f32 \\
    --include /path/to/cmsis-dsp/Include --include /path/to/CMSIS/Include \\
    --cpu cortex-m4 --fpu fpv4-sp-d16 --float-abi hard --define ARM_MATH_CM4 --define __FPU_PRESENT=1

Usage (same, armclang backend - see docs/toolchain-inventory.md for the --armclang-bin path):
  python3 scripts/re/mcu_libmatch.py --image firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin \\
    --base 0x08008000 --addr 0x08008360 --size 836 \\
    --source /path/to/cmsis-dsp/.../arm_cfft_radix4_f32.c --ref-symbol arm_radix4_butterfly_f32 \\
    --include /path/to/cmsis-dsp/Include --include /path/to/CMSIS/Include \\
    --toolchain armclang --armclang-bin ~/.local/share/stm32cube/bundles/st-arm-clang/21.1.1+st.7/bin/starm-clang \\
    --cpu cortex-m4 --fpu fpv4-sp-d16 --float-abi hard --define ARM_MATH_CM4 --define __FPU_PRESENT=1

For a no-HW-FPU module (m0900/m1400, Cortex-M3): --cpu cortex-m3 --fpu none --float-abi soft (or omit
--fpu/--float-abi entirely - soft is the default when --fpu is not given).
"""
from __future__ import annotations

import argparse
import difflib
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402

TOOLCHAIN_PREFIX_DEFAULT = "arm-none-eabi-"


def tool(prefix: str, name: str) -> str:
    return prefix + name


def run(cmd: list[str], **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def read_fw_bytes(image: Path, base: int, addr: int, size: int) -> bytes:
    data = image.read_bytes()
    off = addr - base
    if not (0 <= off < len(data) - size):
        raise SystemExit(f"addr 0x{addr:x} size {size} outside image (base 0x{base:x}, image {len(data)} B)")
    return data[off:off + size]


def objdump_raw_thumb(prefix: str, raw: bytes, vma: int) -> list[str]:
    """Disassemble a raw Thumb byte blob (no ELF container) and return mnemonic+operand lines."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        cmd = [tool(prefix, "objdump"), "-D", "-b", "binary", "-m", "arm", "-Mforce-thumb",
               f"--adjust-vma={vma:#x}", path]
        cp = run(cmd)
        return parse_objdump_insns(cp.stdout)
    finally:
        Path(path).unlink(missing_ok=True)


_INSN_LINE = __import__("re").compile(r"^\s*([0-9a-f]+):\s*((?:[0-9a-f]{2,4}\s*)+)\t(.*)$")


def parse_objdump_insns(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        m = _INSN_LINE.match(line)
        if not m:
            continue
        insn = m.group(3).strip()
        if insn and not insn.startswith(("...", ".word", ".short", ".byte")):
            out.append(insn)
    return out


# FLIRT-style fuzzy mode (issue #41 pt 2 follow-up): for functions that fail exact byte-diff
# (structurally different compiler, not just a different load address/opt level - e.g. m0400's
# __aeabi_f2d, 38 B firmware vs 116 B LLVM compiler-rt). Real IDA FLIRT signatures only wildcard
# relocation-patched bytes and otherwise require an exact byte/CRC match - useless here, since the
# divergence is structural (different register allocation, different algorithm), not relocation
# noise. This mode keeps FLIRT's idea (pattern + masked variable bytes + call-graph shape) but
# replaces FLIRT's strict CRC-of-remaining-bytes with three tolerant signals: masked-byte-identity
# ratio, order-insensitive mnemonic histogram overlap, and call-fanout shape. python-flirt (the
# IDA .sig/.pat library, installed under /usr/bin/python3 only) was evaluated and not used: it
# would reduce to the same byte+wildcard comparison already proven negative in
# docs/toolchain-inventory.md, with no histogram/call-graph tolerance of its own to add.
_ADDR_DEP_RE = __import__("re").compile(
    r"^(bl|blx|b|b\.w|bne|beq|bgt|blt|bge|ble|bhi|bls|bcs|bcc|bmi|bpl|bvs|bvc|cbz|cbnz|"
    r"adr|adr\.w|movw|movt)(\.n|\.w)?$"
)


def _is_addr_dependent(mnemonic: str, operand: str) -> bool:
    """True if this instruction's operand bytes encode a call target, branch target, pc-relative
    literal address, or absolute movw/movt immediate - i.e. a value that depends on load address
    or register allocation, not on the algorithm. Masked out before any fuzzy byte comparison."""
    if _ADDR_DEP_RE.match(mnemonic):
        return True
    return mnemonic.startswith("ldr") and "[pc" in operand


_DETAIL_LINE = __import__("re").compile(r"^\s*([0-9a-f]+):\s*((?:[0-9a-f]{2,4}\s*)+)\t(\S+)\s*(.*)$")


def disassemble_detailed(prefix: str, raw: bytes, vma: int) -> dict:
    """Disassemble raw Thumb bytes; return masked-byte copy (address-dependent operands zeroed),
    the mnemonic+operand instruction list, and a call-fanout count (bl/blx sites) for the
    FLIRT-style fuzzy comparison. vma must match the byte buffer's real load address so `addr -
    vma` gives a correct offset into `raw` (same convention as objdump_raw_thumb)."""
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(raw)
        path = f.name
    try:
        cmd = [tool(prefix, "objdump"), "-D", "-b", "binary", "-m", "arm", "-Mforce-thumb",
               f"--adjust-vma={vma:#x}", path]
        cp = run(cmd)
    finally:
        Path(path).unlink(missing_ok=True)
    masked = bytearray(raw)
    insns: list[str] = []
    calls = 0
    for line in cp.stdout.splitlines():
        m = _DETAIL_LINE.match(line)
        if not m:
            continue
        addr_s, hexbytes, mnemonic, operand = m.groups()
        if mnemonic.startswith((".word", ".short", ".byte", "...")):
            continue
        insns.append(f"{mnemonic} {operand}".strip())
        if mnemonic in ("bl", "blx"):
            calls += 1
        if _is_addr_dependent(mnemonic, operand):
            addr = int(addr_s, 16)
            off = addr - vma
            width = len(hexbytes.split()) if " " in hexbytes.strip() else len(hexbytes.strip()) // 2
            if 0 <= off < len(masked):
                for i in range(off, min(off + width, len(masked))):
                    masked[i] = 0
    return {"masked": bytes(masked), "insns": insns, "calls": calls, "len": len(raw)}


def fuzzy_compare(fw: dict, ref: dict) -> dict:
    """Composite FLIRT-style fuzzy score: masked-byte identity (tolerates relocation/address
    differences), order-insensitive mnemonic histogram overlap (tolerates register-allocation/
    instruction-scheduling differences a strict insn_ratio rejects), and call-fanout shape
    (tolerates everything except how many things the function calls)."""
    n = min(fw["len"], ref["len"])
    masked_pct = 100.0 * sum(1 for i in range(n) if fw["masked"][i] == ref["masked"][i]) / n if n else 0.0
    fw_mn, ref_mn = Counter(mnemonics(fw["insns"])), Counter(mnemonics(ref["insns"]))
    overlap = sum((fw_mn & ref_mn).values())
    denom = max(sum(fw_mn.values()), sum(ref_mn.values()), 1)
    histogram_pct = 100.0 * overlap / denom
    hi, lo = max(fw["calls"], ref["calls"]), min(fw["calls"], ref["calls"])
    call_shape_pct = 100.0 if hi == 0 else 100.0 * lo / hi
    size_ratio = min(fw["len"], ref["len"]) / max(fw["len"], ref["len"], 1)
    composite = 0.40 * masked_pct + 0.35 * histogram_pct + 0.25 * call_shape_pct
    return {
        "masked_byte_pct": masked_pct, "histogram_pct": histogram_pct,
        "call_shape_pct": call_shape_pct, "size_ratio_pct": 100.0 * size_ratio,
        "composite_pct": composite, "fw_calls": fw["calls"], "ref_calls": ref["calls"],
        "fw_len": fw["len"], "ref_len": ref["len"],
    }


def fuzzy_verdict(res: dict) -> str:
    # Threshold calibrated conservatively: this is a ranking aid for a human RE pass, not a prover.
    # Composite >=70% AND size within 2x each way is the floor for "worth a human look" - below
    # that, the shape itself carries no signal (confirmed by this mode's own negative runs).
    if res["composite_pct"] >= 70.0 and res["size_ratio_pct"] >= 50.0:
        return f"I (fuzzy match, composite={res['composite_pct']:.1f}%) - inferred only, re-rules.md pt 7/10: V needs an exact byte-diff"
    return f"U (no fuzzy match, composite={res['composite_pct']:.1f}%)"


def extract_from_archive(prefix: str, archive: Path, member: str, symbol: str) -> tuple[bytes, int]:
    """ar p the member, locate `symbol`'s section + address + size, extract its raw bytes."""
    with tempfile.TemporaryDirectory() as td:
        obj = Path(td) / "member.o"
        cp = subprocess.run([tool(prefix, "ar"), "p", str(archive), member], capture_output=True)
        if cp.returncode != 0 or not cp.stdout:
            raise SystemExit(f"ar p {archive} {member} failed: {cp.stderr!r}")
        obj.write_bytes(cp.stdout)
        return extract_symbol_bytes(prefix, obj, symbol)


def extract_symbol_bytes(prefix: str, obj: Path, symbol: str) -> tuple[bytes, int]:
    """Read ELF symbol table for `symbol`, pull its bytes out of its section. Returns (bytes, size)."""
    cp = run([tool(prefix, "readelf"), "-sW", str(obj)])
    sym_val = sym_size = sym_ndx = None
    for line in cp.stdout.splitlines():
        cols = line.split()
        if len(cols) >= 8 and cols[-1] == symbol and "FUNC" in cols:
            sym_val = int(cols[1], 16)
            sym_size = int(cols[2])
            sym_ndx = cols[6]
            break
    if sym_val is None:
        raise SystemExit(f"symbol {symbol!r} not found (FUNC) in {obj}")
    if sym_size == 0:
        raise SystemExit(f"symbol {symbol!r} has size 0 in {obj} - can't slice its bytes")
    # map section index -> name
    cp2 = run([tool(prefix, "readelf"), "-SW", str(obj)])
    sec_name = None
    for line in cp2.stdout.splitlines():
        cols = line.replace("[", " ").replace("]", " ").split()
        if cols and cols[0] == sym_ndx:
            sec_name = cols[1]
            break
    if sec_name is None:
        raise SystemExit(f"could not resolve section index {sym_ndx} for {symbol} in {obj}")
    with tempfile.TemporaryDirectory() as td:
        raw = Path(td) / "sec.bin"
        cp3 = run([tool(prefix, "objcopy"), "-O", "binary", f"--only-section={sec_name}", str(obj), str(raw)])
        if cp3.returncode != 0:
            raise SystemExit(f"objcopy failed: {cp3.stderr}")
        data = raw.read_bytes()
    base_val = sym_val & ~1  # clear Thumb bit
    if base_val + sym_size > len(data):
        raise SystemExit(f"symbol range outside section {sec_name} ({len(data)} B) for {symbol}")
    return data[base_val:base_val + sym_size], sym_size


def compile_source(prefix: str, source: Path, opt: str, cpu: str, fpu: str | None, float_abi: str,
                    defines: list[str], includes: list[str], extra: list[str]) -> Path:
    """gcc-style flag dialect: -mcpu=/-mfpu=/-mfloat-abi=, triple implied by the prefixed binary name."""
    out = Path(tempfile.mkstemp(suffix=f"_{opt}.o")[1])
    cmd = [tool(prefix, "gcc"), f"-mcpu={cpu}", "-mthumb", f"-mfloat-abi={float_abi}"]
    if fpu and fpu != "none":
        cmd.append(f"-mfpu={fpu}")
    cmd += [f"-{opt}", "-c", str(source), "-o", str(out)]
    for d in defines:
        cmd.append(f"-D{d}")
    for i in includes:
        cmd += ["-I", i]
    cmd += extra
    cp = run(cmd)
    if cp.returncode != 0:
        out.unlink(missing_ok=True)
        raise SystemExit(f"compile failed ({' '.join(cmd)}):\n{cp.stderr}")
    return out


def compile_source_armclang(clang_bin: str, target: str, source: Path, opt: str, cpu: str,
                             fpu: str | None, float_abi: str, defines: list[str], includes: list[str],
                             extra: list[str]) -> Path:
    """armclang/clang-style flag dialect: --target=/-mcpu=/-mfpu=/-mfloat-abi=.

    `-Wno-missing-multilib` silences the "no multilib found" warning: we only compile (-c), never
    link, so the clang-runtimes multilib variant doesn't matter here - confirmed on ST's armclang
    21.1.1 repackaging (docs/toolchain-inventory.md).
    """
    out = Path(tempfile.mkstemp(suffix=f"_{opt}.o")[1])
    cmd = [clang_bin, f"--target={target}", f"-mcpu={cpu}", f"-mfloat-abi={float_abi}",
           "-Wno-missing-multilib"]
    if fpu and fpu != "none":
        cmd.append(f"-mfpu={fpu}")
    cmd += [f"-{opt}", "-c", str(source), "-o", str(out)]
    for d in defines:
        cmd.append(f"-D{d}")
    for i in includes:
        cmd += ["-I", i]
    cmd += extra
    cp = run(cmd)
    if cp.returncode != 0:
        out.unlink(missing_ok=True)
        raise SystemExit(f"armclang compile failed ({' '.join(cmd)}):\n{cp.stderr}")
    return out


def _wine_path(p: Path) -> str:
    """Host path -> wine path, via wine's default Z: = / mapping (no custom drive config needed)."""
    return "Z:" + str(p.resolve())


def compile_source_armcc(armcc_bin: str, wineprefix: str, source: Path, opt: str, cpu: str,
                          float_abi: str, defines: list[str], includes: list[str],
                          extra: list[str]) -> Path:
    """ARM Compiler 5 (Keil armcc) flag dialect: --cpu=/--apcs=/-O0../-Ospace/-Otime, -D/-I (gcc-
    compatible, no space needed). `--apcs=/hardfp` or `/softfp` for float_abi in (hard, softfp);
    soft (no FPU, e.g. Cortex-M3) omits --apcs entirely - armcc's default for an FPU-less --cpu is
    already soft. Runs via `wine <armcc_bin> ...` with WINEPREFIX set to `wineprefix` (see
    docs/toolchain-inventory.md for the install path, e.g. ~/.wine-keil).

    Output is ARM Compiler 5's own object format: ELF-shaped (same Elf32_Ehdr field layout and
    offsets) but with the magic bytes swapped from "\\x7fELF" to "\\xf7ORC" on the eval/Lite license
    tier - GNU readelf/objdump refuse it. extract_symbol_bytes_fromelf_text() reads it back via
    `fromelf --text -c -s` instead (also through wine), not the GNU --toolchain-prefix tools.
    """
    out = Path(tempfile.mkstemp(suffix=f"_{opt}.o")[1])
    cmd = ["wine", armcc_bin, f"--cpu={cpu}"]
    if float_abi in ("hard", "hardfp"):
        cmd.append("--apcs=/hardfp")
    elif float_abi == "softfp":
        cmd.append("--apcs=/softfp")
    cmd += [f"-{opt}", "-c", _wine_path(source), "-o", _wine_path(out)]
    for d in defines:
        cmd.append(f"-D{d}")
    for i in includes:
        cmd += ["-I", _wine_path(Path(i))]
    cmd += extra
    env = {**__import__("os").environ, "WINEPREFIX": wineprefix, "WINEDEBUG": "-all"}
    cp = run(cmd, env=env)
    if cp.returncode != 0 or not out.exists():
        out.unlink(missing_ok=True)
        raise SystemExit(f"armcc compile failed ({' '.join(cmd)}):\n{cp.stdout}\n{cp.stderr}")
    return out


# fromelf --text -c -s instruction line, e.g.:
#   "        0x00000000:    eef01a40    ..@.    VMOV.F32 s3,s0"
#   "        0x0000000c:    4770        pG      BX       lr"
# The hex field is one or more 4-hex-digit halfwords with NO separating space (unlike objdump's
# space-separated halfwords); each halfword's two bytes are swapped relative to its own display
# order to get real memory bytes (confirmed against the same source compiled with GCC: fromelf
# "eef01a40" == objdump "f0ee 401a", little-endian halfwords - see docs/toolchain-inventory.md).
_FROMELF_INSN_LINE = __import__("re").compile(
    r"^\s*0x([0-9a-fA-F]{8}):\s+([0-9a-fA-F]+)\s+.*?\s{2,}(\S.*)$"
)
_FROMELF_SECTION_LINE = __import__("re").compile(r"^\*\* Section #\d+ '([^']*)'")
# fromelf's own symbol table (`-s`), e.g.:
#   "     17  GPIO_Init                  0x000000dd   Gb    2  Code  Hi   0x90"
# Gives the real symbol size, needed because a multi-function source file compiles every function
# of the .c into ONE shared section (armcc does not do -ffunction-sections by default) - without
# the real size, scanning "until the next Section" (fine for a single-function --source file)
# silently captures however many bytes of the NEXT function(s) happen to follow in that section
# too. Caught on GPIO_Init (#41 pt3 addendum, 2026-11-03): capturing to end-of-section inflated
# ref_len from the true 144 B to 384 B (GPIO_Init + the start of GPIO_StructInit etc), which
# diluted insn_ratio/mnemonic_ratio enough to read as U even though the real 144 B were byte-
# exact. Always anchor on the symbol table's own Size column, never section boundaries.
_FROMELF_SYM_ROW = __import__("re").compile(
    r"^\s*\d+\s+(\S+)\s+0x([0-9a-fA-F]+)\s+\S+\s+\S+\s+\S+\s+\S+\s+0x([0-9a-fA-F]+)\s*$"
)


def _fromelf_symbol_size(stdout: str, symbol: str) -> int:
    """Look up `symbol`'s Size column in fromelf's own symbol table listing (requires -s)."""
    for line in stdout.splitlines():
        m = _FROMELF_SYM_ROW.match(line)
        if m and m.group(1) == symbol:
            return int(m.group(3), 16)
    raise SystemExit(f"symbol {symbol!r} not found (with a size) in fromelf -s symbol table\n"
                      f"(stdout follows)\n{stdout}")


def _fromelf_halfwords_to_bytes(hexstr: str) -> bytes:
    out = bytearray()
    for i in range(0, len(hexstr), 4):
        chunk = hexstr[i:i + 4]
        if len(chunk) < 4:
            break
        out += bytes.fromhex(chunk[2:4] + chunk[0:2])
    return bytes(out)


def extract_symbol_bytes_fromelf_text(fromelf_bin: str, wineprefix: str, obj: Path,
                                       symbol: str) -> tuple[bytes, int]:
    """Parse `fromelf --text -c -s <obj>` (via wine) to reconstruct a symbol's raw bytes + insn
    list, for ARM Compiler 5 objects GNU readelf/objdump can't read (see compile_source_armcc).
    Looks up the real size from fromelf's own symbol table first (see _fromelf_symbol_size - a
    multi-function source file packs every function of the .c into one shared section, so the
    disassembly alone can't tell where `symbol` ends), then reads exactly that many bytes
    starting at the `symbol` label line in the disassembly.
    """
    env = {**__import__("os").environ, "WINEPREFIX": wineprefix, "WINEDEBUG": "-all"}
    cp = run(["wine", fromelf_bin, "--text", "-c", "-s", _wine_path(obj)], env=env)
    size = _fromelf_symbol_size(cp.stdout, symbol)
    lines = cp.stdout.splitlines()
    in_target = False
    found_symbol = False
    raw = bytearray()
    insns: list[str] = []
    for line in lines:
        if _FROMELF_SECTION_LINE.match(line.strip()):
            if found_symbol:
                break
            in_target = False
            continue
        stripped = line.strip()
        if stripped == symbol:
            found_symbol = True
            in_target = True
            continue
        if not in_target:
            continue
        if len(raw) >= size:
            break  # reached the known symbol size: stop before the next function's instructions
        m = _FROMELF_INSN_LINE.match(line)
        if m:
            _addr, hexstr, rest = m.groups()
            raw += _fromelf_halfwords_to_bytes(hexstr)
            insns.append(rest.strip())
    if not found_symbol:
        raise SystemExit(f"symbol {symbol!r} not found in fromelf --text output of {obj}\n"
                          f"(stdout follows)\n{cp.stdout}")
    return bytes(raw[:size]), min(len(raw), size)


def mnemonics(insns: list[str]) -> list[str]:
    """First whitespace-separated token of each instruction (opcode only, no operands/registers)."""
    return [i.split()[0] if i.split() else i for i in insns]


def compare(fw: bytes, ref: bytes, fw_insns: list[str], ref_insns: list[str]) -> dict:
    byte_exact = fw == ref
    n = min(len(fw), len(ref))
    byte_prefix_match = sum(1 for i in range(n) if fw[i] == ref[i])
    sm = difflib.SequenceMatcher(a=fw_insns, b=ref_insns, autojunk=False)
    insn_ratio = sm.ratio()
    sm_mn = difflib.SequenceMatcher(a=mnemonics(fw_insns), b=mnemonics(ref_insns), autojunk=False)
    mnemonic_ratio = sm_mn.ratio()
    return {
        "fw_len": len(fw), "ref_len": len(ref),
        "byte_exact": byte_exact,
        "byte_prefix_match_pct": 100.0 * byte_prefix_match / n if n else 0.0,
        "insn_ratio_pct": 100.0 * insn_ratio,
        "mnemonic_ratio_pct": 100.0 * mnemonic_ratio,
        "fw_insn_count": len(fw_insns), "ref_insn_count": len(ref_insns),
    }


def verdict(res: dict) -> str:
    if res["byte_exact"]:
        return "V (byte-identical)"
    if res["fw_len"] == res["ref_len"] and res["insn_ratio_pct"] >= 98.0:
        return "V (instruction-identical, same size)"
    if res["insn_ratio_pct"] >= 85.0:
        return "I (same opcodes+operands, different byte encoding - do not upgrade to V)"
    if res["mnemonic_ratio_pct"] >= 70.0:
        return "I (same opcode sequence, different register allocation - do not upgrade to V)"
    return "U (no useful match - shape-only or unrelated)"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", required=True, type=Path, help="firmware .bin")
    ap.add_argument("--base", required=True, type=lambda s: int(s, 0), help="load base of the image, e.g. 0x08008000")
    ap.add_argument("--addr", required=True, type=lambda s: int(s, 0), help="function address in the firmware")
    ap.add_argument("--size", required=True, type=int, help="function size in bytes (from the Ghidra dump)")
    ap.add_argument("--toolchain-prefix", default=TOOLCHAIN_PREFIX_DEFAULT,
                     help=f"binutils/gcc prefix on PATH (default {TOOLCHAIN_PREFIX_DEFAULT})")
    ap.add_argument("--module", default="", help="module name, for the log line only (m0400, m0900, ...)")
    # archive-extraction path
    ap.add_argument("--ref-archive", type=Path, help="prebuilt .a to pull a symbol from (libgcc.a/libm.a/libc.a)")
    ap.add_argument("--ref-member", help="archive member .o containing the symbol")
    ap.add_argument("--ref-symbol", help="symbol name to extract/compile (required)")
    # compile path
    ap.add_argument("--source", type=Path, help="candidate .c to compile (CMSIS-DSP, newlib, ...)")
    ap.add_argument("--cpu", default="cortex-m4", help="e.g. cortex-m4 (M4F modules), cortex-m3 (no HW FPU)")
    ap.add_argument("--fpu", default=None, help="e.g. fpv4-sp-d16; omit or 'none' for soft-float modules")
    ap.add_argument("--float-abi", default="soft", help="hard/softfp/soft (soft for no-HW-FPU modules)")
    ap.add_argument("--opt-levels", default="O0,O1,O2,O3,Os")
    ap.add_argument("--define", action="append", default=[], dest="defines")
    ap.add_argument("--include", action="append", default=[], dest="includes")
    ap.add_argument("--cc-arg", action="append", default=[], dest="extra", help="extra compiler argument")
    ap.add_argument("--toolchain", choices=["gcc", "armclang", "armcc"], default="gcc",
                     help="compile-path backend flag dialect (--source only; --ref-archive is toolchain-"
                          "agnostic). gcc = arm-none-eabi-gcc syntax (default). armclang = ARM Compiler 6"
                          "/clang syntax, needs --armclang-bin. armcc = ARM Compiler 5/Keil syntax, needs "
                          "--armcc-bin and --wineprefix. See docs/toolchain-inventory.md (#41 pt 10).")
    ap.add_argument("--armclang-bin", help="path to the armclang/clang binary (--toolchain armclang only), "
                                            "e.g. ST's repackaged ~/.local/share/stm32cube/bundles/"
                                            "st-arm-clang/<ver>/bin/starm-clang")
    ap.add_argument("--clang-target", default="arm-none-eabi",
                     help="--target= value for --toolchain armclang (default arm-none-eabi)")
    ap.add_argument("--armcc-bin", help="path to armcc.exe (--toolchain armcc only), e.g. "
                                         "~/.wine-keil/drive_c/Keil_v5/ARM/ARMCC/bin/armcc.exe")
    ap.add_argument("--wineprefix", help="WINEPREFIX armcc.exe was installed into (--toolchain armcc "
                                          "only), e.g. ~/.wine-keil")
    ap.add_argument("--mode", choices=["exact", "fuzzy"], default="exact",
                     help="exact (default, unchanged): byte-diff + ordered insn/mnemonic ratio, V only on an "
                          "exact or instruction-identical match. fuzzy: additionally compute the FLIRT-style "
                          "composite score (masked-byte identity + mnemonic histogram + call-fanout shape) for "
                          "candidates that already failed exact - never upgrades a result past I. Use after "
                          "--mode exact has returned U for every toolchain in docs/toolchain-inventory.md.")
    args = ap.parse_args()
    if args.toolchain == "armclang" and not args.armclang_bin:
        raise SystemExit("--toolchain armclang requires --armclang-bin <path to clang binary>")
    if args.toolchain == "armcc" and not (args.armcc_bin and args.wineprefix):
        raise SystemExit("--toolchain armcc requires --armcc-bin <path to armcc.exe> and --wineprefix <prefix>")

    if not args.ref_symbol:
        raise SystemExit("--ref-symbol is required")
    if bool(args.ref_archive) == bool(args.source):
        raise SystemExit("give exactly one of --ref-archive(+--ref-member) or --source")

    fw = read_fw_bytes(args.image, args.base, args.addr, args.size)
    fw_insns = objdump_raw_thumb(args.toolchain_prefix, fw, args.addr)
    fw_detail = disassemble_detailed(args.toolchain_prefix, fw, args.addr) if args.mode == "fuzzy" else None

    tag = f"[{args.module}] " if args.module else ""
    log(f"{tag}mode={args.mode} addr=0x{args.addr:x} size={args.size} symbol={args.ref_symbol!r}")

    results = []
    if args.ref_archive:
        ref, sz = extract_from_archive(args.toolchain_prefix, args.ref_archive, args.ref_member, args.ref_symbol)
        ref_insns = objdump_raw_thumb(args.toolchain_prefix, ref, 0)
        res = compare(fw, ref, fw_insns, ref_insns)
        res["candidate"] = f"{args.ref_archive}:{args.ref_member}:{args.ref_symbol}"
        if args.mode == "fuzzy":
            ref_detail = disassemble_detailed(args.toolchain_prefix, ref, 0)
            res["fuzzy"] = fuzzy_compare(fw_detail, ref_detail)
        results.append(res)
    else:
        for opt in args.opt_levels.split(","):
            if args.toolchain == "armclang":
                obj = compile_source_armclang(args.armclang_bin, args.clang_target, args.source, opt,
                                               args.cpu, args.fpu, args.float_abi, args.defines,
                                               args.includes, args.extra)
            elif args.toolchain == "armcc":
                obj = compile_source_armcc(args.armcc_bin, args.wineprefix, args.source, opt,
                                            args.cpu, args.float_abi, args.defines, args.includes,
                                            args.extra)
            else:
                obj = compile_source(args.toolchain_prefix, args.source, opt, args.cpu, args.fpu,
                                      args.float_abi, args.defines, args.includes, args.extra)
            try:
                if args.toolchain == "armcc":
                    # ARM Compiler 5's eval-license object format isn't standard ELF (non-standard
                    # magic, --elf conversion license-gated) - parse fromelf --text output instead
                    # of GNU readelf/objcopy. See compile_source_armcc / docs/toolchain-inventory.md.
                    ref, sz = extract_symbol_bytes_fromelf_text(
                        str(Path(args.armcc_bin).with_name("fromelf.exe")), args.wineprefix, obj,
                        args.ref_symbol)
                else:
                    # readelf/objcopy/objdump stay on --toolchain-prefix (GNU binutils): confirmed
                    # compatible with armclang-produced ELF objects, docs/toolchain-inventory.md.
                    ref, sz = extract_symbol_bytes(args.toolchain_prefix, obj, args.ref_symbol)
            finally:
                obj.unlink(missing_ok=True)
            ref_insns = objdump_raw_thumb(args.toolchain_prefix, ref, 0)
            res = compare(fw, ref, fw_insns, ref_insns)
            res["candidate"] = f"[{args.toolchain}] {args.source.name}:{args.ref_symbol}@-{opt}"
            if args.mode == "fuzzy":
                ref_detail = disassemble_detailed(args.toolchain_prefix, ref, 0)
                res["fuzzy"] = fuzzy_compare(fw_detail, ref_detail)
            results.append(res)

    for res in results:
        v = verdict(res)
        log(f"{tag}{res['candidate']}: fw_len={res['fw_len']} ref_len={res['ref_len']} "
            f"byte_exact={res['byte_exact']} byte_prefix_match={res['byte_prefix_match_pct']:.1f}% "
            f"insn_ratio={res['insn_ratio_pct']:.1f}% mnemonic_ratio={res['mnemonic_ratio_pct']:.1f}% "
            f"(fw {res['fw_insn_count']} insns, ref {res['ref_insn_count']} insns) -> {v}")
        print(f"{res['candidate']}: {v} (len fw={res['fw_len']} ref={res['ref_len']}, "
              f"insn_ratio={res['insn_ratio_pct']:.1f}%, mnemonic_ratio={res['mnemonic_ratio_pct']:.1f}%)")
        if args.mode == "fuzzy":
            fz = res["fuzzy"]
            fv = fuzzy_verdict(fz)
            log(f"{tag}{res['candidate']} [fuzzy]: masked_byte={fz['masked_byte_pct']:.1f}% "
                f"histogram={fz['histogram_pct']:.1f}% call_shape={fz['call_shape_pct']:.1f}% "
                f"(fw_calls={fz['fw_calls']} ref_calls={fz['ref_calls']}) "
                f"composite={fz['composite_pct']:.1f}% -> {fv}")
            print(f"  [fuzzy] {fv} (masked_byte={fz['masked_byte_pct']:.1f}%, "
                  f"histogram={fz['histogram_pct']:.1f}%, call_shape={fz['call_shape_pct']:.1f}%, "
                  f"composite={fz['composite_pct']:.1f}%)")

    best = max(results, key=lambda r: r["insn_ratio_pct"])
    log(f"{tag}best (exact ranking): {best['candidate']} -> {verdict(best)}")
    if args.mode == "fuzzy":
        best_fz = max(results, key=lambda r: r["fuzzy"]["composite_pct"])
        log(f"{tag}best (fuzzy ranking): {best_fz['candidate']} -> {fuzzy_verdict(best_fz['fuzzy'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
