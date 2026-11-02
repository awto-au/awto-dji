#!/usr/bin/env python3
"""Verify the load base of the m0306 image (STM32F427 flight controller app, P3X_FW_V01.11.0020_m0306.bin). Issues #40, #83.

Method: for each candidate base, count
  - vector-table words (offset 4..0xa8) that are odd, in-image and start like a handler,
  - odd 32-bit literals anywhere in the image that point inside it, and how many land on a
    Thumb `push {..,lr}` (0xB5xx / 0xE92D with LR) = real function start,
  - the halfwords at the Reset_Handler file offset (classic `ldr r0,[pc,#n]; blx r0`).
A right base gives a hit-rate far above wrong bases. Result: see log (declared 0x08020000).
Importable: assert_base() is the gate used by m0306_ghidra_names.py.
Log: ./tmp/logs/m0306_base_check.log
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0306.bin"
DECLARED_BASE = 0x08020000
CANDIDATES = (0x08020000, 0x08000000, 0x08004000, 0x08008000, 0x08010000, 0x08040000)
MIN_RATIO = 0.20  # declared base must reach this push-start ratio (measured 0.27; wrong bases <= 0.01)


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
    for i in range(1, 48):
        v = struct.unpack_from("<I", data, 4 * i)[0]
        if v == 0:
            continue
        vec_total += 1
        t = (v & ~1) - base
        if (v & 1) and 0 <= t < n - 4 and plausible_entry(data, t):
            vec_ok += 1
    lit_total = lit_push = 0
    for off in range(0xC0, n - 3, 4):
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
    """m0306.tsv rows (addr name note source) must be in-image code; data/params TSV addresses in image or SRAM."""
    sym = REPO / "docs" / "symbols"
    n = ok = 0
    odd = []
    for line in (sym / "m0306.tsv").read_text(encoding="utf-8").splitlines()[1:]:
        f = line.split("\t")
        if len(f) < 2 or not f[0].startswith("0x"):
            continue
        a = int(f[0], 16)
        n += 1
        off = a - DECLARED_BASE
        if not 0 <= off < len(data) - 4:
            odd.append(f"{f[0]} {f[1]} out of image")
            continue
        h = struct.unpack_from("<H", data, off)[0]
        if plausible_entry(data, off) or h >> 11 in (0x1C, 0x1E, 0x1D):
            ok += 1
        else:
            odd.append(f"{f[0]} {f[1]} first halfword {h:04x}")
    log(f"m0306.tsv rows: {n}, plausible code entries {ok}, other {len(odd)}")
    for o in odd[:20]:
        log("  " + o)
    bad = 0
    for name in ("m0306-data.tsv", "m0306-params.tsv", "m0306-vectors.tsv", "m0306-duml-handlers.tsv", "m0306-names.tsv"):
        rows = 0
        for line in (sym / name).read_text(encoding="utf-8").splitlines()[1:]:
            f = line.split("\t")
            if len(f) < 2 or not f[0].startswith("0x"):
                continue
            a = int(f[0], 16)
            rows += 1
            in_flash = DECLARED_BASE <= a < DECLARED_BASE + len(data)
            in_sram = 0x20000000 <= a < 0x20030000 or 0x10000000 <= a < 0x10010000
            if not (in_flash or in_sram):
                bad += 1
                log(f"  {name}: {f[0]} {f[1]} outside flash image and SRAM")
        log(f"{name}: {rows} rows checked")
    if bad or any("out of image" in o for o in odd):
        raise RuntimeError("TSV addresses inconsistent with the declared base")


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
