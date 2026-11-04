#!/usr/bin/env python3.15t
"""Static backward trace of the WRITE side of the five head M9K lookup tables that feed the dead TX
playback-data chain (#91).

  python3.15t fpga/m2001/scripts/cycloneiv_clean_head_ram_write_trace.py --nl tmp/image_sim_dji_push/nl.pkl

The five RAMs (36,62),(23,61),(36,54),(23,55),(23,54) are register-indexed lookup tables (run pi: read
address is a static SPI-register copy, not a streaming pointer).  The playback data leaves at 0 because the
read word is 0.  This asks the static question the probe line could not: does the WRITE path ever put real
data there, or only boot-table constants?  Per head RAM and pin group (we / data / addr=write / raddr=read):
  - cone leaf count + owner-block histogram, pads reached within HOPS FF hops
  - data-source class: does the data cone reach an RX-capture M9K, the uplink-record M9K, or RX pads
    (=> real replay data) vs. only the boot regfile / constants (=> table can only ever hold boot words)
  - write-addr vs read-addr shared FF drivers (can a write ever select the word the read selects)
  - whether we / data / addr cones reach the frame FSM (38,86)/(39,86) or the table sequencer ff_31_73_4

Out tmp/head_ram_write_trace.json; log tmp/logs/cycloneiv_clean_head_ram_write_trace.log.
"""
import argparse
import collections
import json
import logging
import os
import pickle
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO, DJI, BOARD  # noqa: E402,F401

log = logging.getLogger("head_ram_write_trace")

# Five head lookup-table RAMs that sit at the head of the dead playback-data chain (#91 run-pi conclusion).
HEAD_RAMS = [(36, 62), (23, 61), (36, 54), (23, 55), (23, 54)]
FSM_LABS = {(38, 86), (39, 86)}
SEQ_FF = "ff_31_73_4"      # #91 comment called this the table sequencer; this trace shows it is a tied constant
WE_FF = "ff_87_61_2"       # table write-enable


def is_const(P, sig):
    """True if a signal name is a tied constant (gnd/vcc/0/1)."""
    s = str(sig).lower()
    return s in ("gnd", "vcc", "0", "1", "1'b0", "1'b1") or s.endswith("gnd") or s.endswith("vcc")


def direct_drivers(P, sigs):
    """signal list -> Counter of immediate driver cell kinds, and the concrete driver cells."""
    from cycloneiv_clean_partition import cell_of
    kinds = collections.Counter()
    cells = []
    for s in (sigs or []):
        if is_const(P, s):
            kinds["const"] += 1
            continue
        c = cell_of(s)
        if c is None:
            kinds["none"] += 1
        elif isinstance(c, str) and c.startswith("lc_"):
            kinds["lut"] += 1
            cells.append(c)
        elif isinstance(c, str) and c.startswith("ff_"):
            kinds["ff"] += 1
            cells.append(c)
        elif isinstance(c, tuple):
            kinds[c[0]] += 1
            cells.append(c)
        else:
            kinds["other"] += 1
            cells.append(c)
    return kinds, cells


def ff_d_leaves(P, ff):
    """Non-LUT leaves feeding the D (and enable) pins of a single FF, through LUT-only paths (one register stage)."""
    if not (isinstance(ff, str) and ff in P.ff):
        return set()
    leaves, seen, st = set(), set(), list(P.inputs(ff))
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


def group_cells(P, m):
    from cycloneiv_clean_partition import cell_of
    g = {"we": [cell_of(m["we"])] if m.get("we") else [],
         "data": [cell_of(p) for p in (m.get("data") or [])],
         "waddr": [cell_of(p) for p in (m.get("addr") or [])],
         "raddr": [cell_of(p) for p in (m.get("raddr") or [])]}
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
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(os.path.join(DJI, "tmp", "logs", "cycloneiv_clean_head_ram_write_trace.log"))])
    from cycloneiv_clean_partition import Partition
    nl_path = a.nl if os.path.isabs(a.nl) else os.path.join(REPO, a.nl)
    nl = pickle.load(open(nl_path, "rb"))
    P = Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))

    owner = {}
    for b in json.load(open(a.partition))["blocks"]:
        cl = b["cells"]
        for c in cl["luts"] + cl["ffs"]:
            owner[c] = b["name"]
        for x, y in cl["m9k"]:
            owner[("m9k", x, y)] = b["name"]

    def owner_hist(cells):
        return dict(collections.Counter(owner.get(c, "?") for c in cells).most_common(6))

    out = {"rams": {}}
    for xy in HEAD_RAMS:
        if xy not in P.m9k:
            log.warning("RAM %s not in netlist m9k set; skipping", xy)
            continue
        m = P.m9k[xy]
        rec = {}
        for grp in ("we", "data", "waddr", "raddr"):
            sigs = ([m["we"]] if (grp == "we" and m.get("we")) else
                    m.get({"data": "data", "waddr": "addr", "raddr": "raddr"}[grp]) or [])
            kinds, cells = direct_drivers(P, sigs)
            rec[grp] = dict(nsig=len(sigs), driver_kinds=dict(kinds), driver_owners=owner_hist(cells),
                            all_const=(kinds.get("const", 0) == len(sigs) and len(sigs) > 0))
        out["rams"][f"{xy[0]}_{xy[1]}"] = rec
        log.info("RAM %d_%d: we=%s data=%s(all_const=%s,owners=%s) waddr=%s raddr=%s", xy[0], xy[1],
                 dict(rec["we"]["driver_kinds"]), dict(rec["data"]["driver_kinds"]), rec["data"]["all_const"],
                 rec["data"]["driver_owners"], dict(rec["waddr"]["driver_kinds"]), dict(rec["raddr"]["driver_kinds"]))

    # Gating of the two control FFs named in the #91 closing comment: what feeds their D/enable cone (one stage back).
    gate = {}
    for ff in (SEQ_FF, WE_FF):
        leaves = ff_d_leaves(P, ff)
        if not leaves and ff not in P.ff:
            gate[ff] = {"present": False}
            log.warning("control FF %s not in netlist", ff)
            continue
        own = collections.Counter(owner.get(l, "?") for l in leaves)
        fsm_leaf = sorted(str(l) for l in leaves
                          if isinstance(l, str) and l in P.ff and (P.ff[l]["x"], P.ff[l]["y"]) in FSM_LABS)
        gate[ff] = dict(present=True, nleaves=len(leaves), leaf_owners=dict(own.most_common(8)),
                        fsm_leaves=fsm_leaf,
                        leaf_ffs=sorted(str(l) for l in leaves if isinstance(l, str) and l.startswith("ff_"))[:30])
        log.info("control FF %s: %d D/en-cone leaves; owners %s; FSM leaves=%s", ff, len(leaves),
                 dict(own.most_common(5)), fsm_leaf or "none")
    out["control_ffs"] = gate

    json.dump(out, open(os.path.join(DJI, "tmp", "head_ram_write_trace.json"), "w"), indent=1, default=str)
    log.info("wrote tmp/head_ram_write_trace.json")


if __name__ == "__main__":
    main()
