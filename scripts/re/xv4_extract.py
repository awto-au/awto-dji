#!/usr/bin/env python3
"""Minimal DJI xV4 firmware-container reader: list modules, optionally extract some.

Header: magic 0x12345678 at 0, entry count u16 at 0x2c, 0x34-byte entries from 0x40:
  u8 target (module = target & 0x1f, subtype = target >> 5), 3 pad bytes,
  u32 version, u32 data offset, u32 data length, u32 alloc length, md5[16], 2nd hash[16].
Module names follow dji-firmware-tools ("m%02d%02d" % (module, subtype)).

Usage:  python3 scripts/re/xv4_extract.py CONTAINER.bin [OUTDIR [m0900 ...]]
"""
import hashlib
import os
import struct
import sys


def main():
    data = open(sys.argv[1], "rb").read()
    outdir = sys.argv[2] if len(sys.argv) > 2 else None
    want = set(sys.argv[3:])
    assert struct.unpack_from("<I", data, 0)[0] == 0x12345678, "not an xV4 container"
    count = struct.unpack_from("<H", data, 0x2C)[0]
    prefix = os.path.splitext(os.path.basename(sys.argv[1]))[0]
    for n in range(count):
        e = 0x40 + n * 0x34
        target = data[e]
        _ver, off, length, _alloc = struct.unpack_from("<IIII", data, e + 4)
        name = "m%02d%02d" % (target & 0x1F, target >> 5)
        blob = data[off:off + length]
        print(f"{name}  off {off:#010x}  len {length:>9}  sha256 {hashlib.sha256(blob).hexdigest()}")
        if outdir and (not want or name in want):
            with open(os.path.join(outdir, f"{prefix}_{name}.bin"), "wb") as f:
                f.write(blob)


if __name__ == "__main__":
    main()
