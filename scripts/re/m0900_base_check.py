#!/usr/bin/env python3
"""Verify the load base of the m0900 image (STM32F103 app, P3X_FW_V01.11.0020_m0900.bin). Issue #83/#36.

Method: for each candidate base, count
  - vector-table words (offset 4..0xa8) that are odd, in-image and start like a handler,
  - odd 32-bit literals anywhere in the image that point inside it, and how many land on a
    Thumb `push {..,lr}` (0xB5xx / 0xE92D with LR) = real function start,
  - the halfwords at the Reset_Handler file offset (classic `ldr r0,[pc,#n]; blx r0`).
A right base gives a hit-rate far above wrong bases. Result: 0x08008000 (vectors 37/37, push-start ratio >0.5; wrong bases 0-2 vectors, 0.00).
Importable: assert_base() is the gate used by m0900_ghidra_names.py.
Log: ./tmp/logs/m0900_base_check.log
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
DECLARED_BASE = 0x08008000
CANDIDATES = (0x08008000, 0x08000000, 0x08004000, 0x08010000)
MIN_RATIO = 0.30  # declared base must reach this push-start ratio (measured 0.42; wrong bases <= 0.02)


def is_push_lr(data: bytes, off: int) -> bool:
    if off < 0 or off + 4 > len(data):
        return False
    h = struct.unpack_from("<H", data, off)[0]
    if (h & 0xFF00) == 0xB500:  # push {..,lr}
        return True
    if h == 0xE92D:  # push.w {..}; bit14 = lr
        return bool(struct.unpack_from("<H", data, off + 2)[0] & 0x4000)
    return False


def plausible_entry(data: bytes, off: int) -> bool:
    """Handler entry: push{..lr}, `b .` (0xE7FE), `bx lr`, `ldr r0,[pc,#n]` or `push {..}` without lr."""
    h = struct.unpack_from("<H", data, off)[0]
    return (is_push_lr(data, off) or h in (0xE7FE, 0x4770) or (h & 0xF800) == 0x4800
            or (h & 0xFF00) == 0xB400)


def score(data: bytes, base: int) -> dict:
    n = len(data)
    vec_total = vec_ok = 0
    for i in range(1, 43):
        v = struct.unpack_from("<I", data, 4 * i)[0]
        if v == 0:
            continue
        vec_total += 1
        t = (v & ~1) - base
        if (v & 1) and 0 <= t < n - 4 and plausible_entry(data, t):
            vec_ok += 1
    lit_total = lit_push = 0
    for off in range(0xAC, n - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        t = (v & ~1) - base
        if (v & 1) and 0 <= t < n and t % 2 == 0:
            lit_total += 1
            if is_push_lr(data, t):
                lit_push += 1
    reset = struct.unpack_from("<I", data, 4)[0]
    return {"base": base, "vec_ok": vec_ok, "vec_total": vec_total, "lit_total": lit_total,
            "lit_push": lit_push, "ratio": lit_push / lit_total if lit_total else 0.0, "reset": reset}


def reset_pattern(data: bytes) -> tuple[int, str]:
    """Halfwords at file offset (reset & 0x1fff...): reset - declared base, ldr r0,[pc,#n] = 0x48xx; blx r0 = 0x4780."""
    reset = struct.unpack_from("<I", data, 4)[0]
    off = (reset & ~1) - DECLARED_BASE
    h0, h1 = struct.unpack_from("<HH", data, off)
    ok = (h0 & 0xFF00) == 0x4800 and h1 == 0x4780
    return off, f"{h0:04x} {h1:04x} ({'ldr r0,[pc]; blx r0' if ok else 'NOT ldr/blx'})"


def report(data: bytes) -> dict[int, dict]:
    sha = __import__("hashlib").sha256(data).hexdigest()
    log(f"image {FW.name} size={len(data)} (0x{len(data):x}) sha256={sha[:16]}...")
    sp = struct.unpack_from("<I", data, 0)[0]
    log(f"vector[0] SP=0x{sp:08x}  vector[1] reset=0x{struct.unpack_from('<I', data, 4)[0]:08x}")
    out = {}
    for b in CANDIDATES:
        s = score(data, b)
        out[b] = s
        log(f"base 0x{b:08x}: vectors {s['vec_ok']}/{s['vec_total']} plausible entries; "
            f"odd literals {s['lit_total']}, push{{..lr}} starts {s['lit_push']} ({s['ratio']:.2f})"
            f"{'  <- declared' if b == DECLARED_BASE else ''}")
    off, txt = reset_pattern(data)
    log(f"Reset_Handler at file offset 0x{off:x} (base 0x{DECLARED_BASE:08x}): {txt}")
    return out


def check_tsv(data: bytes) -> None:
    """func rows of docs/symbols/m0900_V01.11.0020.tsv must lie in the image and start like code at base 0x08008000."""
    tsv = REPO / "docs" / "symbols" / "m0900_V01.11.0020.tsv"
    n = ok = out = 0
    odd = []
    for line in tsv.read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 3 or f[1] != "func":
            continue
        a = int(f[0], 16)
        n += 1
        off = a - DECLARED_BASE
        if not 0 <= off < len(data) - 4:
            out += 1
            odd.append(f"{f[0]} {f[2]} out of image")
        elif plausible_entry(data, off) or struct.unpack_from("<H", data, off)[0] >> 11 in (0x1C, 0x1E, 0x1D):
            ok += 1  # push, b ., bx lr, ldr pc-rel, push w/o lr, or 32-bit Thumb-2 prefix (e.g. push.w, b.w)
        else:
            odd.append(f"{f[0]} {f[2]} first halfword {struct.unpack_from('<H', data, off)[0]:04x}")
    log(f"TSV func rows: {n}, plausible entries {ok}, outside image {out}, other {len(odd)}")
    for o in odd[:20]:
        log("  " + o)
    if out:
        raise RuntimeError("TSV has func rows outside the image at the declared base")


def assert_base() -> None:
    """Gate: raise if the declared base is not clearly the best candidate."""
    data = FW.read_bytes()
    res = report(data)
    best = max(res.values(), key=lambda s: s["ratio"])
    if best["base"] != DECLARED_BASE or res[DECLARED_BASE]["ratio"] < MIN_RATIO:
        raise RuntimeError(f"base gate failed: declared 0x{DECLARED_BASE:08x}, best 0x{best['base']:08x}")
    check_tsv(data := FW.read_bytes())
    log("base gate OK")


if __name__ == "__main__":
    assert_base()
