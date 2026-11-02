#!/usr/bin/env python3
"""Dump the PHY/RF tables found in the Intel i6050 firmware (awto-dji#61). Needs tmp/intel-wimax/ from intel_wimax_sbcf.py --out.
Prints: band-plan block @0xc8fc00, kHz->band-index classifier chain @0xea5ce8, RF calibration-bin table @0xeef60c,
bandwidth / sample-rate pools, per-bandwidth numerology records. Log: tmp/logs/intel_wimax_phy_tables.log
"""
import re, struct, subprocess, sys
from pathlib import Path

D = Path("tmp/intel-wimax")
REG = {}
for line in (D / "regions.tsv").read_text().splitlines()[1:]:
    f, a, s = line.split("\t")
    REG[int(a, 16)] = (D / f).read_bytes()


def u32(a):
    for base, d in REG.items():
        if base <= a < base + len(d):
            return struct.unpack_from("<I", d, a - base)[0]
    raise KeyError(hex(a))


def band_plan():
    print("== band-plan block @0xc8fc00 (magic %#x), 24-bit LE kHz values" % u32(0xC8FC00))
    base = 0xC8FC00
    d = REG[base]
    vals = []
    for o in range(0x20, 0x60):
        v = d[o] | d[o + 1] << 8 | d[o + 2] << 16
        if 2200000 <= v <= 3900000 and v % 1000 == 0 and d[o + 3] == 0:
            vals.append((hex(base + o), v))
    print("  ", vals)


def classifier():
    print("== classifier 0xea5ce8 (kHz -> band idx): (limit_kHz, idx) from cmp/bhi chain")
    out = subprocess.check_output([sys.executable, "-I", "scripts/re/intel_wimax_dis.py", "ea5ce8", "140", "thumb"], text=True).splitlines()
    limit = None
    res = []
    for l in out[8:]:  # skip prologue / low-range error path
        m = re.match(r"([0-9a-f]+): ldr +r1, \[pc, #0x([0-9a-f]+)\]", l)
        if m:
            limit = u32(((int(m[1], 16) + 4) & ~3) + int(m[2], 16))
        m = re.match(r"[0-9a-f]+: movs +r4, #(0x)?([0-9a-f]+)", l)
        if m and limit is not None:
            res.append((limit, int(m[2], 16) if m[1] else int(m[2])))
            limit = None
    print("  f < %d -> idx 0 + trace log; " % u32(0xEA5DE0 + 0) if False else "", res)


def cal_bins():
    print("== RF cal-bin table from 0xeef5e4: {lo_kHz, hi_kHz, idx} rows, groups = idx restarts")
    a = 0xEEF5E4
    rows = []
    while True:
        lo, hi, n = u32(a), u32(a + 4), u32(a + 8)
        if not (1000000 < lo < hi < 7000000 and n < 64):
            break
        rows.append((lo, hi, n))
        a += 12
    grp = []
    for r in rows:
        if grp and r[2] == 0:
            print("   group idx0..%d  %d..%d kHz (%d rows)" % (grp[-1][2], grp[0][0], grp[-1][1], len(grp)))
            grp = []
        grp.append(r)
    print("   group idx0..%d  %d..%d kHz (%d rows)" % (grp[-1][2], grp[0][0], grp[-1][1], len(grp)))
    for r in rows:
        if r[0] < 2800000:
            print("   %7d %7d idx %2d  width %5d" % (r[0], r[1], r[2], r[1] - r[0]))
    print("   end %#x rows %d" % (a, len(rows)))


def numerology():
    print("== bandwidth / sample-rate pools")
    print("  @0xe94410 8.75M,7M:", u32(0xE94410), u32(0xE94414), "; Fs pool @0xe9442c:", u32(0xE9442C), u32(0xE94430), u32(0xE94434))
    for name, a in (("5MHz", 0xEF1FB4), ("8.75MHz", 0xEF2050), ("10MHz", 0xEF20EC), ("7MHz", 0xEF2188)):
        print("  record %s @%#x:" % (name, a), [u32(a + 4 * i) for i in range(0, 14)])
    print("  df=10937 @0xef1fdc..:", u32(0xEF1FDC), " 9766 @0xef2078:", u32(0xEF2078))


if __name__ == "__main__":
    band_plan(); classifier(); cal_bins(); numerology()
