#!/usr/bin/env python3.15t
"""Add backward FF stages from the dead playback-data frontier to tmp/loopback/probes_ram.json (#91).

  python3.15t fpga/m2001/scripts/loopback_mkprobes_frontier.py [--levels 3] [--budget 700]
Seeds: lvl3 FFs of probes_ram.json that stay 0 in the live-RX run while their enable toggles.  Groups fr1..frN = FF stages upstream of the seeds
not already probed; replaces earlier fr* groups.  Rebuild the sim afterwards (cycloneiv_clean_loopback_sim.py build).
"""
import argparse
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import BOARD, PLURIBUS  # noqa: E402
from cycloneiv_clean_partition import Partition, cell_of  # noqa: E402
from cycloneiv_clean_fsm_rxdetect_trace import cone_leaves  # noqa: E402

SEEDS = ["ff_15_62_6", "ff_18_63_4", "ff_16_63_12", "ff_13_62_8", "ff_18_63_2"]   # lvl3 FFs that stay 0 with a live enable (ff_13_61_15), run pa
ap = argparse.ArgumentParser()
ap.add_argument("--levels", type=int, default=3)
ap.add_argument("--trace", help="sim tag: seed from the deepest probed stage's FFs that never change in probe_TAG.txt (replaces SEEDS)")
ap.add_argument("--budget", type=int, default=700)   # 1024-bit probe vector minus the 291 already in probes_ram.json
a = ap.parse_args()
nl = pickle.load(open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/nl.pkl"), "rb"))
ffmap = json.load(open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/ffmap.json")))
P = Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))
path = os.path.join(str(PLURIBUS), "tmp/loopback/probes_ram.json")
groups = json.load(open(path))
if not a.trace and a.levels:
    groups = {k: v for k, v in groups.items() if not k.startswith("fr")}
seen = {f for v in groups.values() for f in v}


def dead_ffs(tag, grp):
    """FFs of probes_ram group grp that never change in probe_TAG.txt (widths from tb_meta.json + rtl_s.v decls)."""
    import re
    L = os.path.join(str(PLURIBUS), "tmp/loopback") + "/"
    meta = json.load(open(L + "tb_meta.json"))
    decl = {}
    for line in open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/rtl_s.v")):
        m = re.match(r"\s*reg \[(\d+):0\] (\w+) ", line)
        if m:
            decl[m.group(2)] = int(m.group(1)) + 1
        if line.startswith("assign") or len(decl) > 5000:
            break
    widths = [(n, w if w else decl.get(n, 0)) for n, w in meta["probes"]]
    pos = sum(w for _, w in widths)
    fields = {}
    for n, w in widths:
        pos -= w
        fields[n] = (pos, w)
    rows = [int(v, 16) for _, v in (l.split() for l in open(L + f"probe_{tag}.txt"))]
    p, w = fields[grp]
    dead = []
    for i, f in enumerate(groups[grp]):
        bit = p + (w - 1 - i)
        if len({(v >> bit) & 1 for v in rows}) == 1:
            dead.append(f)
    return dead


if a.trace:
    deepest = max((k for k in groups if k.startswith("fr") and groups[k]), key=lambda k: int(k[2:]))
    SEEDS = dead_ffs(a.trace, deepest)
    print("seeds: dead FFs of", deepest, "in trace", a.trace, ":", len(SEEDS))
    base = int(deepest[2:])
else:
    base = 0
cur = [s for s in SEEDS if s in ffmap]
groups.setdefault("fr0", [])
groups["fr0"] += [s for s in cur if s not in seen]
seen |= set(cur)
used = sum(len(v) for k, v in groups.items() if k.startswith("fr"))
for k in range(1, a.levels + 1):
    nxt = set()
    for f in cur:
        for pin in ("d", "ena"):
            c = cell_of(P.ff[f].get(pin))
            if c:
                nxt |= {c} if not (isinstance(c, str) and c.startswith("lc_")) else cone_leaves(P, c)
    nxt = sorted(f for f in nxt if isinstance(f, str) and f.startswith("ff_") and f in ffmap and f not in seen)
    if used + len(nxt) > a.budget:
        print(f"level {k}: {len(nxt)} FFs would exceed budget {a.budget} (used {used}); stopping")
        break
    groups[f"fr{base + k}"] = nxt
    seen |= set(nxt)
    used += len(nxt)
    cur = nxt
    print("level", k, len(nxt))
HEAD_RAMS = [(36, 62), (23, 61), (36, 54), (23, 55), (23, 54)]   # M9Ks heading the dead chain (4b x 2048, no init data)
for xy in HEAD_RAMS:
    m = P.m9k[xy]
    for grp, cells in (("we", [cell_of(m["we"])]), ("data", [cell_of(q) for q in m["data"]])):
        leaves = set()
        for c in cells:
            if isinstance(c, str) and c.startswith("lc_"):
                leaves |= cone_leaves(P, c)
            elif c:
                leaves.add(c)
        fs = sorted(f for f in leaves if isinstance(f, str) and f.startswith("ff_") and f in ffmap and f not in seen)
        if fs:
            groups[f"hw{xy[0]}_{xy[1]}_{grp}"] = fs
            seen |= set(fs)
json.dump(groups, open(path, "w"), indent=1)
print({k: len(v) for k, v in groups.items() if k.startswith("fr")}, "frontier bits", used, "total", sum(len(v) for v in groups.values()))
