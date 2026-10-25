#!/usr/bin/env python3
"""Decrypt a DJI xV4 module with encrypt_type=1 (module-level AES-128).

Scheme (from o-gs/dji-firmware-tools dji_xv4_fwcon.py, public): AES-128-CBC, IV = 0, the cipher
re-initialised every 256 bytes (each 256 B block is an independent CBC run from IV 0). Key is
DJI's public module key. Output is truncated to the entry's decrypted_len and its MD5 is checked
against the entry's decrypted_md5, so a wrong key/scheme fails loudly.

This reads the key as a constant and does the crypto itself; it does not execute the DJI tool.

Usage:  python3 scripts/re/xv4_decrypt.py CONTAINER.bin MODULE OUT.bin   (e.g. MODULE = m0306)
Container hashes: docs/data-manifest.md.
"""
import hashlib
import struct
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = bytes([0x96, 0x70, 0x9A, 0xD3, 0x26, 0x67, 0x4A, 0xC3, 0x82, 0xB6, 0x69, 0x27, 0xE6, 0xD8, 0x84, 0x21])
IV = bytes(16)


def decrypt(ciphertext):
    out = bytearray()
    for p in range(0, len(ciphertext), 256):
        blk = ciphertext[p:p + 256]
        if len(blk) % 16:
            blk = blk + bytes(16 - len(blk) % 16)
        dec = Cipher(algorithms.AES(KEY), modes.CBC(IV)).decryptor()
        out += dec.update(blk) + dec.finalize()
    return bytes(out)


def main():
    container, want, outpath = sys.argv[1], sys.argv[2], sys.argv[3]
    d = open(container, "rb").read()
    n = struct.unpack_from("<H", d, 0x2C)[0]
    for i in range(n):
        o = 0x40 + i * 0x34
        tid = d[o]
        name = "m%02d%02d" % (tid & 0x1F, tid >> 5)
        if name != want:
            continue
        spcoding = d[o + 1]
        enc = (spcoding >> 4) & 0x0F
        _ver, off, slen, dlen = struct.unpack_from("<IIII", d, o + 4)
        dmd5 = d[o + 0x24:o + 0x34]
        print(f"{name}: encrypt_type {enc}, stored_len {slen}, decrypted_len {dlen}")
        payload = d[off:off + slen]
        pt = decrypt(payload)[:dlen] if enc == 1 else payload[:dlen]
        ok = hashlib.md5(pt).digest() == dmd5
        print(f"  decrypted_md5 {dmd5.hex()}  computed {hashlib.md5(pt).hexdigest()}  {'OK' if ok else 'MISMATCH'}")
        if not ok and enc == 1:
            sys.exit("decrypt failed: MD5 mismatch (wrong key/scheme or not encrypt_type 1)")
        open(outpath, "wb").write(pt)
        sp, reset = struct.unpack_from("<II", pt, 0)
        print(f"  wrote {outpath} ({len(pt)} B); vector SP {sp:#x} reset {reset:#x}")
        return
    sys.exit(f"module {want} not found in container")


if __name__ == "__main__":
    main()
