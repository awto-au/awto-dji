#!/usr/bin/env python3
"""Decrypt and unpack an m0800 (DaVinci DM36x video-encoder) firmware module.

Password/cipher is DJI's own, publicly documented by the o-gs/dji-firmware-tools
wiki ("Firmware m0800" page, "Structure" section) since at least 2021 - this
script just reproduces that locally against this repo's firmware images.
Scope (CLAUDE.md): static analysis only. Untrusted firmware bytes; this script
decrypts/unpacks but never executes anything from the extracted tree.

Usage: python3 -I scripts/re/m0800_decrypt.py <path/to/*_m0800.bin> [out_dir]
Output: <out_dir>/dji/... (extracted tree) ; tmp/logs/m0800_decrypt.log
Default out_dir: tmp/air/<stem>_decrypted/
"""
import os
import subprocess
import sys
import tarfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from _log import log, REPO  # noqa: E402

PASSWORD = "Dji123456"  # W: o-gs/dji-firmware-tools wiki, "Firmware m0800" page


def decrypt(src: str, out_dir: str) -> str:
    with open(src, "rb") as fh:
        head = fh.read(8)
    if head != b"Salted__":
        raise SystemExit(f"{src}: no 'Salted__' OpenSSL header, not an m0800-style blob")
    os.makedirs(out_dir, exist_ok=True)
    tgz = os.path.join(out_dir, "decrypted.tar.gz")
    cmd = ["openssl", "enc", "-d", "-des3", "-md", "md5", "-k", PASSWORD,
           "-in", src, "-out", tgz]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        log(f"openssl decrypt FAILED for {src}: {r.stderr.strip()}", level="ERROR")
        raise SystemExit(1)
    log(f"decrypted {src} -> {tgz}")
    return tgz


def extract(tgz: str, out_dir: str) -> list:
    names = []
    with tarfile.open(tgz, "r:gz") as tf:
        tf.extractall(out_dir, filter="data")  # data filter: refuses abs paths/symlink escapes
        names = tf.getnames()
    log(f"extracted {len(names)} entries from {tgz} into {out_dir}")
    return names


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    src = os.path.abspath(sys.argv[1])
    stem = os.path.splitext(os.path.basename(src))[0]
    out_dir = sys.argv[2] if len(sys.argv) > 2 else os.path.join(REPO, "tmp", "air", f"{stem}_decrypted")
    tgz = decrypt(src, out_dir)
    names = extract(tgz, out_dir)
    for n in sorted(names):
        print(n)
    log(f"done: {src} -> {out_dir} ({len(names)} files)")


if __name__ == "__main__":
    main()
