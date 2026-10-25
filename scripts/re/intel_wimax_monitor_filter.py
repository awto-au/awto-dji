#!/usr/bin/env python3
"""Build an Intel WiMAX diagnostic monitor filter table (offline only).

This program does not communicate with a radio or modify firmware.
Intel's 256-byte filter maps each monitor event ID to one byte at
index (event_id - 4013), not a packed bitmap.
"""
import argparse
from pathlib import Path

FIRST_MONITOR = 4013  # MONITOR_START = 4012, plus 1
MONITOR_END = 4269
MONITOR_TABLE_SIZE = MONITOR_END - FIRST_MONITOR

NAMES = {
    4032: "L1 state",
    4034: "BER/PER statistics",
    4044: "symbol FFT antenna recording (format unverified)",
    4045: "CPR record buffer (format unverified)",
    4054: "L1 performance diagnostics",
    4165: "channel impulse debug",
    4166: "RF ADC power measurement",
}

def make_filter(ids):
    table = bytearray(MONITOR_TABLE_SIZE)
    for event in ids:
        if not FIRST_MONITOR <= event < MONITOR_END:
            raise ValueError(f"event {event} outside [{FIRST_MONITOR}, {MONITOR_END})")
        table[event - FIRST_MONITOR] = 1
    return bytes(table)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ids", nargs="*", type=int, help="monitor event IDs")
    parser.add_argument("--out", type=Path, help="write 256-byte table to a file")
    a = parser.parse_args()
    ids = a.ids if a.ids else sorted(NAMES)
    table = make_filter(ids)
    for event in sorted(set(ids)):
        print(f"{event}: filter[{event-FIRST_MONITOR}] = 1: {NAMES.get(event, 'unclassified')}")
    print(f"{len(table)} bytes, {sum(bool(x) for x in table)} enabled")
    if a.out:
        a.out.write_bytes(table)
        print(f"Saved: {a.out}")

if __name__ == "__main__":
    main()
