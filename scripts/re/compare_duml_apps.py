#!/usr/bin/env python3
"""Diff two or more DUML class tables (from extract_duml_classes.py) to find where
DJI apps agree or disagree on a command's cmdset/cmdid/payload layout - the actually
interesting output when checking whether a protocol assumption holds across apps.

Usage:
    python3 -I scripts/re/compare_duml_apps.py tmp/apk/duml_tables/dji.go.v4.json \
        tmp/apk/duml_tables/dji.pilot.json [more.json ...]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402


def load(path: Path) -> dict:
    return {r["class"]: r for r in json.loads(path.read_text())}


def same_fields(a: list, b: list) -> bool:
    return [(f["offset"], f["length"]) for f in a] == [(f["offset"], f["length"]) for f in b]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tables", nargs="+", type=Path)
    args = ap.parse_args()

    names = [p.stem for p in args.tables]
    tables = {name: load(p) for name, p in zip(names, args.tables)}
    all_classes = sorted(set().union(*[set(t) for t in tables.values()]))

    only_in = {name: [] for name in names}
    agree = []
    diverge = []

    for cls in all_classes:
        present = {name: tables[name].get(cls) for name in names}
        have = [name for name, r in present.items() if r is not None]
        if len(have) == 1:
            only_in[have[0]].append(cls)
            continue
        records = [present[name] for name in have]
        # Only compare where every app's extraction was confident (V) - a mismatch
        # against a U record is noise from the extractor, not a real app difference.
        if any(r["confidence"] != "V" for r in records):
            continue
        base = records[0]
        matches = all(
            r["cmdset"] == base["cmdset"] and r["cmdid"] == base["cmdid"]
            and same_fields(r["fields"], base["fields"])
            for r in records[1:]
        )
        if matches:
            agree.append(cls)
        else:
            diverge.append({"class": cls, "by_app": {name: present[name] for name in have}})

    log(f"apps compared: {names}")
    log("classes in exactly one app: " + ", ".join(f"{name}={len(v)}" for name, v in only_in.items()))
    log(f"classes in >1 app, both V-confidence, fully agree: {len(agree)}")
    log(f"classes in >1 app, both V-confidence, DIVERGE: {len(diverge)}")
    for d in diverge:
        log(f"--- {d['class']} ---")
        for name, r in d["by_app"].items():
            log(f"  {name}: cmdset={r['cmdset']} cmdid={r['cmdid']} "
                f"fields={[(f['offset'], f['length']) for f in r['fields']]}")


if __name__ == "__main__":
    main()
