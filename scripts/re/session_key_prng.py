#!/usr/bin/env python3
"""Issue #84 Q4: model of m0900 srand 0x080127d8 / rand 0x080081cc and the session-key seed space.

Constants read from the image literal pools (base 0x08008000): ring P=0x200027ec (ring = P-0x7c, 55 words),
srand add=0x66d619e1 (pool 0x0801280c), mult=0x10dcd (pool 0x08012810), SysTick LOAD=0x1193f (pool 0x0800c240).
Model (from decompile, I - not run on firmware): srand fills ring[54..0] with s+(s>>16), s=s*mult+add;
rand: x=ring[B]+ring[A]; ring[B]=x; A,B advance mod 55 (A starts 31, B starts 0); byte = x & 0xff.
radio_session_key_init takes 24 bytes (3 x 8) after srand(SysTick VAL); VAL in 0..LOAD.
Output: number of distinct 24-byte keys over all seeds, and distinct 8-byte link_xor_key candidates need 3DES (not done here).
Usage: session_key_prng.py   Log: ./tmp/logs/session_key_prng.log
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
BASE = 0x08008000
M32 = 0xFFFFFFFF


def pool(d: bytes, addr: int) -> int:
    return struct.unpack_from("<I", d, addr - BASE)[0]


def key_for_seed(seed: int, mult: int, add: int) -> bytes:
    ring = [0] * 55
    s = seed & M32
    for i in range(54, -1, -1):
        ring[i] = (s + (s >> 16)) & M32
        s = (s * mult + add) & M32
    a, b = 31, 0
    out = bytearray()
    for _ in range(24):
        x = (ring[b] + ring[a]) & M32
        ring[b] = x
        a = (a + 1) % 55
        b = (b + 1) % 55
        out.append(x & 0xFF)
    return bytes(out)


def main() -> int:
    d = FW.read_bytes()
    P, add, mult, load = pool(d, 0x08012808), pool(d, 0x0801280C), pool(d, 0x08012810), pool(d, 0x0800C240)
    log(f"P={P:#x} ring_base={P - 0x7C:#x} add={add:#x} mult={mult:#x} SysTick_LOAD={load:#x}")
    keys = {key_for_seed(v, mult, add) for v in range(load + 1)}
    log(f"seeds 0..{load}: {load + 1} values -> {len(keys)} distinct 24-byte keys")
    log(f"log2(seed space)={(load + 1).bit_length() - 1}.. ({load + 1} = 2^{__import__('math').log2(load + 1):.2f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
