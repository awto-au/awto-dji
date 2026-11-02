#!/usr/bin/env python3
"""Quick capstone disassembly of the extracted Intel i6050 final-memory regions (tmp/intel-wimax/regions.tsv).
Usage: intel_wimax_dis.py <addr> <count> [arm|thumb] [--hexdump]   Low addresses (<0x7720) read the 0x740000 region.
"""
import sys, struct
from pathlib import Path
import capstone

D = Path("tmp/intel-wimax")


def mem(addr, n):
    for line in (D / "regions.tsv").read_text().splitlines()[1:]:
        f, a, s = line.split("\t")
        a, s = int(a, 16), int(s, 16)
        if a == 0x740000 and addr < s:  # alias at 0 (I)
            a = 0
        if a <= addr < a + s:
            return (D / f).read_bytes()[addr - a:addr - a + n]
    raise SystemExit("addr not in any region")


def main():
    addr, cnt = int(sys.argv[1], 16), int(sys.argv[2])
    mode = sys.argv[3] if len(sys.argv) > 3 and not sys.argv[3].startswith("-") else "thumb"
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB if mode == "thumb" else capstone.CS_MODE_ARM)
    md.detail = False
    data = mem(addr, cnt * 4)
    n = 0
    for i in md.disasm(data, addr):
        print("%06x: %-8s %s" % (i.address, i.mnemonic, i.op_str))
        n += 1
        if n >= cnt:
            break


main()
