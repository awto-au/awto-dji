#!/usr/bin/env python3
"""Decode the m0400 DUML dispatch tables from the firmware image (issue #41).

Two dispatchers were found by literal-pool xrefs (m0400_literal_refs.py):
  A  FUN_08016fac  loads table base literal 0x08016ff0 -> 0x0801d464
     entry: {u32 handler (Thumb), u16 key at +4}; key compared with u16 at msg+4
  B  FUN_080170ac  loads table base literal 0x080170a8 -> 0x0801d46c
     entry: {u32 handler, u8 at +4 vs msg[0x0a], u8 at +5 vs msg[0x09]}
Both tables are 0-terminated (handler == 0). Key layout (set<<8 | id) is inferred
from the u16 form; confirm against the handler bodies before relying on it [guess].

Output: tmp/logs/m0400_cmd_table.log
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
BASE = 0x08008000
TABLE_A = 0x0801D464
TABLE_B = 0x0801D46C
MAX_ENTRIES = 64


def walk(data: bytes, base: int, label: str) -> list[tuple[int, int, int]]:
    rows = []
    for i in range(MAX_ENTRIES):
        off = base - BASE + 8 * i
        if off < 0 or off + 8 > len(data):
            log(f"{label}: entry {i} outside image", level="WARN")
            break
        handler, k4, k5 = struct.unpack_from("<IBB", data, off)
        if handler == 0:
            break
        if not (handler & 1) or not (BASE <= (handler & ~1) < BASE + len(data)):
            log(f"{label}: entry {i} at 0x{base + 8 * i:08x} not a handler, stop", level="WARN")
            break
        rows.append((base + 8 * i, handler & ~1, struct.unpack_from("<H", data, off + 4)[0]))
    return rows


def main() -> int:
    data = FW.read_bytes()
    for base, label in ((TABLE_A, "A u16-key"), (TABLE_B, "B u8 key")):
        rows = walk(data, base, label)
        log(f"table {label} at 0x{base:08x}: {len(rows)} entries")
        for at, h, key in rows:
            log(f"  0x{at:08x}  handler=0x{h:08x}  key=0x{key:04x} "
                f"(set=0x{key >> 8:02x} id=0x{key & 0xff:02x})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
