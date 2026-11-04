#!/usr/bin/env python3
"""DB side of the m2001 DJI-functional layer (#98).

Source of truth = the committed board/functional_*.tsv (see functional_tsv.py). The pluribus
annotate DB (gx150.db, gitignored) is a DERIVED index:

  --rebuild         committed TSVs -> DB (clear the functional layer, re-add every block as
                    layer=functional), then check() against the image netlist. Run after a writer
                    edits the TSVs; DB check() is the validator.
  --bootstrap DIR   ONE-TIME migration (already applied; blocks.json retired #98 step 5):
                    board/blocks.json -> the new-shape TSVs in DIR (name-keyed, no block_id).
                    To re-run, restore blocks.json from git history first.

- Physical ids are shared with the pluribus image netlist; functional super-blocks overlap the
  physical-pattern partition (allowed within the layer model, awtoau/pluribus#165).
- Evidence is a cross-repo citation: the functional layer accepts doc:/issue: without a local file
  (proof lives in awto-dji). confidence V/I/U -> tag V/I/U; S -> H (flagged in the claim).

Run:  python3 fpga/m2001/scripts/cycloneiv_clean_fold_functional.py --rebuild
      PLURIBUS_SQLITE_PATH=databases/cycloneiv/gx150.db must point at the family DB.
Logs: tmp/logs/cycloneiv_clean_fold_functional.log
"""
import argparse
import json
import logging
import os
import pickle
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DJI_REPO = os.environ.get("DJI_REPO") or os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
PLURIBUS = os.environ.get("PLURIBUS_REPO") or "/mnt/2tb/git/pluribus"
BOARD = os.path.join(DJI_REPO, "fpga", "m2001", "board")
BLOCKS = os.path.join(BOARD, "blocks.json")

os.makedirs(os.path.join(DJI_REPO, "tmp", "logs"), exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.FileHandler(os.path.join(DJI_REPO, "tmp", "logs",
                              "cycloneiv_clean_fold_functional.log")), logging.StreamHandler()])
log = logging.getLogger("fold")

sys.path.insert(0, HERE)
import functional_tsv as FT  # noqa: E402

IMAGE = "image"


def _annotate():
    sys.path.insert(0, os.path.join(PLURIBUS, "scripts"))
    import cycloneiv_clean_annotate as A  # noqa: E402
    return A


def bootstrap(out_dir):
    """board/blocks.json -> the new-shape committed TSVs (name-keyed). One-time; blocks.json is then retired."""
    data = json.load(open(BLOCKS))
    records = [FT.record(b["name"], b["confidence"], b.get("evidence") or "", b.get("note") or "",
                         b["seeds"]) for b in data["blocks"]]
    # drop blocks with no concrete cell members (labs-only) — they carry no DB cells
    records = [r for r in records if r["members"]]
    FT.write_blocks(out_dir, records)
    FT.write_rename(out_dir, data.get("rename", {}))
    FT.write_proposed(out_dir, data.get("proposed", []))
    nmem = sum(len(r["members"]) for r in records)
    nlab = sum(len(r["labs"]) for r in records)
    log.info("bootstrap: %d blocks, %d members, %d labs, %d rename, %d proposed -> %s",
             len(records), nmem, nlab, len(data.get("rename", {})), len(data.get("proposed", [])), out_dir)


def rebuild(nl_path):
    """Committed TSVs -> DB: clear the functional layer, re-add every block, then check()."""
    A = _annotate()
    eng = A.get_engine()
    records = FT.read_blocks(BOARD)
    blocks, _ = A.load_all(eng, IMAGE)
    for b in blocks:
        if (b["layer"] or "physical") == "functional":
            A.remove_block(eng, IMAGE, b["block_id"])
    for r in records:
        members = [(mid, al or None) for mid, al in r["members"]]
        A.add_block(eng, IMAGE, r["kind"], r["name"], r["claim"], r["tag"], r["evidence"], members, layer="functional")
    log.info("rebuilt %d functional blocks into the DB", len(records))

    totals = A.netlist_totals(pickle.load(open(nl_path, "rb"))) if os.path.isfile(nl_path) else None
    blocks_db, _ = A.load_all(eng, IMAGE)
    func_ids = {b["block_id"] for b in blocks_db if (b["layer"] or "physical") == "functional"}
    allprobs = A.check(eng, IMAGE, totals)
    log.info("check(): %d total problems in the image (all layers)", len(allprobs))
    func_probs = [p for p in allprobs if "layer functional" in p or any(fid in p for fid in func_ids)]
    for p in func_probs:
        log.info("  FUNC PROBLEM: %s", p)
    if not func_probs:
        log.info("  no functional-layer problems")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rebuild", action="store_true", help="committed TSVs -> DB (clear + re-add functional layer), then check()")
    ap.add_argument("--bootstrap", metavar="DIR", help="ONE-TIME: board/blocks.json -> new-shape TSVs in DIR, then exit")
    ap.add_argument("--nl", default=os.path.join(PLURIBUS, "tmp", "dji_patterns", "image_nl.pkl"),
                    help="image netlist for check(--nl) membership/totals validation")
    a = ap.parse_args()
    if a.bootstrap:
        bootstrap(a.bootstrap)
    elif a.rebuild:
        rebuild(a.nl)
    else:
        ap.error("one of --rebuild / --bootstrap is required")


if __name__ == "__main__":
    main()
