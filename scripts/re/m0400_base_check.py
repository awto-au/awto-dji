#!/usr/bin/env python3
"""Verify the load base of the m0400 image (STM32F4 gimbal MCU, P3X_FW_V01.11.0020_m0400.bin). Issue #41.

Method (same as m0900_base_check.py, helpers imported from it):
  - vector-table words (slots 1..97) that are odd, in-image and start like a handler,
  - odd 32-bit literals past the table that point inside the image and land on a Thumb push{..,lr},
  - symbol-TSV func rows (docs/symbols/m0400.tsv) must lie in the image and start like code.
A right base scores far above wrong ones. Importable: assert_base() gates m0400_ghidra_names.py.
Log: ./tmp/logs/m0400_base_check.log
"""
from __future__ import annotations

import hashlib
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from m0900_base_check import plausible_entry, is_push_lr  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
TSV = REPO / "docs" / "symbols" / "m0400.tsv"
DECLARED_BASE = 0x08008000
CANDIDATES = (0x08008000, 0x08000000, 0x08004000, 0x08010000, 0x08020000, 0x08040000)
VEC_SLOTS = 98          # slots 1..97 are handler words (F4: 16 core + 82 IRQ)
VEC_END = 4 * VEC_SLOTS
MIN_RATIO = 0.30        # declared base push-start ratio floor


def score(data: bytes, base: int) -> dict:
    n = len(data)
    vec_total = vec_ok = 0
    for i in range(1, VEC_SLOTS):
        v = struct.unpack_from("<I", data, 4 * i)[0]
        if v == 0:
            continue
        vec_total += 1
        t = (v & ~1) - base
        if (v & 1) and 0 <= t < n - 4 and plausible_entry(data, t):
            vec_ok += 1
    lit_total = lit_push = 0
    for off in range(VEC_END, n - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        t = (v & ~1) - base
        if (v & 1) and 0 <= t < n and t % 2 == 0:
            lit_total += 1
            if is_push_lr(data, t):
                lit_push += 1
    return {"base": base, "vec_ok": vec_ok, "vec_total": vec_total, "lit_total": lit_total,
            "lit_push": lit_push, "ratio": lit_push / lit_total if lit_total else 0.0}


def report(data: bytes) -> dict[int, dict]:
    log(f"image {FW.name} size={len(data)} (0x{len(data):x}) sha256={hashlib.sha256(data).hexdigest()[:16]}...")
    sp, reset = struct.unpack_from("<II", data, 0)
    log(f"vector[0] SP=0x{sp:08x}  vector[1] reset=0x{reset:08x}  (reset file offset at declared base: 0x{(reset & ~1) - DECLARED_BASE:x})")
    out = {}
    for b in CANDIDATES:
        s = score(data, b)
        out[b] = s
        log(f"base 0x{b:08x}: vectors {s['vec_ok']}/{s['vec_total']} plausible entries; odd literals {s['lit_total']}, "
            f"push{{..lr}} starts {s['lit_push']} ({s['ratio']:.2f}){'  <- declared' if b == DECLARED_BASE else ''}")
    return out


def check_tsv(data: bytes) -> None:
    if not TSV.exists():
        log("no symbol TSV yet, skipping row check")
        return
    n = ok = 0
    odd = []
    for line in TSV.read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 3 or f[1] != "func":
            continue
        a = int(f[0], 16)
        n += 1
        off = a - DECLARED_BASE
        if not 0 <= off < len(data) - 4:
            odd.append(f"{f[0]} {f[2]} outside image")
            continue
        h = struct.unpack_from("<H", data, off)[0]
        if plausible_entry(data, off) or h >> 11 in (0x1C, 0x1D, 0x1E):
            ok += 1
        else:
            odd.append(f"{f[0]} {f[2]} first halfword {h:04x}")
    log(f"TSV func rows: {n}, plausible entries {ok}, other {len(odd)}")
    for o in odd[:20]:
        log("  " + o)
    if any("outside" in o for o in odd):
        raise RuntimeError("TSV has func rows outside the image at the declared base")


def assert_base() -> None:
    data = FW.read_bytes()
    res = report(data)
    best = max(res.values(), key=lambda s: s["ratio"])
    if best["base"] != DECLARED_BASE or res[DECLARED_BASE]["ratio"] < MIN_RATIO:
        raise RuntimeError(f"base gate failed: declared 0x{DECLARED_BASE:08x}, best 0x{best['base']:08x}")
    check_tsv(data)
    log("base gate OK")


if __name__ == "__main__":
    assert_base()
