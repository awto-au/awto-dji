#!/usr/bin/env python3
"""Find literal-pool xrefs to strings in the FC module (m0306) and disassemble around them.

Usage: fc_usb_xrefs.py <m0306.bin> <string> [<string> ...]   (image base 0x8020000, Thumb-2)
Log: tmp/logs/fc_usb_xrefs.log
"""
import os, struct, subprocess, sys
import capstone

BASE = 0x8020000
BEFORE, AFTER = 0x60, 0x60  # bytes of disassembly around each referencing literal


def repo():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def main():
    data = open(sys.argv[1], "rb").read()
    log_path = os.path.join(repo(), "tmp", "logs", "fc_usb_xrefs.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lf = open(log_path, "w")

    def out(s=""):
        print(s); lf.write(s + "\n")

    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB | capstone.CS_MODE_MCLASS)
    for needle in sys.argv[2:]:
        pos = data.find(needle.encode())
        out(f"== {needle!r} at file 0x{pos:x} (addr 0x{BASE + pos:x})")
        if pos < 0:
            continue
        addr = struct.pack("<I", BASE + pos)
        i = data.find(addr)
        while i >= 0:
            out(f"-- literal ref at 0x{BASE + i:x}")
            start = max(0, i - BEFORE) & ~1
            for ins in md.disasm(data[start:i + AFTER], BASE + start):
                out(f"  {ins.address:08x}: {ins.mnemonic} {ins.op_str}")
            i = data.find(addr, i + 1)


if __name__ == "__main__":
    main()
