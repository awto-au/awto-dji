#!/usr/bin/env python3.15t
"""Per-bit liveness of the probes_ram.json groups from a loopback sim probe trace; lists dead FFs that have live inputs (gating boundary) (#91).

  python3.15t fpga/m2001/scripts/loopback_probe_boundary.py      (reads tmp/loopback/probe_pl.txt in the pluribus checkout)
"""
import json, re, sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import BOARD, PLURIBUS
from cycloneiv_clean_partition import Partition, cell_of
from cycloneiv_clean_fsm_rxdetect_trace import cone_leaves
L = os.path.join(str(PLURIBUS), "tmp", "loopback") + "/"
meta = json.load(open(L + "tb_meta.json")); pr = json.load(open(L + "probes_ram.json"))
decl = {}
for line in open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/rtl_s.v")):
    m = re.match(r"\s*reg \[(\d+):0\] (\w+) ", line)
    if m: decl[m.group(2)] = int(m.group(1)) + 1
    if line.startswith("assign") or len(decl) > 5000: break
widths = [(n, w if w else decl[n]) for n, w in meta["probes"]]
pos = sum(w for _, w in widths); fields = {}
for n, w in widths: pos -= w; fields[n] = (pos, w)
rows = [(int(t), int(v, 16)) for t, v in (l.split() for l in open(L + "probe_pl.txt"))]
tog = {}
for g, names in pr.items():
    p, w = fields[g]; t = [0] * w; prev = None
    for _, v in rows:
        x = (v >> p) & ((1 << w) - 1)
        if prev is not None:
            d = x ^ prev
            while d:
                b = d & -d; t[b.bit_length() - 1] += 1; d ^= b
        prev = x
    for i in range(w): tog[names[w - 1 - i]] = t[i]
nl = pickle.load(open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/nl.pkl"), "rb"))
P = Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))
dead = {f for f, n in tog.items() if n == 0}
print("probed", len(tog), "dead", len(dead))
for f in sorted(dead):
    F = P.ff[f]; c = cell_of(F.get("d"))
    if not c: continue
    lv = {c} if not (isinstance(c, str) and c.startswith("lc_")) else cone_leaves(P, c)
    live = sorted(str(x) + f":{tog[x]}" for x in lv if isinstance(x, str) and tog.get(x))
    unk = sorted(str(x) for x in lv if not (isinstance(x, str) and x in tog))
    if live:
        print(f, "D=", F["d"], "LIVE inputs:", live, "| unprobed:", unk[:6])
