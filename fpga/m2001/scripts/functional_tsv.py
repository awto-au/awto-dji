"""Committed functional-layer TSVs — the SOURCE OF TRUTH for the m2001 DJI-functional blocks (#98).

Pure TSV I/O + the blocks.json->row derivation. No pluribus import (the DB side lives in
cycloneiv_clean_fold_functional.py). Writers (block_add.py, region_verify.py --write-blocks,
partition.py --build-seeds) edit these files through this module; the read-path
(partition.py) loads them; the gitignored annotate DB (gx150.db) is a DERIVED index
rebuilt from them by `fold_functional.py --rebuild`, and DB check() validates.

Keyed by `name`: block ids are a DB-internal value (annotate next_block_id counts across the whole
image incl. the gitignored physical layer, so a committed file cannot allocate one) — `name` is
unique per functional block and is already the DB's upsert key, so the TSVs carry no block_id.

Files (board/):
  functional_blocks.tsv    name  kind  tag  n_members  evidence  claim
  functional_members.tsv   name  obj_kind  physical_id  alias
  functional_labs.tsv      name  lab_x  lab_y          (coarse LAB coords; not DB cells)
  functional_rename.tsv    from  to                    (unknown-component name -> functional name)
  functional_proposed.tsv  name  confidence  blob  region  model  model_confidence  verify  test  detail
"""
import os
import re

BLOCKS = "functional_blocks.tsv"
MEMBERS = "functional_members.tsv"
LABS = "functional_labs.tsv"
RENAME = "functional_rename.tsv"
PROPOSED = "functional_proposed.tsv"

PROPOSED_COLS = ["name", "confidence", "blob", "region", "model", "model_confidence", "verify", "test", "detail"]

# ---- derivation (blocks.json record -> TSV fields) -----------------------------------------------------------------

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
TAG = {"V": "V", "I": "I", "U": "U", "S": "H"}          # confidence -> annotate tag (S structural -> H)
CONF = {v: k for k, v in TAG.items()}                   # tag -> confidence (H -> S)

# clock_infra's identity is PLL_2/PLL_8 (its B14 seed is a dedicated clock-input pin, absent from the
# fabric netlist); its cell members are the PLLs.
MEMBER_OVERRIDE = {"clock_infra": ["pll_2", "pll_8"]}


def kind_of(name):
    if name.startswith("802.16-lfsr"):
        return "SCR"
    return KIND.get(name, "DAT")


def members_of(name, seeds):
    """seeds dict (blocks.json shape) -> ordered [physical_id]. labs are coarse LAB coords, not cells."""
    if name in MEMBER_OVERRIDE:
        return list(MEMBER_OVERRIDE[name])
    ms = []
    ms += list(seeds.get("ffs", []))
    ms += list(seeds.get("luts", []))
    ms += [f"m9k_{x}_{y}" for x, y in seeds.get("m9k", [])]
    ms += [f"mac_{x}_{y}" for x, y in seeds.get("mac", [])]
    ms += [f"pad_{b}" for b in seeds.get("pads", [])]
    return ms


def _obj_kind(oid):
    for p, k in (("ff_", "ff"), ("lc_", "lut"), ("m9k_", "m9k"), ("mac_", "mac"), ("pad_", "pad"), ("pll_", "pll")):
        if oid.startswith(p):
            return k
    raise ValueError(f"unknown physical id form: {oid}")


def _split_top(s):
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


def evidence_of(raw):
    """blocks.json evidence string -> cross-repo citation tokens (doc:/issue:) + issue:98.
    Each top-level ';'-piece kept as a doc: token (internal ';' -> ',' so it survives the ';' re-split);
    GitHub '#NNN' refs surfaced as issue: tokens, order-preserving."""
    raw = raw or ""
    toks = [f"doc:{p.replace(';', ',')}" for p in _split_top(raw)]
    for n in dict.fromkeys(re.findall(r"#(\d+)", raw)):
        toks.append(f"issue:{n}")
    toks.append("issue:98")
    return ";".join(dict.fromkeys(toks))      # order-preserving dedup (raw '#98' + the appended issue:98)


def claim_of(name, conf, note):
    c = (note or "").strip() or f"DJI-functional block {name}"
    if conf == "S":
        c = f"[DJI confidence S: structural / table inference] {c}"
    return c


def record(name, conf, evidence, note, seeds, labs=None):
    """Writer-facing: a block record (seeds in blocks.json shape) -> the canonical TSV-row dict.
    `evidence` is the raw blocks.json evidence string; it is converted to the cross-repo citation here."""
    ms = members_of(name, seeds)
    return dict(name=name, kind=kind_of(name), tag=TAG[conf], n_members=len(ms),
                evidence=evidence_of(evidence), claim=claim_of(name, conf, note),
                members=[(m, "") for m in ms], labs=[list(t) for t in (labs or seeds.get("labs", []))])


# ---- low-level TSV read/write --------------------------------------------------------------------------------------

