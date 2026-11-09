#!/usr/bin/env python3.15t
"""Emit the real m2001 TX stimulus as SPI (op,reg,val) triples for the gate-level sim (#89 step 3).

Replays what the ground firmware (m1400) does: the two 256-register boot passes (copy0 reg0=0xB8,
copy1 reg0=0x08) decoded from the FPGA init script, an optional documented post-boot trigger, then
one uplink record (regs 0x44..0x7B + the 8 ID bytes) built by cycloneiv_clean_uplink_record.py.

All writes use opcode 0x0E (reads 0x0F); the copy is picked by FPGA reg0 bit7 (V: m1400
fpga_reg_write @0xbdf6, FUN_00015d4a; awto-dji #89). The uplink PAYLOAD is synthetic (the real ID /
key / header template live in runtime RAM, not the firmware image) — this exercises the TX plumbing
and modulation structure, not real traffic.

  python3.15t fpga/m2001/scripts/cycloneiv_clean_tx_stimulus.py [--trigger] [--out FILE]
Output: a text file of `OP REG VAL` hex triples (one per line, `#` comments), default
tmp/cycloneiv_clean/tx_stimulus.txt. Feed to the sim's +stim=<file>.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import DJI  # noqa: E402
import cycloneiv_clean_uplink_record as UR  # noqa: E402

LISTING = os.path.join(DJI, "tmp", "m1400_fpga_script_listing.txt")


def boot_passes():
    """The first two FPGA_RAW 256-register passes from the mode3 table -> [(0x0E,reg,val)]. V decode."""
    if not os.path.isfile(LISTING):
        sys.exit(f"missing {LISTING}; run scripts/re/m1400_fpga_script_decode.py first")
    triples, passes = [], 0
    for line in open(LISTING):
        f = line.split()
        if len(f) >= 3 and f[1] == "FPGA_RAW":          # cols: addr FPGA_RAW 0xeRR 0xVV
            reg, val = int(f[2], 16) & 0xFF, int(f[3], 16) & 0xFF
            triples.append((0x0E, reg, val))
            if reg == 0xFF:
                passes += 1
                if passes == 2:                         # copy0 + copy1 only; the AD9363 bridge block follows
                    break
    return triples


def record_writes():
    """One uplink record (synthetic payload) as the firmware writes it: reg0|=0x80, ID bytes, 0x44..0x7B, reg0&=~0x80."""
    tmpl = bytes(range(0x0F)); chunk = UR.duml_frame(0x00, 0x01, bytes(range(4)))
    rec = UR.build_record(tmpl, chunk, 7, bytes(range(1, 9)))         # 0x38 bytes -> regs 0x44..0x7B
    idb = UR.build_id_block(bytes([0x12, 0x34, 0x56, 0x78, 0x00, 0x01, 0x02]))   # 8 bytes
    out = [(0x0E, 0x00, 0x88)]                                        # reg0 (0x08) | 0x80 = copy select
    out += [(0x0E, 0x40 + i, idb[i]) for i in range(4)]
    out += [(0x0E, 0x7C + i, idb[4 + i]) for i in range(4)]
    out += [(0x0E, 0x44 + i, rec[i]) for i in range(len(rec))]
    out += [(0x0E, 0x00, 0x08)]                                       # reg0 &= ~0x80
    return out


def trigger():
    """Documented post-boot arm (dji-m2001-loopback.md:14): [0E 01 02] + reg0 bit0 pulse. HYPOTHESIS (OP13 is U)."""
    return [(0x0E, 0x01, 0x02), (0x0E, 0x00, 0x09), (0x0E, 0x00, 0x08)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trigger", action="store_true", help="append the documented (unverified) post-boot arm pulse")
    ap.add_argument("--out", default=os.path.join(DJI, "tmp", "cycloneiv_clean", "tx_stimulus.txt"))
    a = ap.parse_args()
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    boot, rec = boot_passes(), record_writes()
    trig = trigger() if a.trigger else []
    with open(a.out, "w") as f:                                  # comment-free: the sim reads this with $fscanf("%h %h %h")
        for _label, seq in (("boot", boot), ("trigger", trig), ("record", rec)):
            for op, rg, v in seq:
                f.write(f"{op:02X} {rg:02X} {v:02X}\n")
    print(f"wrote {len(boot)} boot + {len(trig)} trigger + {len(rec)} record writes -> {a.out}  (section breakdown in this message; file is comment-free for $fscanf)")


if __name__ == "__main__":
    main()
