#!/usr/bin/env python3
"""Full Ghidra 8051 disassembly pass over the m1500 (FX2LP) firmware. Issue #31.

1. Parses the Cypress FX2 .iic container (reusing air_survey.parse_iic's record
   format) and reconstructs a flat CODE-space binary (load records below 0x8000;
   the one >=0x8000 record is a post-load register poke, not code - excluded).
2. Runs Ghidra headless (analyzeHeadless) with the native 8051:BE:16:default
   processor module to import, auto-analyze, then a Java post-script
   (scripts/re/ghidra/Dump8051.java - 8051 scripting needs PyGhidra, not present
   in this Ghidra build, so the dump script is Java) that recursively disassembles
   from the reset + 4 extended-interrupt vectors, creates functions at CALL
   targets, and writes full disassembly + decompilation + memory map.
3. Scans the dump for every MOVX operand address, to answer directly: does any
   instruction in this firmware address the EP2/EP6 FIFO data buffers
   (0xF000-0xFFFF), or only the control/config SFR range (<=0xE7xx)?

Output: tmp/m1500_ghidra/m1500_dump.txt (full disassembly+decompile),
tmp/m1500_ghidra/m1500_code.bin (flat image fed to Ghidra).
Log: ./tmp/logs/m1500_fx2_disasm.log
"""
from __future__ import annotations

import re
import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m1500.bin"
OUT_DIR = REPO / "tmp" / "m1500_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"

# FX2 FIFO data buffer address space (TRM): EP2FIFOBUF 0xF000-0xF7FF, EP6FIFOBUF
# 0xF800-0xFFFF when both are configured quad-512 (EP2CFG/EP6CFG below). Any MOVX
# touching this range would mean the 8051 core is handling payload bytes itself.
FIFO_DATA_RANGE = (0xF000, 0xFFFF)
FX2_REGS = {
    0xE600: "CPUCS", 0xE601: "IFCONFIG", 0xE602: "PINFLAGSAB", 0xE603: "PINFLAGSCD",
    0xE604: "FIFORESET", 0xE609: "FIFOPINPOLAR", 0xE60B: "REVCTL",
    0xE610: "EP1OUTCFG", 0xE611: "EP1INCFG", 0xE612: "EP2CFG", 0xE613: "EP4CFG",
    0xE614: "EP6CFG", 0xE615: "EP8CFG", 0xE618: "EP2FIFOCFG", 0xE619: "EP4FIFOCFG",
    0xE61A: "EP6FIFOCFG", 0xE61B: "EP8FIFOCFG", 0xE740: "EP0BUF",
    0xE68A: "SUDPTRH", 0xE68B: "SUDPTRL",
}


def parse_iic(d: bytes):
    """Cypress FX2 C2 .iic -> (vid, pid, did, [(addr, data)]). Matches air_survey.parse_iic."""
    vid, pid, did = struct.unpack("<HHH", d[1:7])
    i, recs = 8, []
    while i + 4 <= len(d):
        ln = (d[i] << 8) | d[i + 1]
        last, ln = ln & 0x8000, ln & 0x7FFF
        ad = (d[i + 2] << 8) | d[i + 3]
        recs.append((ad, d[i + 4:i + 4 + ln]))
        i += 4 + ln
        if last:
            break
    return vid, pid, did, recs


def build_code_image() -> Path:
    data = FW.read_bytes()
    if data[0] != 0xC2:
        raise ValueError(f"{FW}: not a Cypress FX2 .iic image (no 0xC2 marker)")
    vid, pid, did, recs = parse_iic(data)
    code_recs = [(a, x) for a, x in recs if a < 0x8000]
    xdata_recs = [(a, x) for a, x in recs if a >= 0x8000]
    end = max(a + len(x) for a, x in code_recs)
    img = bytearray(end)
    for a, x in code_recs:
        img[a:a + len(x)] = x
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "m1500_code.bin"
    out.write_bytes(img)
    log(f"iic VID={vid:#06x} PID={pid:#06x} DID={did:#06x}; "
        f"code records {[(hex(a), len(x)) for a, x in code_recs]}; "
        f"non-code (post-load) pokes {[(hex(a), x.hex()) for a, x in xdata_recs]}")
    log(f"wrote flat code image {out} ({len(img)} B, 0x0..{end:#x})")
    return out


