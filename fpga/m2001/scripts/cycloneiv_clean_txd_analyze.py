#!/usr/bin/env python3.15t
"""Extract the 12-bit AD9363 TXD bus from a sim pad trace and summarise TX activity (#89 step 3).

Trace row = 'edge hexword', hexword = {pad_outs[0]..pad_outs[-1]} MSB..LSB (gen_tb's output capture).
TXD_0..11 and the burst gate (AC8, I) / mux-select (R25, V) are read by ball -> bit position. Reports
whether the TXD lines carry a waveform while the burst gate is asserted, and the dominant period.
Read-only. All pad roles V from pins.tsv except AC8 (I).

  python3.15t fpga/m2001/scripts/cycloneiv_clean_txd_analyze.py [--nl NL.pkl] [--trace trace_tx_out.txt]
Writes a summary JSON next to the trace + prints the headline lines.
"""
import argparse
import json
import os
import pickle
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO  # noqa: E402

TXD = {0: "E25", 1: "E26", 2: "H24", 3: "G25", 4: "G26", 5: "F26", 6: "H25", 7: "H26", 8: "J26", 9: "K26", 10: "L25", 11: "L26"}
GATE, MUX = "AC8", "R25"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", default=os.path.join(REPO, "tmp", "image_sim_dji_push", "nl.pkl"))
    ap.add_argument("--trace", default=os.path.join(REPO, "tmp", "image_sim", "trace_tx_out.txt"))
    a = ap.parse_args()
    sys.path.insert(0, REPO)
    nl = pickle.load(open(a.nl, "rb"))
    outs = sorted(b for b, d in ({io["ball"]: io["dir"] for io in nl.ios}).items() if d != "input")
    N = len(outs)
    bp = {b: (N - 1) - outs.index(b) for b in outs}
    txb = [bp[TXD[i]] for i in range(12)]
    vals, gate, mux = [], [], []
    for line in open(a.trace):
        p = line.split()
        if len(p) != 2:
            continue
        w = int(p[1], 16)
        vals.append(sum(((w >> txb[i]) & 1) << i for i in range(12)))
        gate.append((w >> bp[GATE]) & 1); mux.append((w >> bp[MUX]) & 1)
    vals, gate, mux = np.array(vals), np.array(gate), np.array(mux)
    chg = np.flatnonzero(np.diff(vals) != 0) if len(vals) else np.array([])
    s = dict(trace=a.trace, rows=len(vals), txd_distinct=int(len(set(vals.tolist()))),
             txd_range=[int(vals.min()), int(vals.max())] if len(vals) else [],
             txd_changes=int(len(chg)), first_change=int(chg[0]) if len(chg) else None, last_change=int(chg[-1]) if len(chg) else None,
             gate_high=int(gate.sum()), gate_first_high=int(np.argmax(gate)) if gate.any() else None, mux_high=int(mux.sum()))
    if gate.any():
        g = vals[gate == 1]
        s["txd_gated"] = dict(samples=int(len(g)), distinct=int(len(set(g.tolist()))), range=[int(g.min()), int(g.max())])
        if len(g) >= 64:
            x = g.astype(float) - g.mean()
            spec = np.abs(np.fft.rfft(x)); k = int(np.argmax(spec[1:]) + 1)
            s["txd_gated"]["dominant_period_samples"] = round(len(g) / k, 2)
            s["txd_gated"]["top_bins"] = sorted(int(b) for b in (np.argsort(spec[1:])[-5:] + 1))
    out = os.path.splitext(a.trace)[0] + "_txd_summary.json"
    json.dump(s, open(out, "w"), indent=1)
    print(f"TXD rows={s['rows']} distinct={s['txd_distinct']} changes={s['txd_changes']} "
          f"gate_high={s['gate_high']} (first@{s['gate_first_high']}) mux_high={s['mux_high']}")
    if "txd_gated" in s:
        print(f"TXD while gate high: {s['txd_gated']}")
    else:
        print("burst gate (AC8) NEVER asserted -> no TX burst; needs the arm trigger / lock state (#89 risk)")
    print(f"summary -> {out}")


if __name__ == "__main__":
    main()
