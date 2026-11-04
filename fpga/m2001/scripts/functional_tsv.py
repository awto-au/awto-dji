"""Read the committed functional-layer TSVs (fpga/m2001/board/functional_*.tsv, emitted from the
pluribus annotate DB by cycloneiv_clean_fold_functional.py --emit) and rebuild the blocks.json
shape: {"blocks": [...with seeds...], "rename": {...}, "proposed": [...]}.

Lets read-path consumers (cycloneiv_clean_partition.py) drop the blocks.json dependency with a
one-line swap. The DB/TSVs are the source of truth (awto-dji #98); blocks.json is retired once the
write-path consumers migrate too.

confidence <- tag with H->S reversed (fold mapped DJI 'S' structural/table inference to annotate 'H').
seeds rebuilt from members: ff_/lc_ ids verbatim, pad_<ball> -> <ball>, m9k_x_y/mac_x_y -> [x,y];
labs from functional_labs.tsv (LAB coords, not cell ids).
"""
import os
import re

TAG_TO_CONF = {"H": "S"}   # reverse of the fold's S->H


def _rows(path):
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            yield dict(zip(hdr, line.rstrip("\n").split("\t")))


def load(board_dir):
    bpath = os.path.join(board_dir, "functional_blocks.tsv")
    blocks = {}
    for r in _rows(bpath):
        blocks[r["block_id"]] = dict(
            name=r["name"], confidence=TAG_TO_CONF.get(r["tag"], r["tag"]),
            evidence=r["evidence"], note=r["claim"],
            seeds=dict(ffs=[], luts=[], labs=[], m9k=[], mac=[], pads=[]))
    by_name = {b["name"]: b for b in blocks.values()}

    for r in _rows(os.path.join(board_dir, "functional_members.tsv")):
        s = blocks[r["block_id"]]["seeds"]
        pid = r["physical_id"]
        if pid.startswith("ff_"):
            s["ffs"].append(pid)
        elif pid.startswith("lc_"):
            s["luts"].append(pid)
        elif pid.startswith("pad_"):
            s["pads"].append(pid[len("pad_"):])
        elif pid.startswith(("m9k_", "mac_")):
            x, y = map(int, pid.split("_")[1:3])
            s["m9k" if pid.startswith("m9k_") else "mac"].append([x, y])
        # pll_ members (clock_infra) have no blocks.json seed category -> dropped, as in the fold

    lpath = os.path.join(board_dir, "functional_labs.tsv")
    if os.path.isfile(lpath):
        for r in _rows(lpath):
            if r["name"] in by_name:
                by_name[r["name"]]["seeds"]["labs"].append([int(r["lab_x"]), int(r["lab_y"])])

    for b in blocks.values():                          # match blocks.json: sorted, de-duped
        s = b["seeds"]
        s["ffs"] = sorted(set(s["ffs"]))
        s["luts"] = sorted(set(s["luts"]))
        s["pads"] = sorted(set(s["pads"]))
        s["labs"] = sorted({tuple(t) for t in s["labs"]})
        s["m9k"] = sorted({tuple(t) for t in s["m9k"]})
        s["mac"] = sorted({tuple(t) for t in s["mac"]})
        for k in ("labs", "m9k", "mac"):
            s[k] = [list(t) for t in s[k]]

    rename = {}
    rpath = os.path.join(board_dir, "functional_rename.tsv")
    if os.path.isfile(rpath):
        rename = {r["from"]: r["to"] for r in _rows(rpath)}

    proposed = []
    ppath = os.path.join(board_dir, "functional_proposed.tsv")
    if os.path.isfile(ppath):
        for r in _rows(ppath):
            if r.get("model_confidence"):
                try:
                    r["model_confidence"] = float(r["model_confidence"])
                except ValueError:
                    pass
            proposed.append(r)

    # preserve TSV row order: Partition.seed() resolves seed conflicts by block order ("first wins").
    return dict(blocks=list(blocks.values()), rename=rename, proposed=proposed)
