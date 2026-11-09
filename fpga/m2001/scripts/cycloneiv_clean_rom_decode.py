#!/usr/bin/env python3.15t
"""Decode every M9K with non-zero init in the image lift -> a deterministic shape fact sheet (#89 step 8, #90).

For each ROM: reachable window (address bits tied to a constant shrink it), field decomposition
(the word split into equal sub-fields), and a battery of deterministic descriptors per field +
cross-field. Shapes are V (read straight from the ROM contents); the role hint is I/U.

Descriptors: const | few-valued (<=8 distinct) | linear ramp | tone (A cos+phi, rms<=2% of A) |
gf_log/antilog perm | bit-reversal perm | mirror-pair (field j == -field k, i.e. a packed (A,-A)
butterfly/twiddle word). Anything not matched is reported with its range + monotonicity so a human
can judge (e.g. a quarter-wave amplitude table that is not a uniform-frequency tone).

  python3.15t fpga/m2001/scripts/cycloneiv_clean_rom_decode.py [--nl tmp/image_sim_dji_push/nl.pkl]
Outputs: tmp/cycloneiv_clean/rom_decode.json + a markdown table on stdout. Log tmp/logs/cycloneiv_clean_rom_decode.log.
"""
import argparse
import json
import logging
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO, DJI  # noqa: E402  (REPO = pluribus engine checkout)
OUT = os.path.join(REPO, "tmp", "cycloneiv_clean")
RG = os.path.join(OUT, "regions")
log = logging.getLogger("rom_decode")

TONE_RMS = 0.02        # a field is a clean tone when the best A cos(2 pi k n/N + phi) + c fits within 2% of A
RAMP_R = 0.9995        # linear-ramp Pearson r threshold


def signed(v, w):
    return v - (1 << w) if (v >> (w - 1)) & 1 else v


def window(m):
    """ROM words the read address can reach + which address bits are tied."""
    init = list(m.get("init") or [])
    ab = m.get("raddr") or m.get("addr") or []
    fixed = {i: int(b[-1]) for i, b in enumerate(ab) if b in ("1'b0", "1'b1")}
    if not fixed:
        return init, len(ab), []
    win = [v for i, v in enumerate(init) if all(((i >> b) & 1) == val for b, val in fixed.items())]
    return win, len(ab), sorted(fixed)


