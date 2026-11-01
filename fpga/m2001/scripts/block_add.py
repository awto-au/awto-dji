#!/usr/bin/env python3.15t
"""Add or update one named block in fpga/m2001/board/blocks.json (the durable name registry) as a finding is made (#90).

  python3.15t fpga/m2001/scripts/block_add.py --name tx_playback_ctl --conf V --evidence "probe: we 1.34M changes (#91)" \\
      --ffs ff_a,ff_b --luts lc_x --probe-group pb23_62_addr --m9k 23,62 --note "..."
Conf: V verified (observed/derived), I inferred, S structure only, U unknown.  An existing block of the same name is replaced.
Refuses cells already seeded by ANOTHER block (partition marks them contested and drops both); --allow-overlap overrides.
--probe-group G adds the FFs of group G from tmp/loopback/probes_ram.json (pluribus checkout).  Log tmp/logs/block_add.log.
"""
import argparse
import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS, DJI, BOARD  # noqa: E402
log = logging.getLogger("block_add")


def csv(v):
    return [x for x in (v or "").split(",") if x]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--conf", required=True, choices=["V", "I", "S", "U"])
    ap.add_argument("--evidence", required=True)
    ap.add_argument("--note", default="")
    ap.add_argument("--ffs", default="")
    ap.add_argument("--luts", default="")
    ap.add_argument("--m9k", default="", help="x,y;x,y")
    ap.add_argument("--mac", default="", help="x,y;x,y")
    ap.add_argument("--labs", default="", help="x,y;x,y")
    ap.add_argument("--pads", default="")
    ap.add_argument("--probe-group", action="append", default=[])
    ap.add_argument("--allow-overlap", action="store_true")
    ap.add_argument("--blocks", default=os.path.join(BOARD, "blocks.json"))
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "block_add.log"))])
    ffs = csv(a.ffs)
    if a.probe_group:
        pr = json.load(open(os.path.join(str(PLURIBUS), "tmp", "loopback", "probes_ram.json")))
        for g in a.probe_group:
            ffs += pr[g]
    pair = lambda v: [list(map(int, x.split(","))) for x in v.split(";") if x]
    seeds = dict(ffs=sorted(set(ffs)), luts=sorted(set(csv(a.luts))), labs=sorted(pair(a.labs)), m9k=sorted(pair(a.m9k)),
                 mac=sorted(pair(a.mac)), pads=sorted(set(csv(a.pads))))
    db = json.load(open(a.blocks))
    clash = {}
    for b in db["blocks"]:
        if b["name"] == a.name:
            continue
        for k in ("ffs", "luts", "pads"):
            hit = set(seeds[k]) & set(b["seeds"].get(k, []))
            if hit:
                clash.setdefault(b["name"], []).extend(sorted(hit))
        for k in ("labs", "m9k", "mac"):
            hit = {tuple(x) for x in seeds[k]} & {tuple(x) for x in b["seeds"].get(k, [])}
            if hit:
                clash.setdefault(b["name"], []).extend(sorted(map(str, hit)))
    if clash and not a.allow_overlap:
        for n, c in clash.items():
            log.error("overlap with block %s: %d cells, e.g. %s", n, len(c), c[:4])
        sys.exit("refused: cells already seeded by another block (use --allow-overlap to add anyway)")
    new = dict(name=a.name, confidence=a.conf, evidence=a.evidence, note=a.note, seeds=seeds)
    old = [i for i, b in enumerate(db["blocks"]) if b["name"] == a.name]
    if old:
        db["blocks"][old[0]] = new
    else:
        db["blocks"].append(new)
    json.dump(db, open(a.blocks, "w"), indent=1)
    log.info("%s block %s (%s): %s", "updated" if old else "added", a.name, a.conf, {k: len(v) for k, v in seeds.items()})


if __name__ == "__main__":
    main()
