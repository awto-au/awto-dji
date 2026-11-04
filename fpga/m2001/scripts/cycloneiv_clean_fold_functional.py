#!/usr/bin/env python3
"""Fold the DJI-functional m2001 block identities (board/blocks.json) into the pluribus annotate
DB as layer=functional (awto-dji #98 step 1).

- Physical ids are shared with the pluribus image netlist; functional super-blocks overlap the
  physical-pattern partition (allowed within the layer model, awtoau/pluribus#165).
- confidence V/I/U -> tag V/I/U; S (structural/table inference) -> H, flagged in the claim.
- Evidence is a cross-repo citation: the functional layer accepts doc:/issue: without a local
  file (proof lives in awto-dji). Each block cites its blocks.json evidence string verbatim +
  issue:98.
- labs (coarse LAB coords) are not cell ids in the annotate model; the concrete ff/lc/m9k/mac/pad
  seeds are the members. Blocks with only labs+m9k carry their m9k/mac/pads.

Run:  python3 fpga/m2001/scripts/cycloneiv_clean_fold_functional.py [--apply]
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
BLOCKS = os.path.join(DJI_REPO, "fpga", "m2001", "board", "blocks.json")

os.makedirs(os.path.join(DJI_REPO, "tmp", "logs"), exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(message)s",
                    handlers=[logging.FileHandler(os.path.join(DJI_REPO, "tmp", "logs",
                              "cycloneiv_clean_fold_functional.log")), logging.StreamHandler()])
log = logging.getLogger("fold")

sys.path.insert(0, os.path.join(PLURIBUS, "scripts"))
import cycloneiv_clean_annotate as A  # noqa: E402

IMAGE = "image"

# DJI-functional name -> annotate kind (prefix only; the real identity is the name).
KIND = {
    "clock_infra": "CLK",
    "spi_regfile": "SPI", "radio_spi_engine": "SPI",
    "af3_engine": "DAT", "video_duml_demux": "DAT", "rx_id_comparator": "DAT",
    "tx_playback": "DAT", "uplink_record_readers": "DAT", "tx_playback_ctl": "FSM",
    "tx_playback_data_pipe": "DAT",
    "fx3_gpif": "IO", "duml_uart_tx_ac11": "IO", "fx3_in_uart_tx_ac10": "IO",
    "ad9363_rx_capture": "IO", "pads_misc": "IO",
    "video_buffer": "MEM", "reg3_tables": "MEM", "tx_source_bank": "MEM",
    "frame_fsm": "FSM",
}
# the six 802.16 LFSR scramblers -> SCR (matched by prefix below)

TAG = {"V": "V", "I": "I", "U": "U", "S": "H"}

# Members that are not plain seed cells. clock_infra's identity is PLL_2/PLL_8 (its B14 seed is a
# dedicated clock-input pin, absent from the fabric netlist); its cell members are the PLLs.
MEMBER_OVERRIDE = {"clock_infra": ["pll_2", "pll_8"]}


def kind_of(name):
    if name.startswith("802.16-lfsr"):
        return "SCR"
    return KIND.get(name, "DAT")


def members_of(seeds):
    ms = []
    ms += list(seeds.get("ffs", []))
    ms += list(seeds.get("luts", []))
    ms += [f"m9k_{x}_{y}" for x, y in seeds.get("m9k", [])]
    ms += [f"mac_{x}_{y}" for x, y in seeds.get("mac", [])]
    ms += [f"pad_{b}" for b in seeds.get("pads", [])]
    # labs are coarse LAB coords, not cell ids in the annotate model -> not members
    return [(m, None) for m in ms]


def split_top(s):
    """Split on ';' at paren depth 0 so a ';' inside '(...)' stays within its piece."""
    out, buf, depth = [], [], 0
    for ch in s:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch == ";" and depth == 0:
            out.append("".join(buf)); buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [p.strip() for p in out if p.strip()]


def evidence_of(blk):
    raw = blk.get("evidence") or ""
    # each top-level piece kept as a citation; internal ';' -> ',' so the token survives parse_evidence's ';' split.
    toks = [f"doc:{p.replace(';', ',')}" for p in split_top(raw)]
    import re
    for n in dict.fromkeys(re.findall(r"#(\d+)", raw)):  # also surface GitHub issue refs, order-preserving
        toks.append(f"issue:{n}")
    toks.append("issue:98")
    return ";".join(toks)


def claim_of(blk):
    c = (blk.get("note") or "").strip() or f"DJI-functional block {blk['name']}"
    if blk["confidence"] == "S":
        c = f"[DJI confidence S: structural / table inference] {c}"
    return c


def emit_tsv(eng, out_dir):
    """Emit the DB functional layer (source of truth) -> two committed TSVs in awto-dji.
    functional_blocks.tsv: one row per block; functional_members.tsv: one row per member."""
    blocks, mem = A.load_all(eng, IMAGE)
    func = [b for b in blocks if (b["layer"] or "physical") == "functional"]
    # emit in blocks.json order: Partition.seed() resolves seed conflicts by block order ("first wins"),
    # so the row order is load-bearing. Sourced from blocks.json now; the TSV order is the durable copy.
    order = {blk["name"]: i for i, blk in enumerate(json.load(open(BLOCKS))["blocks"])}
    func.sort(key=lambda b: (order.get(b["name"], len(order)), b["block_id"]))
    os.makedirs(out_dir, exist_ok=True)
    bpath = os.path.join(out_dir, "functional_blocks.tsv")
    mpath = os.path.join(out_dir, "functional_members.tsv")
    with open(bpath, "w") as f:
        f.write("block_id\tname\tkind\ttag\tn_members\tevidence\tclaim\n")
        for b in func:
            f.write("\t".join(str(b[k]) for k in
                    ("block_id", "name", "kind", "tag", "n_members", "evidence", "claim")) + "\n")
    with open(mpath, "w") as f:
        f.write("block_id\tname\tobj_kind\tphysical_id\talias\n")
        for b in func:
            for m in mem[b["block_id"]]:
                f.write(f"{b['block_id']}\t{b['name']}\t{m['obj_kind']}\t{m['obj_id']}\t{m['alias'] or ''}\n")
    nmem = sum(len(mem[b["block_id"]]) for b in func)
    log.info("emitted %d blocks -> %s", len(func), bpath)
    log.info("emitted %d members -> %s", nmem, mpath)
    emit_sidecars(out_dir)


def emit_sidecars(out_dir):
    """labs / rename / proposed are blocks.json data with no annotate-member home (labs are LAB coords,
    not cell ids; rename + proposed are top-level config). Emit them verbatim so the committed TSVs fully
    replace blocks.json as an input. Sourced from blocks.json now; becomes the durable copy."""
    data = json.load(open(BLOCKS))
    clean = lambda v: str(v).replace("\t", " ").replace("\n", " ")

    lpath = os.path.join(out_dir, "functional_labs.tsv")
    nlab = 0
    with open(lpath, "w") as f:
        f.write("name\tlab_x\tlab_y\n")
        for blk in data["blocks"]:
            for x, y in blk["seeds"].get("labs", []):
                f.write(f"{blk['name']}\t{x}\t{y}\n"); nlab += 1
    log.info("emitted %d labs -> %s", nlab, lpath)

    rpath = os.path.join(out_dir, "functional_rename.tsv")
    with open(rpath, "w") as f:
        f.write("from\tto\n")
        for k, v in data.get("rename", {}).items():
            f.write(f"{k}\t{v}\n")
    log.info("emitted %d renames -> %s", len(data.get("rename", {})), rpath)

    ppath = os.path.join(out_dir, "functional_proposed.tsv")
    cols = ["name", "confidence", "blob", "region", "model", "model_confidence", "verify", "test", "detail"]
    with open(ppath, "w") as f:
        f.write("\t".join(cols) + "\n")
        for r in data.get("proposed", []):
            f.write("\t".join(clean(r.get(c, "")) for c in cols) + "\n")
    log.info("emitted %d proposed -> %s", len(data.get("proposed", [])), ppath)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="write to the DB (default: dry-run plan only)")
    ap.add_argument("--emit", metavar="DIR", help="emit the DB functional layer to committed TSVs in DIR and exit")
    ap.add_argument("--nl", default=os.path.join(PLURIBUS, "tmp", "dji_patterns", "image_nl.pkl"),
                    help="image netlist for check(--nl) membership validation")
    a = ap.parse_args()

    if a.emit:
        emit_tsv(A.get_engine(), a.emit)
        return

    data = json.load(open(BLOCKS))
    blocks = data["blocks"]
    log.info("blocks.json: %d functional identities", len(blocks))

    plan = []
    for blk in blocks:
        nm = blk["name"]
        ms = [(m, None) for m in MEMBER_OVERRIDE[nm]] if nm in MEMBER_OVERRIDE else members_of(blk["seeds"])
        if not ms:
            log.warning("  SKIP %s: no concrete cell members (labs-only)", nm)
            continue
        plan.append((kind_of(nm), nm, claim_of(blk), TAG[blk["confidence"]], evidence_of(blk), ms))
        log.info("  %-5s %-30s tag=%s members=%d", kind_of(nm), nm, TAG[blk["confidence"]], len(ms))

    if not a.apply:
        log.info("dry-run: %d blocks planned; re-run with --apply", len(plan))
        return

    eng = A.get_engine()
    for kind, nm, claim, tag, ev, ms in plan:
        bid, act = A.add_block(eng, IMAGE, kind, nm, claim, tag, ev, ms, layer="functional")
        log.info("  %s %s %s", act, bid, nm)

    totals = None
    if os.path.isfile(a.nl):
        totals = A.netlist_totals(pickle.load(open(a.nl, "rb")))
    blocks_db, _ = A.load_all(eng, IMAGE)
    func_ids = {b["block_id"] for b in blocks_db if (b["layer"] or "physical") == "functional"}
    allprobs = A.check(eng, IMAGE, totals)
    log.info("check(): %d total problems in the image (all layers)", len(allprobs))
    func_probs = [p for p in allprobs if "layer functional" in p or any(fid in p for fid in func_ids)]
    for p in func_probs:
        log.info("  FUNC PROBLEM: %s", p)
    if not func_probs:
        log.info("  no functional-layer problems")


if __name__ == "__main__":
    main()
