#!/usr/bin/env python3
"""Full Ghidra ARM Cortex-M disassembly pass over the m0900 (air radio MCU) firmware.

Issue #18: settle whether SPI1 (0x40013000, separate from the already-traced SPI2
0x40003800 FPGA bridge) is used anywhere in the firmware. scripts/re/m0900_trace.py
(capstone linear sweep) already found exactly one SPI1-base literal load, inside the
generic StdPeriph SPI_DeInit() dispatcher, never called. This script repeats the
search with Ghidra's full auto-analysis (recursive disassembly from the reset vector,
function boundaries from real flow analysis, not a resyncing linear sweep) as an
independent check, matching the rigor of the m1500/FX2LP Ghidra pass (issue #31).

Loader: raw binary, ARM:LE:32:Cortex, base 0x08008000 (app region; bootloader
0x08000000-0x08008000 is not in this image - m0900_trace.py reset-vector check).

Output: tmp/m0900_ghidra/m0900_dump.txt (function list + full disassembly +
named-peripheral literal xrefs for SPI1/SPI2/GPIOA/B/C/RCC).
Log: ./tmp/logs/m0900_ghidra_disasm.log
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
BASE_ADDR = "0x08008000"
OUT_DIR = REPO / "tmp" / "m0900_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"


def run_ghidra() -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m0900_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M0900Project",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", BASE_ADDR,
        "-postScript", "DumpARM.java", str(dump_path),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0900_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # Full auto-analysis on a 75 KB Cortex-M image; measured this run below in
        # the log. No timeout wrapper - headless Ghidra gives no stall-watchable
        # progress line (awto-dan agent-rules host-process note), and this image is
        # two orders smaller than anything Ghidra's analyzers are slow on.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def report(dump_path: Path) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    section = text.split("=== NAMED PERIPHERAL LITERAL XREFS ===", 1)[-1]
    log("--- NAMED PERIPHERAL LITERAL XREFS (Ghidra) ---")
    for line in section.splitlines():
        if line.strip():
            log(line)
    func_count_line = next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), "")
    log(func_count_line)
    insn_line = next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), "")
    log(insn_line)


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW} - see docs/data-manifest.md", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    dump_path = run_ghidra()
    report(dump_path)
    log(f"full dump: {dump_path}")
    archive = archive_project(REPO, OUT_DIR / "proj", "m0900_radio")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
