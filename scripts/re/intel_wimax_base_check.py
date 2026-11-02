#!/usr/bin/env python3
"""Verify load base of Intel i6050 code segments: count 32-bit literals that point into the segment
and land on a function prologue (ARM push/stmfd lr, Thumb push {..,lr}), for the declared base and shifted bases.
A right base gives a hit-rate far above shifted bases. Reads segments from ./tmp/intel-wimax (see intel_wimax_sbcf.py --out).
Log: ./tmp/logs/intel_wimax_base_check.log
"""
import struct, sys
from pathlib import Path

SEGS = {"seg07_dc0000.bin": 0xDC0000, "seg13_e80000.bin": 0xE80000, "seg11_740000.bin": 0x740000}


def arm_prologue(w):  # stmfd sp!,{...,lr}
    return (w & 0xFFFF0000) == 0xE92D0000 and (w & 0x4000)


def thumb_prologue(h):  # push {..,lr}
    return (h & 0xFF00) == 0xB500


def score(data, base, d):
    n = len(data)
    hits_a = hits_t = tot = 0
    for off in range(0, n - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        t = v - (base + d)
        if v & 1:
            t = (v & ~1) - (base + d)
        if 0 <= t < n - 4:
            tot += 1
            if not (v & 1) and t % 4 == 0 and arm_prologue(struct.unpack_from("<I", data, t)[0]):
                hits_a += 1
            elif (v & 1) and thumb_prologue(struct.unpack_from("<H", data, t)[0]):
                hits_t += 1
    return tot, hits_a, hits_t


def main(d="tmp/intel-wimax"):
    for name, base in SEGS.items():
        data = Path(d, name).read_bytes()
        print("== %s declared base 0x%x size 0x%x" % (name, base, len(data)))
        for delta in (0, 0x1000, -0x1000, 0x10000, -0x10000, 0x4, 0x100):
            tot, a, t = score(data, base, delta)
            print("  base 0x%06x  in-range literals %6d  ARM-prologue hits %5d  Thumb-prologue hits %5d%s" % (
                base + delta, tot, a, t, "  <- declared" if delta == 0 else ""))


if __name__ == "__main__":
    main(*sys.argv[1:])
