#!/usr/bin/env python3
"""Full Ghidra RE pass over the m0400 (gimbal MCU) firmware, redo of the shallow awto-dji#41
pass (0c4234a only decoded 2/27 dispatch entries and left peripherals as bare ref counts).

Adds real STM32F407 (RM0090) SVD register labels (docs/data/stm32f407-register-map.tsv, via
scripts/re/svd_to_labels.py) and full decompilation of all functions, same method as the
m1400/LPC1765 pass (issue #39) that set the depth bar for this redo. Loader: raw binary,
ARM:LE:32:Cortex, base 0x08008000 (unchanged from the first pass, confirmed in
docs/air-id-and-stream-survey.md "m0400 gimbal" - RCC/FLASH/USART1 literals line up).

Output: tmp/m0400_ghidra/m0400_full_dump.txt (SVD label count, function list, named
peripheral-base xrefs, full disassembly, full decompilation of all functions).
Log: ./tmp/logs/m0400_full_reversing.log (headless log: m0400_full_headless.log)
Ghidra project re-archived to re/ghidra-projects/m0400_gimbal.tar.gz on success.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
BASE_ADDR = "0x08008000"
SVD_LABELS = REPO / "docs" / "data" / "stm32f407-register-map.tsv"
OUT_DIR = REPO / "tmp" / "m0400_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
CMD_TABLE = "0x0801D46C:27"


def run_ghidra() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proj_dir = OUT_DIR / "proj_full"
    if proj_dir.exists():
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m0400_full_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M0400FullProject",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", BASE_ADDR,
        "-postScript", "DumpM0400Full.java", str(dump_path), str(SVD_LABELS), CMD_TABLE,
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0400_full_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # 328-function, 97 KB Cortex-M4 image; the m1400 pass (155 KB, similar function
        # count) completed full decompile-all in well under its own run, no timeout wrapper
        # - headless Ghidra gives no stall-watchable progress line to key a timeout off.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW}", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    if not SVD_LABELS.exists():
        log(f"SVD label TSV not found at {SVD_LABELS} - run svd_to_labels.py first", level="ERROR")
        return 1
    dump_path = run_ghidra()
    log(f"full dump: {dump_path} ({dump_path.stat().st_size} bytes)")
    archive = archive_project(REPO, OUT_DIR / "proj_full", "m0400_gimbal")
    log(f"project re-archived: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
