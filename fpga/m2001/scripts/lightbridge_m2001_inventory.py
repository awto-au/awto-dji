#!/usr/bin/env python3
"""Inventory and deduplicate m2001 modules in DJI xV4 firmware containers.

The script reads containers in place and never extracts proprietary payloads.  It prints
one TSV row per m2001 entry followed by hash groups, and can write the same facts as JSON.

Usage:
  python3 scripts/lightbridge_m2001_inventory.py /path/to/firmware/raw [--json report.json]
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct

XV4_MAGIC = 0x12345678
ENTRY_BASE = 0x40
ENTRY_SIZE = 0x34


def m2001_entry(path):
    with path.open("rb") as f:
        header = f.read(0x10000)
        if len(header) < ENTRY_BASE or struct.unpack_from("<I", header, 0)[0] != XV4_MAGIC:
            return None
        count = struct.unpack_from("<H", header, 0x2C)[0]
        for index in range(count):
            off = ENTRY_BASE + index * ENTRY_SIZE
            if off + ENTRY_SIZE > len(header):
                raise ValueError(f"truncated xV4 entry table: {path}")
            target = header[off]
            name = "m%02d%02d" % (target & 0x1F, target >> 5)
            if name != "m2001":
                continue
            version, data_off, stored_len, alloc_len = struct.unpack_from("<IIII", header, off + 4)
            f.seek(data_off)
            remaining = stored_len
            digest = hashlib.sha256()
            while remaining:
                block = f.read(min(1 << 20, remaining))
                if not block:
                    raise ValueError(f"truncated m2001 payload: {path}")
                digest.update(block)
                remaining -= len(block)
            return {
                "path": str(path),
                "entry_version": f"0x{version:08x}",
                "stored_len": stored_len,
                "alloc_len": alloc_len,
                "sha256": digest.hexdigest(),
            }
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="file or directory containing DJI xV4 containers")
    parser.add_argument("--json", type=Path, help="optional JSON report path")
    args = parser.parse_args()

    paths = [args.root] if args.root.is_file() else sorted(p for p in args.root.rglob("*") if p.is_file())
    rows = []
    containers = 0
    for path in paths:
        try:
            with path.open("rb") as f:
                magic = f.read(4)
            if len(magic) != 4 or struct.unpack("<I", magic)[0] != XV4_MAGIC:
                continue
            containers += 1
            row = m2001_entry(path)
            if row:
                rows.append(row)
        except (OSError, struct.error, ValueError) as exc:
            raise SystemExit(str(exc)) from exc

    groups = {}
    for row in rows:
        groups.setdefault(row["sha256"], []).append(row["path"])
    report = {
        "root": str(args.root),
        "xv4_containers": containers,
        "m2001_entries": len(rows),
        "unique_m2001": len(groups),
        "entries": rows,
        "groups": groups,
    }

    print("path\tentry_version\tstored_len\talloc_len\tsha256")
    for row in rows:
        print("{path}\t{entry_version}\t{stored_len}\t{alloc_len}\t{sha256}".format(**row))
    print(f"SUMMARY\txv4={containers}\tm2001={len(rows)}\tunique={len(groups)}")
    for digest, members in groups.items():
        print(f"GROUP\t{digest}\t{len(members)}")
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
