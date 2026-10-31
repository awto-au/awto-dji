#!/usr/bin/env python3
"""Decode m1400's FPGA/AD9363 boot script tables (interpreter fpga_script_exec_record @0x15a6c).

Record = 4 bytes [opcode, b1, b2, b3]; opcodes (from the decompile):
  5  raw 3-byte SPI0 frame to the FPGA slave: [b1, b2, b3]  (b1=0x0E write / 0x0F read)
  6  AD9363 write via FPGA bridge (reg 0x01=1): addr=b1<<8|b2, val=b3 (addr 0x0A3 patched from RAM)
  7  FPGA read [b1, b2, FF] (result discarded)
  8  AD9363 read via bridge: addr=b1<<8|b2 (0x0A3 result cached)
  9  FPGA read (result discarded)
  10 poll AD9363 reg (b1&0xf)<<8|b2 until bit (b3>>4) == (b3&1), 300 x 2 units
  11 delay b3 units
  12 FPGA reg 0x01 (bridge/engine mode) := {0x0a:2, 0x0b:1, 0x1a:0, 0x1b:1}[b1]

Tables (literal pool of fpga_post_boot_config @0x15b86): mode 3 -> 0x271d4 (0x313c B),
mode 0 -> 0x2a310 (0x91c B), mode 1 -> 0x2a310+0x91c (0x313c B), mode-3 extra -> 0x2dd68 (100 B).

  python3 scripts/re/m1400_fpga_script_decode.py            # summary + full listing to tmp/
Log: tmp/logs/m1400_fpga_script_decode.log (via scripts/_log.py)
"""
import collections
import os
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402  (scripts/_log.py: 3-tier repo root + tmp/logs logger)

REPO = str(REPO)
FW = os.path.join(REPO, "firmware", "unpacked", "C1_FW_V01.06.0000", "C1_FW_V01.06.0000_m1400.bin")
BASE = 0xA000
TABLES = {"mode3": (0x271D4, 0x313C), "mode0": (0x2A310, 0x91C), "mode1": (0x2A310 + 0x91C, 0x313C),
          "mode3_extra": (0x2DD68, 100)}
MODE12 = {0x0A: 2, 0x0B: 1, 0x1A: 0, 0x1B: 1}
OPN = {5: "FPGA_RAW", 6: "AD_WR", 7: "FPGA_RD", 8: "AD_RD", 9: "FPGA_RD", 10: "AD_POLL", 11: "DELAY", 12: "MODE"}


def decode(b, addr, length):
    out = []
    for i in range(0, length, 4):
        op, b1, b2, b3 = struct.unpack_from("<4B", b, addr - BASE + i)
        if op == 6 or op == 8:
            out.append((addr + i, OPN[op], (b1 << 8) | b2, b3))
        elif op == 10:
            out.append((addr + i, OPN[op], ((b1 & 0xF) << 8) | b2, b3))
        elif op == 12:
            out.append((addr + i, OPN[op], b1, MODE12.get(b1, "?")))
        elif op in OPN:
            out.append((addr + i, OPN[op], (b1 << 8) | b2, b3))
        else:
            out.append((addr + i, f"OP{op}", (b1 << 8) | b2, b3))
    return out


def main():
    os.makedirs(os.path.join(REPO, "tmp"), exist_ok=True)
    b = open(FW, "rb").read()
    outp = os.path.join(REPO, "tmp", "m1400_fpga_script_listing.txt")
    with open(outp, "w") as f:
        for name, (addr, length) in TABLES.items():
            recs = decode(b, addr, length)
            ops = collections.Counter(r[1] for r in recs)
            ad_wr = [r for r in recs if r[1] == "AD_WR"]
            fpga_raw = [r for r in recs if r[1] == "FPGA_RAW"]
            modes = [r for r in recs if r[1] == "MODE"]
            log("%s @0x%x: %d records %s" % (name, addr, len(recs), dict(ops)))
            log("  AD9363 writes: %d (distinct addrs %d, range 0x%03x..0x%03x)" % (len(ad_wr),
                len({r[2] for r in ad_wr}), min((r[2] for r in ad_wr), default=0), max((r[2] for r in ad_wr), default=0)))
            log("  FPGA raw frames: %d; mode changes: %s" % (len(fpga_raw), [(hex(r[0]), r[3]) for r in modes]))
            f.write(f"== {name} @0x{addr:x} ({len(recs)} records)\n")
            for a, op, x, y in recs:
                f.write(f"{a:06x} {op:8s} 0x{x:03x} {y if isinstance(y, str) else f'0x{y:02x}'}\n")
    log("-> %s" % outp)


if __name__ == "__main__":
    main()
