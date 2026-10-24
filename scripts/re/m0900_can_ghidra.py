#!/usr/bin/env python3
"""Headless Ghidra pass over the m0900 (STM32F103) image for the CAN1 reversal. Issue #36.

1. Runs analyzeHeadless (own project dir tmp/m0900_can_ghidra/proj, separate from the
   SPI1 investigation #18) on firmware/P3X_FW_V01.11.0020_m0900.bin, loaded raw at
   0x08000000, processor ARM:LE:32:Cortex.
2. Post-script scripts/re/ghidra/M0900Dump.java writes functions, call sites,
   full disassembly (with owning function) and decompilation to
   tmp/m0900_can_ghidra/m0900_dump.txt.
3. Literal-pool scan: every 32-bit word in flash equal to a CAN1 (0x40006400..) or
   SRAM target of interest is listed with the functions whose LDR loads it.

Outputs: tmp/m0900_can_ghidra/m0900_dump.txt, tmp/m0900_can_ghidra/literal_hits.txt
Log:     tmp/logs/m0900_can_ghidra.log (headless output: tmp/logs/m0900_can_ghidra_headless.log)

Stall guard: headless log silent for 60 s -> kill, fail, log last line.
"""
from __future__ import annotations

import re
import shutil
import struct
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
OUT_DIR = REPO / "tmp" / "m0900_can_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
BASE = 0x08000000
STALL_LIMIT_S = 60  # no headless output for this long = hung (agent-rules host-process rule)

# Targets for the literal-pool scan (CAN1 block 0x40006400-0x400067FF, SRAM used by CAN code).
TARGET_RANGES = {
    "CAN1": (0x40006400, 0x400067FF),
    "CAN_SRAM_TXQ_2538": (0x20002538, 0x20002538),
    "CAN_SRAM_2330": (0x20002330, 0x20002330),
    "RING_24b8": (0x200024B8, 0x200024B8),
}


def run_ghidra() -> Path:
    proj = OUT_DIR / "proj"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir(parents=True)
    dump = OUT_DIR / "m0900_dump.txt"
    headless_log = REPO / "tmp" / "logs" / "m0900_can_ghidra_headless.log"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj), "M0900CanProject",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", f"{BASE:#x}",
        "-postScript", "M0900Dump.java", str(dump),
        "-scriptPath", str(SCRIPT_DIR),
        "-deleteProject",
    ]
    log("running: " + " ".join(cmd))
    with headless_log.open("w", encoding="utf-8") as fh:
        proc = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        last_size, last_change = -1, time.monotonic()
        while proc.poll() is None:
            size = headless_log.stat().st_size
            if size != last_size:
                last_size, last_change = size, time.monotonic()
            elif time.monotonic() - last_change > STALL_LIMIT_S:
                proc.kill()
                proc.wait()
                tail = headless_log.read_text(encoding="utf-8", errors="replace").splitlines()[-3:]
                raise RuntimeError(f"Ghidra stalled {STALL_LIMIT_S}s, killed; last lines: {tail}")
            time.sleep(1)  # poll interval 1 s: stall limit is 60 s, so 1 s resolution is ample
    log(f"analyzeHeadless exit={proc.returncode}, log {headless_log}")
    if proc.returncode != 0 or not dump.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump


def literal_scan(dump: Path) -> None:
    """Find flash literal-pool words in the CAN/SRAM target ranges and the LDR sites using them."""
    data = FW.read_bytes()
    hits: dict[str, list[tuple[int, int]]] = {k: [] for k in TARGET_RANGES}
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        for name, (lo, hi) in TARGET_RANGES.items():
            if lo <= v <= hi:
                hits[name].append((BASE + off, v))
    text = dump.read_text(encoding="utf-8", errors="replace")
    disasm = text.split("=== FULL DISASSEMBLY ===", 1)[1].split("=== DECOMPILATION ===", 1)[0]
    lines = [l for l in disasm.splitlines() if " ; ref->" in l]
    out = []
    for name, lst in hits.items():
        for lit_addr, val in lst:
            # Ghidra prints flash addresses without 0x: "ref->08001234(READ)".
            users = [l.split(":", 1)[0] + " " + l.split("[", 1)[1].split("]", 1)[0]
                     for l in lines if re.search(rf"ref->{lit_addr:08x}\(", l)]
            out.append(f"{name} value={val:#010x} literal@{lit_addr:#010x} users={users}")
    out_path = OUT_DIR / "literal_hits.txt"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    log(f"literal-pool hits: {sum(len(v) for v in hits.values())} -> {out_path}")


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW}", level="ERROR")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    dump = run_ghidra()
    literal_scan(dump)
    log(f"full dump: {dump}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
