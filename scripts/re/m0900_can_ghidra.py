#!/usr/bin/env python3
"""CAN1 reversal pass over the m0900 image (issue #36): rebuild project via m0900_ghidra_names.py
(base 0x08008000, gated by m0900_base_check.py), then literal-pool scan for CAN1 / CAN SRAM objects.

Outputs: re/ghidra-projects/m0900_radio/m0900_dump.txt, tmp/m0900_can_ghidra/literal_hits.txt
Log: tmp/logs/m0900_can_ghidra.log
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from m0900_base_check import DECLARED_BASE as BASE, FW  # noqa: E402
import m0900_ghidra_names  # noqa: E402

OUT_DIR = REPO / "tmp" / "m0900_can_ghidra"
TARGET_RANGES = {
    "CAN1": (0x40006400, 0x400067FF),
    "CAN_SRAM_TXQ_2538": (0x20002538, 0x20002538),
    "CAN_SRAM_2330": (0x20002330, 0x20002330),
    "RING_24b8": (0x200024B8, 0x200024B8),
}


def literal_scan(dump: Path) -> None:
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
            users = [l.split(":", 1)[0] + " " + l.split("[", 1)[1].split("]", 1)[0]
                     for l in lines if re.search(rf"ref->{lit_addr:08x}\(", l)]
            out.append(f"{name} value={val:#010x} literal@{lit_addr:#010x} users={users}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "literal_hits.txt"
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    log(f"literal-pool hits: {sum(len(v) for v in hits.values())} -> {out_path}")


def main() -> int:
    m0900_ghidra_names.main()
    literal_scan(m0900_ghidra_names.DUMP)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
