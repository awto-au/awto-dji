#!/usr/bin/env python3
"""Rebuild the m0400 (STM32F4 gimbal MCU) Ghidra project and APPLY committed names. Issue #41.

1. Gate: m0400_base_check.assert_base() (link base 0x08008000).
2. analyzeHeadless: raw binary, ARM:LE:32:Cortex, base 0x08008000; pre-script M0400Setup.java adds
   SRAM/PERIPH/SCS blocks; auto-analysis; post-script M0400Dump.java applies
   docs/symbols/m0400.tsv (names, labels, `type=` data types) + the C block of
   docs/symbols/m0400-structs.h, then dumps functions/callsites/strings/disassembly/decompilation.
3. Outputs (tracked): re/ghidra-projects/m0400_gimbal/proj/ (the .gpr project, names persisted),
   re/ghidra-projects/m0400_gimbal/m0400_dump.txt. Renames live in the TSV; the project is regenerable.
Usage: m0400_ghidra_names.py [--no-dump-copy]
Log: ./tmp/logs/m0400_ghidra_names.log (headless: ./tmp/logs/m0400_ghidra_names_headless.log)
Stall guard: no headless output for 60 s -> kill, fail, log last line + silence.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from m0400_base_check import DECLARED_BASE, FW, assert_base  # noqa: E402

STALL_LIMIT_S = 60  # no headless output this long = hung (decompile prints one line per function)
POLL_S = 1  # stall-check resolution only
PROJ_PARENT = REPO / "re" / "ghidra-projects" / "m0400_gimbal"
PROJ_NAME = "M0400Project"
DUMP = PROJ_PARENT / "m0400_dump.txt"
SYMBOLS = REPO / "docs" / "symbols" / "m0400.tsv"
STRUCTS = REPO / "docs" / "symbols" / "m0400-structs.h"
SVD = REPO / "docs" / "data" / "stm32f407-register-map.tsv"  # RM0090 register labels
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
HEADLESS_LOG = REPO / "tmp" / "logs" / "m0400_ghidra_names_headless.log"


def analyze_headless() -> str:
    exe = shutil.which("analyzeHeadless") or str(Path.home() / ".local" / "bin" / "analyzeHeadless")
    return exe


def run_ghidra() -> None:
    proj = PROJ_PARENT / "proj"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    tmp_dump = REPO / "tmp" / "m0400_ghidra_names" / "m0400_dump.txt"
    tmp_dump.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        analyze_headless(), str(proj), PROJ_NAME,
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", f"{DECLARED_BASE:#x}",
        "-scriptPath", str(SCRIPT_DIR),
        "-preScript", "M0400Setup.java",
        "-postScript", "M0400Dump.java", str(tmp_dump), str(SYMBOLS), str(STRUCTS), str(SVD),
    ]
    log("running: " + " ".join(cmd))
    HEADLESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.monotonic()
    with HEADLESS_LOG.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        last_size, last_change = -1, time.monotonic()
        while proc.poll() is None:
            size = HEADLESS_LOG.stat().st_size
            if size != last_size:
                last_size, last_change = size, time.monotonic()
            elif time.monotonic() - last_change > STALL_LIMIT_S:
                proc.kill()
                proc.wait()
                tail = HEADLESS_LOG.read_text(encoding="utf-8", errors="replace").splitlines()[-1:]
                raise RuntimeError(f"Ghidra stalled {STALL_LIMIT_S}s, killed; last line: {tail}; "
                                   f"elapsed {time.monotonic() - t_start:.0f}s")
            time.sleep(POLL_S)
    log(f"analyzeHeadless exit={proc.returncode} elapsed={time.monotonic() - t_start:.0f}s log={HEADLESS_LOG}")
    if proc.returncode != 0 or not tmp_dump.exists():
        raise RuntimeError(f"Ghidra headless failed, see {HEADLESS_LOG}")
    shutil.copyfile(tmp_dump, DUMP)
    for line in HEADLESS_LOG.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(("INFO  SCRIPT:", "M0400")) or "M0400" in line and "applied" in line:
            log(line.strip())
    log(f"dump -> {DUMP}")


def main() -> int:
    assert_base()
    run_ghidra()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