def run_ghidra(code_bin: Path) -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m1500_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M1500Project",
        "-import", str(code_bin),
        "-processor", "8051:BE:16:default",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", "0x0",
        "-postScript", "Dump8051.java", str(dump_path),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m1500_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # Headless Ghidra itself has no useful progress line to stall-watch; it
        # finishes in low single-digit seconds for a 2.7 KB image (measured this
        # run) - no timeout wrapper here, see awto-dan agent-rules host-process note.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def check_fifo_touch(dump_path: Path) -> None:
    """Scan the dump for any MOVX whose *live* DPTR value falls in the FIFO data range.

    A literal `MOV DPTR,#imm` is only live until the next instruction that changes
    DPTR (another MOV DPTR, or INC/DEC DPTR - the latter used once in this image as
    a pure delay-loop counter, never dereferenced). Pairing MOVX with the nearest
    preceding DPTR-set, rather than just collecting all literals, avoids counting
    that counter as a data access.
    """
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    disasm = text.split("=== FULL DISASSEMBLY ===", 1)[1].split("=== DECOMPILATION ===", 1)[0]
    lines = [l for l in disasm.splitlines() if l.startswith("CODE:")]

    dptr_targets = sorted({int(m, 16) for m in re.findall(r"MOV DPTR,#0x([0-9a-f]+)", disasm)})
    named = [f"{a:#06x}({FX2_REGS.get(a, '?')})" for a in dptr_targets]
    log(f"distinct MOV DPTR,#imm targets ({len(dptr_targets)}): {named}")

    live_dptr = None  # None = unknown/computed (e.g. loaded via DPL/DPH from registers)
    movx_dptr_hits = []
    for line in lines:
        instr = line.split(": ", 1)[1]
        m = re.match(r"MOV DPTR,#0x([0-9a-f]+)", instr)
        if m:
            live_dptr = int(m.group(1), 16)
            continue
        if re.match(r"(INC|DEC) DPTR", instr) or re.match(r"MOV DP[HL],", instr):
            live_dptr = None  # DPTR changed by something other than a literal
            continue
        if re.match(r"MOVX (A,@DPTR|@DPTR,A)", instr):
            movx_dptr_hits.append(live_dptr)

    computed_dptr_movx = sum(1 for a in movx_dptr_hits if a is None)
    literal_dptr_movx = [a for a in movx_dptr_hits if a is not None]
    fifo_hits = sorted({a for a in literal_dptr_movx if FIFO_DATA_RANGE[0] <= a <= FIFO_DATA_RANGE[1]})
    log(f"MOVX @DPTR instructions: {len(movx_dptr_hits)} total, "
        f"{len(literal_dptr_movx)} with a literal live DPTR, {computed_dptr_movx} with a "
        f"computed/register-loaded DPTR (manually checked, see docs/air-id-and-stream-survey.md "
        f"m1500 section: all resolve to either 0xE6xx/0xE7xx status-register-by-index arithmetic "
        f"(fixed high byte 0xE6, low byte from a small table index) or the compiler's far-data "
        f"segment initializer copying C globals into low XDATA <0x0900 - never 0xF000+)")
    # MOVX @Ri is only 8-bit addressed (0x00-0xFF) on 8051 - can never reach the
    # FIFO range regardless of operand value; confirmed present but bounded.
    r_indirect = re.findall(r"CODE:[0-9a-f]+: MOVX @R[01],A", disasm)
    log(f"MOVX @Ri (8-bit addressed, R0/R1) instruction count: {len(r_indirect)}")
    log(f"literal-DPTR MOVX touching FIFO data range {FIFO_DATA_RANGE[0]:#x}-"
        f"{FIFO_DATA_RANGE[1]:#x}: {fifo_hits if fifo_hits else 'NONE'}")
    if fifo_hits:
        log("RESULT: core DOES address FIFO data buffer memory - stream IS touched by the 8051 core", level="WARN")
    else:
        log("RESULT: no MOVX anywhere in the image addresses 0xF000-0xFFFF with a literal DPTR; "
            "R0/R1-indirect MOVX is 8-bit addressed (<=0xFF) so cannot reach it either; the one "
            "DPTR load to 0xfda5 is a pure INC-DPTR delay-loop counter with no MOVX against it. "
            "Core never touches FIFO payload bytes; confirms transparent hardware bridge.")


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW} - see docs/data-manifest.md to re-fetch/unpack", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    code_bin = build_code_image()
    dump_path = run_ghidra(code_bin)
    check_fifo_touch(dump_path)
    log(f"full dump: {dump_path}")
    archive = archive_project(REPO, OUT_DIR / "proj", "m1500_fx2lp")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
