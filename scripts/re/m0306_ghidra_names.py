#!/usr/bin/env python3
"""Rebuild the m0306 (STM32F427 flight controller) Ghidra project and APPLY committed names. Issues #40, #83.

1. Gate: m0306_base_check.assert_base() (link base 0x08020000, NOT 0x08000000).
2. analyzeHeadless: raw binary, ARM:LE:32:Cortex, base 0x08020000; pre-script M0306Setup.java adds
   SRAM/PERIPH/SCS blocks; auto-analysis; post-script M0306Names.java applies
   docs/symbols/m0306*.tsv (legacy + m0306-names.tsv; names, labels, `type=` data types) + the C block of
   docs/symbols/m0306-structs.h, then dumps functions/callsites/strings/disassembly/decompilation.
3. Outputs (tracked): re/ghidra-projects/m0306_flight_controller/proj/ (the .gpr project, names persisted),
   re/ghidra-projects/m0306_flight_controller/m0306_dump.txt. Renames live in the TSV; the project is regenerable.
Usage: m0306_ghidra_names.py [--no-dump-copy]
Log: ./tmp/logs/m0306_ghidra_names.log (headless: ./tmp/logs/m0306_ghidra_names_headless.log)
Stall guard: no headless output AND no CPU progress (auto-analysis is silent) for 60 s -> kill, fail, log last line + silence.
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
from m0306_base_check import DECLARED_BASE, FW, assert_base  # noqa: E402

STALL_LIMIT_S = 60  # no headless output this long = hung (decompile prints one line per function)
POLL_S = 1  # stall-check resolution only
PROJ_PARENT = REPO / "re" / "ghidra-projects" / "m0306_flight_controller"
PROJ_NAME = "M0306Project"
DUMP = PROJ_PARENT / "m0306_dump.txt"
SYM = REPO / "docs" / "symbols"
SYMBOLS = [SYM / "m0306.tsv", SYM / "m0306-data.tsv", SYM / "m0306-params.tsv", SYM / "m0306-vectors.tsv", SYM / "m0306-duml-handlers.tsv", SYM / "m0306-names.tsv"]  # later files win
STRUCTS = REPO / "docs" / "symbols" / "m0306-structs.h"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
HEADLESS_LOG = REPO / "tmp" / "logs" / "m0306_ghidra_names_headless.log"


def cpu_ticks(tag: str) -> int:
    """utime+stime (clock ticks) summed over processes whose cmdline contains tag; progress proof during silent auto-analysis."""
    total = 0
    for d in Path("/proc").iterdir():
        if not d.name.isdigit():
            continue
        try:
            if tag.encode() not in (d / "cmdline").read_bytes():
                continue
            f = (d / "stat").read_text().rsplit(")", 1)[1].split()
            total += int(f[11]) + int(f[12])
        except (OSError, IndexError, ValueError):
            continue
    return total


def analyze_headless() -> str:
    exe = shutil.which("analyzeHeadless") or str(Path.home() / ".local" / "bin" / "analyzeHeadless")
    return exe


def run_ghidra() -> None:
    proj = PROJ_PARENT / "proj"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    tmp_dump = REPO / "tmp" / "m0306_ghidra_names" / "m0306_dump.txt"
    tmp_dump.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        analyze_headless(), str(proj), PROJ_NAME,
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", f"{DECLARED_BASE:#x}",
        "-scriptPath", str(SCRIPT_DIR),
        "-preScript", "M0306Setup.java",
        "-postScript", "M0306Names.java", str(tmp_dump), str(STRUCTS), *[str(p) for p in SYMBOLS],
    ]
    log("running: " + " ".join(cmd))
    HEADLESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    t_start = time.monotonic()
    with HEADLESS_LOG.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        last_size, last_cpu, last_change = -1, -1, time.monotonic()
        while proc.poll() is None:
            size, cpu = HEADLESS_LOG.stat().st_size, cpu_ticks(PROJ_NAME)
            if size != last_size or cpu - last_cpu > 100:  # >1 s CPU per poll window = analysing, not hung
                last_size, last_cpu, last_change = size, cpu, time.monotonic()
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
        if line.startswith(("INFO  SCRIPT:", "M0306")) or "M0306" in line and "applied" in line:
            log(line.strip())
    log(f"dump -> {DUMP}")


def main() -> int:
    assert_base()
    run_ghidra()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
