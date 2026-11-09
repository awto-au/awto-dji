#!/usr/bin/env python3.15t
"""Trace how each init M9K is ADDRESSED and where its output goes (#89 step 8, #90).

Companion to cycloneiv_clean_rom_decode.py (which reads the stored shapes). This resolves the
addressing so a ROM's window can be judged quarter/half/full and its role narrowed:

  per ROM -> read-address pins (raddr/addr) + tie window; the driver of each address bit; a
  classification of the address source (pad-loaded index | carry-chain fold = conditional negate
  |x| | plain FF/counter); whether a shared carry-out touches only the address LUTs (so the sign
  does NOT reach the data path); and the output-data fanout (consumer kinds, and whether any output
  reaches another M9K address = an interleaver/permutation).

Deterministic, read-only. Shapes/edges reported are V; role names are I.

  python3.15t fpga/m2001/scripts/cycloneiv_clean_rom_addr_trace.py [--nl NL.pkl] [--cell m9k_36_82 ...]
Default: every M9K with non-zero init. Log tmp/logs/cycloneiv_clean_rom_addr_trace.log.
"""
import argparse
import collections
import logging
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO, DJI, BOARD  # noqa: E402
import cycloneiv_clean_partition as CP  # noqa: E402
log = logging.getLogger("rom_addr")


def cone_back(P, start, maxdepth=6):
    """Cells reached walking backward (ff.d -> driver, lut.pins) up to maxdepth. Returns the set of names."""
    seen, frontier = set(), list(start)
    for _ in range(maxdepth):
        nxt = []
        for c in frontier:
            if c in seen or not isinstance(c, str):
                continue
            seen.add(c)
            if c in P.ff:
                nxt.append(P.ff[c].get("d"))
            elif c in P.lut:
                nxt += P.lut[c].get("pins", [])
        frontier = [c for c in nxt if c and c not in seen]
    return seen


def addr_source(P, drivers):
    """Classify the address source from its driver LUTs/FFs. Returns (label, evidence). Edges are V;
    the fold reading is a CANDIDATE (a shared non-constant driver into most address LUTs) — the
    conditional-negate / |signed| conclusion needs the truth tables, which this does not decode."""
    cone = cone_back(P, drivers)
    pads = sorted(c for c in cone if isinstance(c, str) and c.startswith("pad_"))
    # a single non-constant signal feeding an input of (most) address-bit LUTs = a shared sign candidate
    dpins = collections.Counter()
    for d in drivers:
        dl = P.ff[d].get("d") if d in P.ff else d           # the LUT behind the address FF
        for p in (P.lut.get(dl, {}).get("pins", []) if dl in P.lut else []):
            if not str(p).startswith("1'b"):                # constants tie every LUT; they are not a sign
                dpins[p] += 1
    shared = [c for c, n in dpins.items() if n >= max(3, len(drivers) - 1)]
    if shared:
        return "candidate fold (shared driver into most address LUTs; truth tables NOT decoded)", f"shared {shared[:2]} into {len(drivers)} address LUTs"
    if pads:
        return "pad-loaded index register", f"pad(s) in address cone: {pads[:3]}"
    return "FF/LUT-driven (counter / accumulator; not resolved here)", f"drivers {drivers[:3]}"


def fanout_of(P, net):
    cons = P.fanout.get(net, [])
    kinds = collections.Counter(c[0] if isinstance(c, (list, tuple)) else str(c)[:3] for c in cons)
    hits_m9k_addr = any((isinstance(c, (list, tuple)) and c[0] == "m9k") for c in cons)
    return len(cons), dict(kinds), hits_m9k_addr


def trace(P, cell):
    x, y = (int(t) for t in cell.split("_")[1:3])
    m = P.m9k[(x, y)]
    use, tag = (m.get("raddr"), "raddr") if m.get("raddr") else (m.get("addr") or [], "addr")
    tied = {i: int(p[-1]) for i, p in enumerate(use) if str(p).startswith("1'b")}
    drivers = [p for p in use if not str(p).startswith("1'b")]
    W = int(m.get("W") or 0)
    depth = len(m.get("init") or [])
    window = [v for v in range(depth) if all(((v >> b) & 1) == val for b, val in tied.items())] if tied else list(range(depth))
    label, ev = addr_source(P, drivers)
    # output fanout
    out_bits, out_hit_addr = [], False
    for i in range(W):
        n, kinds, hit = fanout_of(P, f"{cell}_o[{i}]")
        if n:
            out_bits.append((i, n, kinds))
            out_hit_addr = out_hit_addr or hit
    log.info("\n=== %s  W=%d depth=%d  %s=%d bits, tied %s -> window %d words %s",
             cell, W, depth, tag, len(use), tied or "{}", len(window),
             f"[{min(window)}..{max(window)}]" if window else "")
    log.info("  address source: %s  (%s)", label, ev)
    log.info("  address bit drivers: %s", drivers)
    log.info("  output bits with fanout: %s", [(i, n) for i, n, _ in out_bits])
    log.info("  output reaches an M9K address (interleaver signature): %s", out_hit_addr)
    return dict(cell=cell, W=W, depth=depth, addr_tag=tag, tied=tied, window=[min(window), max(window)] if window else [],
                addr_source=label, addr_evidence=ev, drivers=drivers,
                out_bits=[[i, n] for i, n, _ in out_bits], out_reaches_m9k_addr=out_hit_addr)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", default=os.path.join(REPO, "tmp", "image_sim_dji_push", "nl.pkl"))
    ap.add_argument("--cell", action="append", help="m9k_X_Y (default: every M9K with non-zero init)")
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "cycloneiv_clean_rom_addr_trace.log"))])
    sys.path.insert(0, REPO)
    nl = pickle.load(open(a.nl, "rb"))
    P = CP.Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))
    cells = a.cell or [f"m9k_{m['x']}_{m['y']}" for m in sorted((m for m in nl.m9k if any(m.get("init") or [])), key=lambda m: (m["x"], m["y"]))]
    for c in cells:
        trace(P, c)


if __name__ == "__main__":
    main()
