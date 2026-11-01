#!/usr/bin/env python3.15t
"""Static backward trace of the TX playback RAM write side: M9K (23,62)/(23,63) we / data / addr cones (#91).

  python3.15t fpga/m2001/scripts/cycloneiv_clean_playback_ram_trace.py --nl tmp/image_sim_dji_push/nl.pkl
Per pin group: cone leaves (FF/pad/M9K/MAC), owner block histogram, pads reached within HOPS FF hops, and whether the
FSM (38,86)/(39,86) or the uplink-record readers are upstream.  Out tmp/playback_ram_trace.json; log tmp/logs/cycloneiv_clean_playback_ram_trace.log.
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
from cycloneiv_clean_fsm_rxdetect_trace import cone_leaves, walk_back  # noqa: E402
log = logging.getLogger("playback_ram_trace")
RAMS = [(23, 62), (23, 63)]
FSM_LABS = {(38, 86), (39, 86)}


def group_cells(P, m):
    """pin group -> ordered list of driver cells (None entries dropped)."""
    from cycloneiv_clean_partition import cell_of
    g = {"data": [cell_of(p) for p in m["data"]], "addr": [cell_of(p) for p in m["addr"]], "raddr": [cell_of(p) for p in m["raddr"]],
         "we": [cell_of(m["we"])]}
    return {k: [c for c in v if c] for k, v in g.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nl", required=True)
    ap.add_argument("--partition", default=os.path.join(REPO, "tmp", "cycloneiv_clean", "partition.json"))
    ap.add_argument("--hops", type=int, default=14)
    ap.add_argument("--cap", type=int, default=200000)
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "cycloneiv_clean_playback_ram_trace.log"))])
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
    out = {}
    for xy in RAMS:
        m = P.m9k[xy]
        for grp, cells in group_cells(P, m).items():
            leaves = set()
            for c in cells:
                leaves |= {c} if not (isinstance(c, str) and c.startswith("lc_")) else cone_leaves(P, c) | set()
                if isinstance(c, str) and c.startswith("lc_"):
                    leaves |= cone_leaves(P, c)
            own = collections.Counter(owner.get(l, "?") for l in leaves)
            pads, upstream, fsm_up = {}, collections.Counter(), False
            for l in sorted(leaves, key=str):
                p, bl, _ = walk_back(P, l, owner, a.hops, a.cap)
                for k, v in p.items():
                    pads[k] = min(v, pads.get(k, 99))
                upstream.update(bl)
                fsm_up = fsm_up or any((P.ff[n]["x"], P.ff[n]["y"]) in FSM_LABS for n in [l] if isinstance(n, str) and n in P.ff)
            key = f"{xy[0]}_{xy[1]}.{grp}"
            out[key] = dict(cells=len(cells), leaves=len(leaves), leaf_owners=dict(own.most_common(6)), pads=dict(sorted(pads.items(), key=lambda kv: kv[1])),
                            upstream=dict(upstream.most_common(8)), fsm_is_direct_leaf=fsm_up)
            log.info("%s: %d cells, %d leaves; leaf owners %s; pads %s; upstream %s; FSM direct=%s", key, len(cells), len(leaves),
                     dict(own.most_common(4)), pads or "none", dict(upstream.most_common(5)), fsm_up)
    json.dump(out, open(os.path.join(DJI, "tmp", "playback_ram_trace.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