def _rows(path):
    if not os.path.isfile(path):
        return
    with open(path) as f:
        hdr = f.readline().rstrip("\n").split("\t")
        for line in f:
            yield dict(zip(hdr, line.rstrip("\n").split("\t")))


_clean = lambda v: str(v).replace("\t", " ").replace("\n", " ")


def read_blocks(board_dir):
    """-> ordered list of records {name, kind, tag, n_members, evidence, claim, members[(id,alias)], labs[[x,y]]}.
    Row order is load-bearing: Partition.seed() resolves seed conflicts by block order (first-wins)."""
    blocks, order = {}, []
    for r in _rows(os.path.join(board_dir, BLOCKS)):
        r["n_members"] = int(r["n_members"]) if r.get("n_members") else 0
        r["members"], r["labs"] = [], []
        blocks[r["name"]] = r
        order.append(r["name"])
    for r in _rows(os.path.join(board_dir, MEMBERS)):
        blocks[r["name"]]["members"].append((r["physical_id"], r.get("alias", "") or ""))
    for r in _rows(os.path.join(board_dir, LABS)):
        if r["name"] in blocks:
            blocks[r["name"]]["labs"].append([int(r["lab_x"]), int(r["lab_y"])])
    return [blocks[n] for n in order]


def write_blocks(board_dir, records):
    """Rewrite functional_blocks.tsv + functional_members.tsv + functional_labs.tsv from records (order preserved)."""
    os.makedirs(board_dir, exist_ok=True)
    with open(os.path.join(board_dir, BLOCKS), "w") as f:
        f.write("name\tkind\ttag\tn_members\tevidence\tclaim\n")
        for b in records:
            f.write("\t".join(_clean(b[k]) for k in ("name", "kind", "tag", "n_members", "evidence", "claim")) + "\n")
    with open(os.path.join(board_dir, MEMBERS), "w") as f:
        f.write("name\tobj_kind\tphysical_id\talias\n")
        for b in records:
            for mid, al in b["members"]:
                f.write(f"{_clean(b['name'])}\t{_obj_kind(mid)}\t{mid}\t{_clean(al)}\n")
    with open(os.path.join(board_dir, LABS), "w") as f:
        f.write("name\tlab_x\tlab_y\n")
        for b in records:
            for x, y in b.get("labs", []):
                f.write(f"{_clean(b['name'])}\t{x}\t{y}\n")


def read_rename(board_dir):
    return {r["from"]: r["to"] for r in _rows(os.path.join(board_dir, RENAME))}


def write_rename(board_dir, rename):
    with open(os.path.join(board_dir, RENAME), "w") as f:
        f.write("from\tto\n")
        for k, v in rename.items():
            f.write(f"{_clean(k)}\t{_clean(v)}\n")


def read_proposed(board_dir):
    out = []
    for r in _rows(os.path.join(board_dir, PROPOSED)):
        if r.get("model_confidence"):
            try:
                r["model_confidence"] = float(r["model_confidence"])
            except ValueError:
                pass
        out.append(r)
    return out


def write_proposed(board_dir, proposed):
    with open(os.path.join(board_dir, PROPOSED), "w") as f:
        f.write("\t".join(PROPOSED_COLS) + "\n")
        for r in proposed:
            f.write("\t".join(_clean(r.get(c, "")) for c in PROPOSED_COLS) + "\n")


# ---- read-path: TSVs -> blocks.json shape --------------------------------------------------------------------------

def load(board_dir):
    """Rebuild the seed-record shape {blocks:[...+seeds], rename:{}, proposed:[]} for partition.py.
    Seeds reconstructed from members: ff_/lc_ verbatim, pad_<ball>-><ball>, m9k_x_y/mac_x_y->[x,y];
    labs from the sidecar. pll_ members (clock_infra) have no blocks.json seed category -> dropped."""
    blocks = []
    for b in read_blocks(board_dir):
        seeds = dict(ffs=[], luts=[], labs=[list(t) for t in b["labs"]], m9k=[], mac=[], pads=[])
        for pid, _ in b["members"]:
            if pid.startswith("ff_"):
                seeds["ffs"].append(pid)
            elif pid.startswith("lc_"):
                seeds["luts"].append(pid)
            elif pid.startswith("pad_"):
                seeds["pads"].append(pid[len("pad_"):])
            elif pid.startswith(("m9k_", "mac_")):
                x, y = map(int, pid.split("_")[1:3])
                seeds["m9k" if pid.startswith("m9k_") else "mac"].append([x, y])
        for k in ("ffs", "luts", "pads"):
            seeds[k] = sorted(set(seeds[k]))
        for k in ("labs", "m9k", "mac"):
            seeds[k] = [list(t) for t in sorted({tuple(v) for v in seeds[k]})]
        blocks.append(dict(name=b["name"], confidence=CONF.get(b["tag"], b["tag"]),
                           evidence=b["evidence"], note=b["claim"], seeds=seeds))
    return dict(blocks=blocks, rename=read_rename(board_dir), proposed=read_proposed(board_dir))
