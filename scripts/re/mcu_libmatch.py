#!/usr/bin/env python3
"""Generic open-source library-match tool for MCU RE passes (issue #41, reusable for any module:
m0400, m0306, m0900, m1400, ...).

Dan's rule: when a FUN_* / shape-named function looks like libm/CMSIS-DSP/libgcc soft-float, do not
just label it by shape - COMPILE (or extract from the toolchain's own prebuilt archive) the real
candidate source with the project's arm-none-eabi toolchain and diff the result against the firmware
bytes at the real address. This script does that diff, generically:

  - --ref-archive/--ref-member/--ref-symbol : pull a symbol straight out of a prebuilt .a (libgcc.a,
    libm.a, libc.a) - fastest, "the exact binary the vendor likely linked" when it matches.
  - --source/--ref-symbol (+ --cpu/--fpu/--float-abi/--opt-levels/--define/--include) : compile a
    candidate .c with arm-none-eabi-gcc at several -O levels and diff each.

Always logs to ./tmp/logs/mcu_libmatch.log. Never executes the firmware or the compiled reference -
static byte/instruction comparison only.

Usage (prebuilt archive, e.g. newlib sqrtf against m0400 Cortex-M4F):
  python3 scripts/re/mcu_libmatch.py --image firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin \\
    --base 0x08008000 --addr 0x080133d8 --size 58 \\
    --ref-archive /usr/arm-none-eabi/lib/thumb/v7e-m+fp/hard/libm.a \\
    --ref-member libm_a-wf_sqrt.o --ref-symbol sqrtf

Usage (compile CMSIS-DSP source, Cortex-M4F):
  python3 scripts/re/mcu_libmatch.py --image firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin \\
    --base 0x08008000 --addr 0x08008360 --size 836 \\
    --source /path/to/cmsis-dsp/Source/TransformFunctions/arm_cfft_radix4_f32.c \\
    --ref-symbol arm_radix4_butterfly_f32 \\
    --include /path/to/cmsis-dsp/Include --include /path/to/CMSIS/Include \\
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
    ap.add_argument("--cc-arg", action="append", default=[], dest="extra", help="extra arm-none-eabi-gcc argument")
    args = ap.parse_args()

    if not args.ref_symbol:
        raise SystemExit("--ref-symbol is required")
    if bool(args.ref_archive) == bool(args.source):
        raise SystemExit("give exactly one of --ref-archive(+--ref-member) or --source")

    fw = read_fw_bytes(args.image, args.base, args.addr, args.size)
    fw_insns = objdump_raw_thumb(args.toolchain_prefix, fw, args.addr)

    tag = f"[{args.module}] " if args.module else ""
    log(f"{tag}addr=0x{args.addr:x} size={args.size} symbol={args.ref_symbol!r}")

    results = []
    if args.ref_archive:
        ref, sz = extract_from_archive(args.toolchain_prefix, args.ref_archive, args.ref_member, args.ref_symbol)
        ref_insns = objdump_raw_thumb(args.toolchain_prefix, ref, 0)
        res = compare(fw, ref, fw_insns, ref_insns)
        res["candidate"] = f"{args.ref_archive}:{args.ref_member}:{args.ref_symbol}"
        results.append(res)
    else:
        for opt in args.opt_levels.split(","):
            obj = compile_source(args.toolchain_prefix, args.source, opt, args.cpu, args.fpu, args.float_abi,
                                  args.defines, args.includes, args.extra)
            try:
                ref, sz = extract_symbol_bytes(args.toolchain_prefix, obj, args.ref_symbol)
            finally:
                obj.unlink(missing_ok=True)
            ref_insns = objdump_raw_thumb(args.toolchain_prefix, ref, 0)
            res = compare(fw, ref, fw_insns, ref_insns)
            res["candidate"] = f"{args.source.name}:{args.ref_symbol}@-{opt}"
            results.append(res)

    for res in results:
        v = verdict(res)
        log(f"{tag}{res['candidate']}: fw_len={res['fw_len']} ref_len={res['ref_len']} "
            f"byte_exact={res['byte_exact']} byte_prefix_match={res['byte_prefix_match_pct']:.1f}% "
            f"insn_ratio={res['insn_ratio_pct']:.1f}% mnemonic_ratio={res['mnemonic_ratio_pct']:.1f}% "
            f"(fw {res['fw_insn_count']} insns, ref {res['ref_insn_count']} insns) -> {v}")
        print(f"{res['candidate']}: {v} (len fw={res['fw_len']} ref={res['ref_len']}, "
              f"insn_ratio={res['insn_ratio_pct']:.1f}%, mnemonic_ratio={res['mnemonic_ratio_pct']:.1f}%)")

    best = max(results, key=lambda r: r["insn_ratio_pct"])
    log(f"{tag}best: {best['candidate']} -> {verdict(best)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