def field_split(W):
    for f in sorted({W, 18, 16, 12, 10, 9, 8} - {0}, reverse=True):
        if f and f <= W and W % f == 0:
            for j in range(W // f):
                yield f"f[{j * f + f - 1}:{j * f}]" if f != W else "word", f, j


def tone_fit(x):
    n = len(x); t = np.arange(n)
    p = np.abs(np.fft.rfft(x - x.mean())); k0 = int(np.argmax(p[1:]) + 1) if len(p) > 2 else 1
    best = None
    for k in np.linspace(max(0.25, k0 - 1.5), k0 + 1.5, 121):
        M = np.column_stack([np.cos(2 * np.pi * k * t / n), np.sin(2 * np.pi * k * t / n), np.ones(n)])
        coef, *_ = np.linalg.lstsq(M, x, rcond=None)
        A = float(np.hypot(coef[0], coef[1]))
        if A < 1e-9:
            continue
        rms = float(np.sqrt(np.mean((M @ coef - x) ** 2))) / A
        if best is None or rms < best[0]:
            best = (rms, A, n / k)
    return best


def perm_descr(words, A):
    """gf_log / bit-reversal permutation checks on the full word sequence (depth 2^A)."""
    out = []
    if words and all(w >= 0 for w in words):
        m = max(words).bit_length()
        seq = words[:(1 << m) - 1]
        if 3 <= m <= 16 and sorted(seq) == list(range(1, 1 << m)):
            out.append(f"gf_log/antilog perm of 1..2^{m}-1")
    if A and len(words) == (1 << A):
        if all(words[i] == int(format(i, f"0{A}b")[::-1], 2) for i in range(len(words))):
            out.append("bit-reversal permutation")
    return out


def modular_ramp(raw, f):
    """A phase-accumulator ramp wraps mod 2^f, so it is not linear in raw value. Detect a near-constant
    step: >=90% of consecutive (signed) differences within +-1 of the median step. -> step, else None."""
    mod = 1 << f
    dd = np.array([((raw[i + 1] - raw[i]) % mod) for i in range(len(raw) - 1)], dtype=float)
    dd = np.where(dd > mod // 2, dd - mod, dd)          # minimal signed residue
    med = float(np.median(dd))
    if abs(med) < 0.5 or np.mean(np.abs(dd - med) <= 1) < 0.9:
        return None
    return med


def field_descr(raw, f):
    """Deterministic descriptors for one field view. Returns (list[str], signed-array)."""
    d, xs = [], np.array([signed(v, f) for v in raw], dtype=float)
    ds = len(set(raw))
    if ds == 1:
        return [f"const {raw[0]}"], xs
    if ds <= 8:
        return [f"few-valued {sorted(set(raw))}"], xs
    idx = np.arange(len(xs))
    if np.ptp(xs) > 0:
        r = float(np.corrcoef(idx, xs)[0, 1])
        if abs(r) > RAMP_R:
            d.append(f"linear ramp slope {float(np.polyfit(idx, xs, 1)[0]):.3g} r={r:.4f}")
    if not d:
        step = modular_ramp(raw, f)
        if step is not None:
            d.append(f"modular ramp step {step:.3g} (phase accumulator, period {2 ** f / abs(step):.0f} of 2^{f})")
    if len(xs) >= 16 and np.ptp(xs) > 0:
        fit = tone_fit(xs)
        if fit and fit[0] <= TONE_RMS:
            d.append(f"tone rms {100 * fit[0]:.2f}% A={fit[1]:.0f} period {fit[2]:.1f}")
    mono = bool(np.all(np.diff(xs) >= 0) or np.all(np.diff(xs) <= 0))
    fs = f" full-scale |A|=2^{f - 1}" if max(abs(xs.min()), abs(xs.max())) >= (1 << (f - 1)) - 2 else ""
    if not d:
        d.append(f"unclassified: {ds} distinct, signed[{xs.min():.0f},{xs.max():.0f}]{' monotone' if mono else ''}{fs}")
    return d, xs


def region_of(x, y):
    """Which #90 blob/region holds m9k_x_y, if a carve exists."""
    cell = f"m9k_{x}_{y}"
    for blob in ("802.16-rx", "802.16-tx"):
        p = os.path.join(RG, blob, "cell_region.json")
        if os.path.isfile(p):
            cr = json.load(open(p))
            if cell in cr:
                return f"{blob}/{cr[cell]}"
    return None


def decode(m):
    W = int(m.get("W") or 0)
    win, nab, tied = window(m)
    rec = dict(cell=f"m9k_{m['x']}_{m['y']}", x=m["x"], y=m["y"], W=W, depth=len(m.get("init") or []),
               addr_bits=nab, tied_bits=tied, window=len(win), distinct=len(set(win)),
               region=region_of(m["x"], m["y"]), fields=[])
    sgn = {}
    for label, f, j in field_split(W):
        raw = [(v >> (j * f)) & ((1 << f) - 1) for v in win]
        if len(set(raw)) < 3:
            continue
        descr, xs = field_descr(raw, f)
        descr += perm_descr(raw, nab) if f == W else []
        rec["fields"].append(dict(field=label, bits=f, distinct=len(set(raw)), descr=descr))
        sgn[(f, j)] = xs
    # cross-field mirror pairs (A, -A): a packed butterfly/twiddle word
    keys = sorted(sgn)
    for a in range(len(keys)):
        for b in range(a + 1, len(keys)):
            if keys[a][0] != keys[b][0] or np.ptp(sgn[keys[a]]) == 0:
                continue
            match = float(np.mean(sgn[keys[a]] == -sgn[keys[b]]))   # tolerant: a full-scale sample saturates (−2^(f−1) has no positive mate)
            if match >= 0.95:
                rec.setdefault("cross", []).append(f"fields {keys[a]} and {keys[b]} are a mirror pair (A,-A), {100 * match:.0f}% exact")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", default=os.path.join(REPO, "tmp", "image_sim_dji_push", "nl.pkl"))
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    os.makedirs(OUT, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "cycloneiv_clean_rom_decode.log"))])
    sys.path.insert(0, REPO)
    nl = pickle.load(open(a.nl, "rb"))
    roms = [decode(m) for m in sorted((m for m in nl.m9k if any(m.get("init") or [])), key=lambda m: (m["x"], m["y"]))]
    json.dump(roms, open(os.path.join(OUT, "rom_decode.json"), "w"), indent=1)
    log.info("M9K total %d; with non-zero init %d -> %s\n", len(nl.m9k), len(roms), os.path.join(OUT, "rom_decode.json"))
    log.info("| ROM | WxD | window | region | fields (deterministic shape) |")
    log.info("|---|---|---|---|---|")
    for r in roms:
        fd = "; ".join(f"{f['field']}{f['bits']}b: {', '.join(f['descr'])}" for f in r["fields"])
        if r.get("cross"):
            fd += " || " + "; ".join(r["cross"])
        log.info("| %s | %dx%d | %d | %s | %s |", r["cell"], r["W"], r["depth"], r["window"], r["region"] or "-", fd)


if __name__ == "__main__":
    main()
