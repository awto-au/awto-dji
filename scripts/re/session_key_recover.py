#!/usr/bin/env python3
"""Issue #84: recover m0900/m1400 link_xor_key by brute-forcing the <=72000-seed space against a
captured scrambled frame, using fpga_link_payload_descramble's own CRC16 check as the oracle.

Needs one captured frame (bytes 1..0x37 of the scrambled payload, 0x37 B) from the RADIO link - no
capture exists in this repo yet (checked: captures/ holds only USB-wired DUML, no radio/OFDM data).
Until one exists this is a ready tool, not a result; do not report a "recovered key" without a real
capture behind it.

Derivation (all V, re/ghidra-projects/m0900_radio, docs/session-key-trace.md): seed = SysTick VAL
(0..0x1193f) -> srand/rand (session_key_prng.key_for_seed) -> 24-byte radio_session_key -> 3DES-ECB
encrypt the constant 78 65 54 87 62 23 36 47 -> 8-byte link_xor_key, repeated to cover 0x37 bytes.
Oracle: XOR the frame with the candidate key, CRC16 (seed 0x55aa, scripts/re/duml_proto.py) over the
unscrambled bytes must match the frame's trailing 2-byte CRC (two-stage per the symbol note; this
checks the inner stage only - see docs/session-key-trace.md if the outer stage needs modelling too).

Usage: session_key_recover.py --frame-hex <0x37-or-more-byte hex, includes trailing CRC16>
       session_key_recover.py --frame-file <path, raw bytes>
Log: ./tmp/logs/session_key_recover.log
"""
from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from session_key_prng import key_for_seed, pool  # noqa: E402
from duml_proto import crc16  # noqa: E402

try:
    from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
except ImportError:  # cryptography < 48
    from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
from cryptography.hazmat.primitives.ciphers import Cipher, modes

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
BASE = 0x08008000
CONST = bytes.fromhex("7865548762233647")
SCRAMBLE_LEN = 0x37  # bytes 1..0x37 of the frame, per fpga_link_payload_descramble (0x0800e008)
CRC_SEED = 0x55AA


def link_xor_key(seed: int, mult: int, add: int) -> bytes:
    k24 = key_for_seed(seed, mult, add)
    enc = Cipher(TripleDES(k24), modes.ECB()).encryptor()
    return enc.update(CONST) + enc.finalize()


def try_seed(seed: int, mult: int, add: int, frame: bytes) -> tuple[bytes, bytes] | None:
    key = link_xor_key(seed, mult, add)
    xk = (key * ((len(frame) // 8) + 1))[: len(frame)]
    out = bytes(a ^ b for a, b in zip(frame, xk))
    if len(out) < 2:
        return None
    if crc16(CRC_SEED, out[:-2]) == struct.unpack_from("<H", out, len(out) - 2)[0]:
        return key, out
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--frame-hex")
    g.add_argument("--frame-file")
    a = ap.parse_args()
    frame = bytes.fromhex(a.frame_hex) if a.frame_hex else Path(a.frame_file).read_bytes()
    if len(frame) < SCRAMBLE_LEN:
        log(f"frame is {len(frame)} B, need >= {SCRAMBLE_LEN} B (bytes 1..0x37) - not a usable capture")
        return 2
    d = FW.read_bytes()
    add, mult, load = pool(d, 0x0801280C), pool(d, 0x08012810), pool(d, 0x0800C240)
    log(f"brute-forcing {load + 1} seeds against a {len(frame)}-B frame (CRC16 oracle, seed {CRC_SEED:#x})")
    hits = []
    for seed in range(load + 1):
        hit = try_seed(seed, mult, add, frame)
        if hit:
            hits.append((seed, hit[0], hit[1]))
            log(f"CRC16 match: seed={seed:#x} link_xor_key={hit[0].hex()}")
    if not hits:
        log("no seed's key passes the CRC16 oracle - frame may not be from this scheme, or not aligned")
        return 1
    if len(hits) > 1:
        log(f"WARNING: {len(hits)} seeds matched - CRC16 alone may not disambiguate; check the outer CRC stage too")
    return 0


if __name__ == "__main__":
    sys.exit(main())
