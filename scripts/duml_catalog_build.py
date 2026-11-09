#!/usr/bin/env python3
"""Reconcile the source-attributed DUML command tables into ONE canonical versioned catalog (#102).

Inputs (docs/data/, each source-attributed):
  apk-duml-commands.tsv   cmdset cmdid name direction payload status evidence   (DJI GO 4 APK)
  dll-duml-commands.tsv   cmdset cmdid name source status                        (DJI Windows DLLs)
  apk-cmdset-devicetype.tsv  kind name value source                              (CmdSet / DeviceType enums)
Output:
  docs/data/duml-catalog.json  — one entry per (cmdset, cmdid), merged, with per-source evidence.
The three language bindings (Dart app/packages/duml, Python, Rust) should generate from this, not
hand-copy. This is reconciliation + codegen, not authoring: the data already exists per-source.

  python3 scripts/duml_catalog_build.py [--out docs/data/duml-catalog.json]
Log: tmp/logs/duml_catalog_build.log.
"""
import argparse
import csv
import datetime
import json
import logging
import os
import re

ROOT = os.environ.get("DJI_REPO") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "docs", "data")
log = logging.getLogger("duml_catalog")


def rows(name):
    with open(os.path.join(DATA, name)) as f:
        yield from csv.DictReader(f, delimiter="\t")


def split_cmdset(s):
    """'0x00 general' -> ('0x00', 'general'). Tolerates a bare hex or a bare name."""
    s = (s or "").strip()
    parts = s.split(None, 1)
    if parts and parts[0].lower().startswith("0x"):
        return parts[0].lower(), (parts[1].strip() if len(parts) > 1 else None)
    return None, s or None


def norm_id(v):
    v = (v or "").strip()
    return v.lower() if v.lower().startswith("0x") else None       # '?' / blank -> unknown


def key(cset, cid, name):
    return (cset, cid) if cid else (cset, "?" + (name or "").strip().lower())


def provenance():
    """Firmware-version coverage: which firmware the APK's DUML command TABLE (sha256-matched) appears in.
    Table-level provenance (not per-command versioning); grounds the catalog against real firmware."""
    p = os.path.join(DATA, "duml-table-matches-2026-10-24.json")
    if not os.path.isfile(p):
        return None
    m = json.load(open(p))
    seen, vers = set(), []
    for x in m.get("matches", []):
        g = re.search(r"([A-Za-z0-9]+)_FW_(V\d+\.\d+\.\d+)", x.get("path", ""))
        if g and (g.group(1), g.group(2)) not in seen:
            seen.add((g.group(1), g.group(2)))
            vers.append({"model": g.group(1), "version": g.group(2), "path": x["path"], "sha256": x.get("sha256")})
    return dict(apk_library=m.get("apk_library"), table_sha256=m.get("table_sha256"), table_length=m.get("table_length"),
                firmware_versions=sorted(vers, key=lambda v: (v["model"], v["version"])))


def build():
    cmdsets, devtypes = {}, {}
    for r in rows("apk-cmdset-devicetype.tsv"):
        k, nm, val = r.get("kind"), r.get("name"), r.get("value")
        if k == "CmdSet" and val is not None:
            try:
                cmdsets[f"0x{int(val):02x}"] = nm
            except (ValueError, TypeError):
                pass
        elif k == "DeviceType" and val is not None:
            devtypes[val] = nm

    cat = {}
    for r in rows("apk-duml-commands.tsv"):
        cset, csname = split_cmdset(r["cmdset"])
        cid = norm_id(r["cmdid"])
        e = cat.setdefault(key(cset, cid, r["name"]), _blank(cset, csname or cmdsets.get(cset), cid))
        e["name"] = e["name"] or r["name"].strip()
        e["direction"] = e["direction"] or (r.get("direction") or "").strip() or None
        e["payload"] = e["payload"] or (r.get("payload") or "").strip() or None
        e["sources"].append({"origin": "apk", "name": r["name"].strip(),
                             "status": (r.get("status") or "").strip(), "evidence": (r.get("evidence") or "").strip()})
    for r in rows("dll-duml-commands.tsv"):
        cset, csname = split_cmdset(r["cmdset"])
        cid = norm_id(r["cmdid"])
        e = cat.setdefault(key(cset, cid, r["name"]), _blank(cset, csname or cmdsets.get(cset), cid))
        e["name"] = e["name"] or r["name"].strip()
        e["sources"].append({"origin": "dll", "name": r["name"].strip(),
                             "status": (r.get("status") or "").strip(), "evidence": (r.get("source") or "").strip()})

    cmds = sorted(cat.values(), key=lambda e: (e["cmdset"] or "", e["cmdid"] or "zzz", e["name"] or ""))
    return dict(schema=1, generated=datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
                generator="scripts/duml_catalog_build.py",
                note="Reconciled from docs/data/{apk,dll}-duml-commands.tsv + apk-cmdset-devicetype.tsv. "
                     "Canonical source for the Dart/Python/Rust DUML bindings (awto-dji #102). "
                     "Table provenance (firmware versions the command table is sha256-matched in) under 'table_provenance'.",
                table_provenance=provenance(),
                cmdsets=cmdsets, device_types=devtypes, n_commands=len(cmds), commands=cmds)


def _blank(cset, csname, cid):
    return dict(cmdset=cset, cmdset_name=csname, cmdid=cid, name=None, direction=None, payload=None, sources=[])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(DATA, "duml-catalog.json"))
    a = ap.parse_args()
    os.makedirs(os.path.join(ROOT, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(ROOT, "tmp", "logs", "duml_catalog_build.log"))])
    cat = build()
    json.dump(cat, open(a.out, "w"), indent=1)
    both = sum(1 for c in cat["commands"] if {s["origin"] for s in c["sources"]} >= {"apk", "dll"})
    known = sum(1 for c in cat["commands"] if c["cmdid"])
    log.info("duml-catalog: %d commands (%d with a known cmdid, %d corroborated by apk+dll), %d cmdsets -> %s",
             cat["n_commands"], known, both, len(cat["cmdsets"]), a.out)


if __name__ == "__main__":
    main()
