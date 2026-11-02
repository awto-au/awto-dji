#!/usr/bin/env python3
"""Generic small-integer ratio matcher for reversing work: a measured/decoded value is often
exactly (or within a tight tolerance window of) base * n/d for small integers n, d - the m2001
FPGA lift repeatedly found register/clock values off by an exact x2 or x4 from the "obvious"
reading. This is that check, made reusable for any module (MCU, FPGA, PHY) instead of
re-deriving it by hand each time.

Usage (library):
    from value_scale_match import find_ratios
    find_ratios(704, [512, 1024, 2048], max_den=64, tol=0.0)   # exact fractions only
    find_ratios(11.2e6, [10e6], max_den=100, tol=1e-6)         # near-exact, float tolerance

Usage (CLI): value_scale_match.py <value> <base1> [base2 ...] [--max-den N] [--tol T]
Log: ./tmp/logs/value_scale_match.log
"""
from __future__ import annotations

import argparse
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402


def find_ratios(value: float, bases: list[float], max_den: int = 64, tol: float = 1e-9) -> list[dict]:
    """For each base, find small n/d such that base*n/d ~= value within tol (relative).
    Returns matches sorted by (den, num) i.e. simplest fraction first."""
    out = []
    for base in bases:
        if base == 0:
            continue
        r = Fraction(value, base).limit_denominator(max_den) if isinstance(value, Fraction) else \
            Fraction(value / base).limit_denominator(max_den)
        got = base * r.numerator / r.denominator
        err = abs(got - value) / abs(value) if value else abs(got - value)
        if err <= tol or tol == 0.0 and value == got:
            out.append({"base": base, "ratio": f"{r.numerator}/{r.denominator}", "num": r.numerator,
                        "den": r.denominator, "reconstructed": got, "rel_err": err})
    return sorted(out, key=lambda m: (m["den"], m["num"]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("value", type=float)
    ap.add_argument("bases", type=float, nargs="+")
    ap.add_argument("--max-den", type=int, default=64)
    ap.add_argument("--tol", type=float, default=1e-9)
    a = ap.parse_args()
    hits = find_ratios(a.value, a.bases, a.max_den, a.tol)
    if not hits:
        log(f"{a.value}: no ratio <= 1/{a.max_den} matches any base within tol {a.tol}")
        return 1
    for h in hits:
        log(f"{a.value} = {h['base']} * {h['ratio']} (rel_err={h['rel_err']:.2e})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
