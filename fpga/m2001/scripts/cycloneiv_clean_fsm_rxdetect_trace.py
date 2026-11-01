#!/usr/bin/env python3.15t
"""Backward trace of the frame FSM (38,86)/(39,86) inputs: which leaves gate the TX slot (#91 step 1).

  python3.15t fpga/m2001/scripts/cycloneiv_clean_fsm_rxdetect_trace.py --nl tmp/image_sim_dji_push/nl.pkl
Static, no sim.  Per FSM FF: next-state cone leaves (FF / pad / M9K / MAC).  Non-FSM leaves are walked back through FFs
(HOPS, CAP) to pads and partition blocks.  Out tmp/fsm_rxdetect_trace.json; log tmp/logs/cycloneiv_clean_fsm_rxdetect_trace.log.
"""
import argparse
import collections
import json
import logging
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO, DJI, BOARD  # noqa: E402,F401  (REPO = pluribus engine checkout; DJI = this repo)
log = logging.getLogger("fsm_rxdetect")
FSM_LABS = {(38, 86), (39, 86)}
HOPS = 6          # FF hops back from a leaf; the RX detect chain is short (decision: widen only if pads are not reached)
CAP = 3000        # visited-node cap per leaf walk (comb chains can be long; bounds runtime)


def cone_leaves(P, root):
    """Non-LUT cells feeding `root` through LUT-only paths (root's own data/ctl pins)."""
    leaves, seen, st = set(), set(), list(P.inputs(root))
    while st:
        c = st.pop()
        if c in seen:
            continue
        seen.add(c)
        if isinstance(c, str) and c.startswith("lc_"):
            st.extend(P.inputs(c))
        else:
            leaves.add(c)
    return leaves


def walk_back(P, start, owner, hops, cap):
    """BFS through FFs and LUTs from `start`; returns pads reached by FF-hop depth and block-name histogram."""
    seen, pads, blocks = {start}, {}, collections.Counter()
    frontier = [(start, 0)]
    while frontier and len(seen) < cap:
        nxt = []
        for c, h in frontier:
            blocks[owner.get(c, "?")] += 1
            if isinstance(c, tuple) and c[0] == "pad":
                pads.setdefault(c[1], h)
                continue
            nh = h + 1 if (isinstance(c, str) and c.startswith("ff_")) else h
            if nh > hops:
                continue
            for i in P.inputs(c):
                if i not in seen:
                    seen.add(i)
                    nxt.append((i, nh))
        frontier = nxt
    return pads, blocks, len(seen)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", required=True)
    ap.add_argument("--partition", default=os.path.join(REPO, "tmp", "cycloneiv_clean", "partition.json"))
    ap.add_argument("--hops", type=int, default=HOPS)
    ap.add_argument("--cap", type=int, default=CAP)
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "cycloneiv_clean_fsm_rxdetect_trace.log"))])
    from cycloneiv_clean_partition import Partition
    nl = pickle.load(open(a.nl, "rb"))
    P = Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))
    owner = {}
    for b in json.load(open(a.partition))["blocks"]:
        cl = b["cells"]
        for c in cl["luts"] + cl["ffs"]:
            owner[c] = b["name"]
        for x, y in cl["m9k"]:
            owner[("m9k", x, y)] = b["name"]
    fsm = sorted(n for n, F in P.ff.items() if (F["x"], F["y"]) in FSM_LABS)
    log.info("FSM FFs in %s: %d", sorted(FSM_LABS), len(fsm))
    out = dict(fsm=fsm, ffs={}, leaves={})
    allleaves = collections.defaultdict(set)
    for f in fsm:
        lv = cone_leaves(P, f)
        out["ffs"][f] = sorted(map(str, lv))
        for l in lv:
            allleaves[l].add(f)
        log.info("%s: %d cone leaves (%d FSM-internal)", f, len(lv), sum(1 for l in lv if l in fsm))
    ext = sorted((l for l in allleaves if l not in fsm), key=str)
    log.info("external leaves: %d", len(ext))
    for l in ext:
        pads, blocks, n = walk_back(P, l, owner, a.hops, a.cap)
        row = dict(feeds=sorted(allleaves[l]), owner=owner.get(l, "?"), pads=pads, upstream_blocks=dict(blocks.most_common(5)), visited=n)
        out["leaves"][str(l)] = row
        log.info("  %s -> %s [%s] pads<=%dhop: %s | upstream %s", l, ",".join(row["feeds"]), row["owner"], a.hops, pads or "none", row["upstream_blocks"])
    json.dump(out, open(os.path.join(DJI, "tmp", "fsm_rxdetect_trace.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
