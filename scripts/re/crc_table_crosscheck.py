#!/usr/bin/env python3
"""Byte-compare DUML CRC8/CRC16 lookup tables across MCU firmware images.

Cross-module correlation pass (awto-dji#36/#41/#61): checks whether the
CRC8 (seed 0x77) and CRC16 (seed 0x3692) tables found independently in
m0900, m0400, m0306 and m1400 are byte-identical, not just same-seed.
Read-only: only reads firmware images already unpacked on disk
(not committed to the repo, see HANDOVER.md "DATA NOT IN THE REPO").

Usage: python3 scripts/re/crc_table_crosscheck.py
Log: ./tmp/logs/crc_table_crosscheck.log
"""
import hashlib
import logging
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
LOG_DIR = REPO / "tmp" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "crc_table_crosscheck.log", mode="w"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)

# (module, image path, load base, table addr, table len, table kind)
TABLES = [
    ("m0900", "firmware/unpacked/P3X_FW_V01.11.0020_m0900.bin", 0x08008000, 0x0801A208, 256, "crc8"),
    ("m0900", "firmware/unpacked/P3X_FW_V01.11.0020_m0900.bin", 0x08008000, 0x0801A308, 512, "crc16"),
    ("m0400", "firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin", 0x08008000, 0x0801B8D7, 256, "crc8"),
    ("m0400", "firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin", 0x08008000, 0x0801B6D4, 512, "crc16"),
    ("m0306", "firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin", 0x08020000, 0x080EF734, 512, "crc16"),
    ("m1400", "firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1400.bin", 0x00000000, 0x000249D2, 256, "crc8"),
]


def main():
    rows = []
    for mod, relpath, base, addr, length, kind in TABLES:
        path = REPO / relpath
        if not path.exists():
            log.warning("MISSING %s %s %s: %s not on disk, skipped", mod, kind, hex(addr), relpath)
            continue
        data = path.read_bytes()
        off = addr - base
        if off < 0 or off + length > len(data):
            log.warning("OUT OF RANGE %s %s %s: file offset 0x%x, len %d, file size %d",
                        mod, kind, hex(addr), off, length, len(data))
            continue
        table = data[off:off + length]
        sha = hashlib.sha256(table).hexdigest()[:16]
        rows.append((mod, kind, hex(addr), hex(off), length, sha, table[:8].hex()))
        log.info("%s %s addr=%s fileoff=%s len=%d sha256[:16]=%s first8=%s",
                  mod, kind, hex(addr), hex(off), length, sha, table[:8].hex())

    log.info("--- grouping by kind ---")
    for kind in ("crc8", "crc16"):
        group = [r for r in rows if r[1] == kind]
        if len(group) < 2:
            log.info("%s: only %d table(s) extracted, nothing to compare", kind, len(group))
            continue
        shas = {r[5] for r in group}
        if len(shas) == 1:
            log.info("%s: IDENTICAL bytes across %s", kind, [r[0] for r in group])
        else:
            log.info("%s: DIFFERENT bytes - %s", kind,
                      [(r[0], r[5]) for r in group])


if __name__ == "__main__":
    main()
