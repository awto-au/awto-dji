#!/usr/bin/env python3
"""Issue #84 Q2/Q6: crypto constants in m0900 / m1400 / m0306 and the m0306 DUML dispatch table.

1. Constant scan (LE and BE words): AES S-box/Te0, SHA-1/256/512, MD5, secp256r1/secp256k1/curve25519 primes,
   P-256 b, CRC32 table, DES S1 (nibble bytes), 3DES link constant. Negative result is the finding for most.
2. m0306: decode the (funcptr, key=(cmd<<8)|cmdset) table at 0x080ab440..0x080ab644 (docs/fc-usb-duml.md) and list
   the cmdsets present; check cmdset 0x09 absence.
Usage: session_key_crypto_scan.py   Log: ./tmp/logs/session_key_crypto_scan.log
"""
from __future__ import annotations

import bisect
import re
import struct
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

U = REPO / "firmware" / "unpacked"
G = REPO / "re" / "ghidra-projects"
IMAGES = {
    "m0900": (REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin", 0x08008000, G / "m0900_radio" / "m0900_dump.txt"),
    "m1400": (U / "C1_FW_V01.06.0000" / "C1_FW_V01.06.0000_m1400.bin", 0xA000, G / "m1400_radio" / "m1400_dump.txt"),
    "m0306": (U / "P3X_FW_V01.11.0020_m0306.bin", 0x08020000, G / "m0306_flight_controller" / "m0306_dump.txt"),
}
W32 = {
    "AES Te0": 0xC66363A5, "SHA256 K0,K1": (0x428A2F98, 0x71374491), "SHA1 K0": 0x5A827999,
    "SHA1 H0": 0x67452301, "SHA512 K0": (0x428A2F98, 0xD728AE22), "MD5 T0": 0xD76AA478,
    "P-256 prime": (0xFFFFFFFF, 0x00000001, 0, 0, 0), "P-256 b": 0x5AC635D8, "secp256k1 prime": 0xFFFFFC2F,
    "CRC32 tab": (0, 0x77073096, 0xEE0E612C), "TEA delta": 0x9E3779B9,
}
BYTES = {
    "AES sbox": bytes.fromhex("637c777bf26b6fc5"), "AES inv sbox": bytes.fromhex("52096ad53036a538"),
    "curve25519 prime LE": bytes.fromhex("edffffffffffffff"), "DES S1 nibbles": bytes([14, 4, 13, 1, 2, 15, 11, 8]),
    "3DES link const": bytes.fromhex("7865548762233647"), "RSA e=65537 BE": bytes.fromhex("00010001"),
    "ASN.1 RSA/SPKI 30 82": bytes.fromhex("30820122"),
}
HDR = re.compile(r"^---- (\S+) @ ([0-9a-fA-F]+) ----$")


def fidx(dump: Path):
    p = sorted((int(m.group(2), 16), m.group(1)) for m in map(HDR.match, dump.read_text(errors="replace").splitlines()) if m)
    return [a for a, _ in p], [n for _, n in p]


def where(idx, addr):
    k = bisect.bisect_right(idx[0], addr) - 1
    return idx[1][k] if k >= 0 else "?"


def finds(d: bytes, pat: bytes):
    i = d.find(pat)
    while i != -1:
        yield i
        i = d.find(pat, i + 1)


def main() -> int:
    for name, (fw, base, dump) in IMAGES.items():
        d = fw.read_bytes()
        idx = fidx(dump)
        log(f"== {name} ({len(d)} B, base {base:#x})")
        pats = dict(BYTES)
        for k, v in W32.items():
            v = v if isinstance(v, tuple) else (v,)
            pats[k + " LE"] = struct.pack("<%dI" % len(v), *v)
            pats[k + " BE"] = struct.pack(">%dI" % len(v), *v)
        for k, pat in pats.items():
            hits = list(finds(d, pat))
            if hits:
                for h in hits[:4]:
                    log(f"  HIT {k}: off={h:#x} addr={base + h:#x} in {where(idx, base + h)}")
            else:
                log(f"  none {k}")
    fw, base, _ = IMAGES["m0306"]
    d = fw.read_bytes()
    start, end = 0x080AB440, 0x080AB644
    cs = Counter()
    ents = []
    for a in range(start, end, 8):
        ptr, key = struct.unpack_from("<IH", d, a - base)
        ents.append((a, ptr, key & 0xFF, key >> 8))
        cs[key & 0xFF] += 1
    log(f"m0306 dispatch table {start:#x}..{end:#x}: {len(ents)} entries, cmdset histogram "
        + ", ".join(f"{k:#04x}:{v}" for k, v in sorted(cs.items())))
    log(f"m0306 cmdset 0x09 entries: {cs.get(9, 0)}")
    for a, ptr, s, c in ents:
        if s != 3:
            log(f"  non-FLYC entry {a:#x}: cmdset={s:#x} cmd={c:#x} fn={ptr:#x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
