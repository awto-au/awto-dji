#!/usr/bin/env python3
"""Rebuild the m1400 (LPC1765 RC MCU) Ghidra project and APPLY committed names. Issue #84 (model: m0900_ghidra_names.py).

1. Gate: image reset vector (SP 0x10007f60, reset 0x23ba9) must land on a push {..,lr} at base 0xA000 + 0x19ba8.
2. analyzeHeadless: raw binary, ARM:LE:32:Cortex, base 0xA000; pre-script M1400Setup.java (SRAM/AHB SRAM/peripheral blocks so RAM rows apply); post-scripts M1400Names.java (applies
   docs/symbols/c1_m1400.tsv) then DumpLPC17xx.java (SVD labels, xrefs, disassembly, decompilation).
3. Outputs (tracked): re/ghidra-projects/m1400_radio/proj/, re/ghidra-projects/m1400_radio/m1400_dump.txt.
Log: ./tmp/logs/m1400_ghidra_names.log. Stall guard: no headless output for 60 s -> kill, fail.
"""
from __future__ import annotations

import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

STALL_LIMIT_S = 60  # no headless output this long = hung
POLL_S = 1  # stall-check resolution only
BASE = 0xA000
FW = REPO / "firmware" / "unpacked" / "C1_FW_V01.06.0000" / "C1_FW_V01.06.0000_m1400.bin"
SVD = REPO / "docs" / "data" / "lpc176x5x-register-map.tsv"
SYMBOLS = REPO / "docs" / "symbols" / "c1_m1400.tsv"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
PROJ_PARENT = REPO / "re" / "ghidra-projects" / "m1400_radio"
HEADLESS_LOG = REPO / "tmp" / "logs" / "m1400_ghidra_names_headless.log"


def assert_base() -> None:
    d = FW.read_bytes()
    sp, reset = struct.unpack_from("<II", d, 0)[0], struct.unpack_from("<II", d, 4)[0]
    off = (reset & ~1) - BASE
    h = struct.unpack_from("<H", d, off)[0]
    ok = (reset & 1) and 0 <= off < len(d) and ((h & 0xFF00) == 0xB500 or h == 0xE92D or (h & 0xF800) == 0x4800)
    log(f"base gate: SP={sp:#x} reset={reset:#x} -> offset {off:#x} first halfword {h:#06x} ok={bool(ok)}")
    if not ok:
        raise RuntimeError("m1400 base gate failed")


def run_ghidra() -> None:
    exe = shutil.which("analyzeHeadless") or str(Path.home() / ".local" / "bin" / "analyzeHeadless")
    proj = PROJ_PARENT / "proj"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    tmp_dump = REPO / "tmp" / "m1400_ghidra_names" / "m1400_dump.txt"
    tmp_dump.parent.mkdir(parents=True, exist_ok=True)
    cmd = [exe, str(proj), "M1400Project", "-import", str(FW), "-processor", "ARM:LE:32:Cortex",
           "-loader", "BinaryLoader", "-loader-baseAddr", f"{BASE:#x}", "-scriptPath", str(SCRIPT_DIR),
           "-preScript", "M1400Setup.java",
           "-postScript", "M1400Names.java", str(SYMBOLS),
           "-postScript", "DumpLPC17xx.java", str(tmp_dump), str(SVD)]
    log("running: " + " ".join(cmd))
    HEADLESS_LOG.parent.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
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
                raise RuntimeError(f"Ghidra stalled {STALL_LIMIT_S}s, killed; elapsed {time.monotonic() - t0:.0f}s")
            time.sleep(POLL_S)
    log(f"analyzeHeadless exit={proc.returncode} elapsed={time.monotonic() - t0:.0f}s log={HEADLESS_LOG}")
    if proc.returncode != 0 or not tmp_dump.exists():
        raise RuntimeError(f"Ghidra headless failed, see {HEADLESS_LOG}")
    shutil.copyfile(tmp_dump, PROJ_PARENT / "m1400_dump.txt")
    for line in HEADLESS_LOG.read_text(errors="replace").splitlines():
        if "M1400Names" in line and "applied" in line:
            log(line.strip())


def main() -> int:
    assert_base()
    run_ghidra()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
