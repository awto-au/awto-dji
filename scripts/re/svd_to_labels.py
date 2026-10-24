#!/usr/bin/env python3
"""Flatten a CMSIS-SVD file into a (address, label) TSV for Ghidra labelling.

Resolves `derivedFrom` (e.g. UART1/2/3 derive their register layout from UART0, just at a
different baseAddress) - the SVD stores the register list once on the base peripheral and
every derived sibling just repeats the offsets, so a naive per-peripheral walk misses them.

Used for awto-dji#39 (m1400, LPC1765): the register-labelling input for
scripts/re/ghidra/DumpLPC17xx.java, so the Ghidra pass gets [spec]-grade peripheral/register
names instead of re-deriving them from the datasheet by hand.

Usage: python3 -I scripts/re/svd_to_labels.py --svd PATH --out PATH
Log: ./tmp/logs/svd_to_labels.log
"""
from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--svd", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    svd_path = Path(args.svd)
    out_path = Path(args.out)
    tree = ET.parse(svd_path)
    peripherals = tree.findall(".//peripheral")

    by_name = {p.find("name").text: p for p in peripherals}
    rows: list[tuple[int, str]] = []

    for p in peripherals:
        name = p.find("name").text
        base = int(p.find("baseAddress").text, 0)
        regs_el = p.find("registers")
        if regs_el is None:
            derived = p.attrib.get("derivedFrom")
            if derived and derived in by_name:
                regs_el = by_name[derived].find("registers")
        if regs_el is None:
            log(f"{name}: no registers (and no resolvable derivedFrom)", level="WARN")
            continue
        for reg in regs_el.findall("register"):
            rname = reg.find("name").text
            off = int(reg.find("addressOffset").text, 0)
            rows.append((base + off, f"{name}_{rname}"))

    rows.sort()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        fh.write("address\tlabel\n")
        for addr, label in rows:
            fh.write(f"0x{addr:08X}\t{label}\n")

    log(f"wrote {len(rows)} register labels from {svd_path} to {out_path}")
    print(f"{len(rows)} labels -> {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
