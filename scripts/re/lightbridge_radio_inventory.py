#!/usr/bin/env python3
"""Hash-pinned ground/air radio-script inventory for #87 (static, not a simulator).

Exports register-setting facts and summaries. Full ordered traces stay in tmp/.
Unknown read-dependent values are symbolic, never invented from a table literal.
"""
import argparse
from collections import Counter, defaultdict
import csv
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HASHES = {
    "air": "72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d",
    "ground": "43bc7d6cb9f9c916dcfee0146378a3a6c823d0c65ac9613ca5adecae25f9d93f",
}
# Every offset here is a FILE offset. Ground flash addresses add 0xA000;
# air flash addresses add 0x08008000. Bounds come from the firmware loops.
PROFILES = [
    ("air_ad_boards_2_4_5", "air", 0xE660, 0x293C),
    ("ground_mode3", "ground", 0x1D1D4, 0x313C),
    ("ground_mode1", "ground", 0x20C2C, 0x313C),
]


def verified_image(path, kind):
    data = path.read_bytes()
    actual = hashlib.sha256(data).hexdigest()
    if actual != HASHES[kind]:
        raise ValueError(f"{path}: unexpected {kind} firmware SHA-256 {actual}")
    return data


def records(image, offset, size):
    if offset < 0 or size % 4 or offset + size > len(image):
        raise ValueError("script bounds outside firmware or not 4-byte aligned")
    for i in range(offset, offset + size, 4):
        op, a, b, c = image[i:i + 4]
        if op not in (5, 6, 7, 8, 9, 10, 11, 12, 13):
            raise ValueError(f"unrecognised record at {i:#x}: {op:#x}")
        yield {"file_offset": f"0x{i:x}", "op": op, "a": a, "b": b, "c": c}


def analyse(rows):
    final, history = {}, defaultdict(list)
    gain, fir = {}, {"tx": {}, "rx": {}}
    gain_index, gain_word = None, {}
    fir_index, fir_words = {}, defaultdict(dict)
    for row in rows:
        if row["op"] != 6:
            continue
        reg, value = ((row["a"] & 0x7F) << 8) | row["b"], row["c"]
        applied = "(cached_read_0x0A3 & 0x3f) | 0x40" if reg == 0x0A3 else f"0x{value:02x}"
        final[reg] = {"table_literal": f"0x{value:02x}", "applied": applied, "file_offset": row["file_offset"]}
        history[reg].append((row["file_offset"], value))
        if reg == 0x130:
            gain_index, gain_word = value, {}
        elif reg in (0x131, 0x132, 0x133):
            gain_word[reg] = value
        elif reg == 0x137 and gain_index is not None and len(gain_word) == 3:
            gain[gain_index] = tuple(gain_word[x] for x in (0x131, 0x132, 0x133))
        for side, base in (("tx", 0x060), ("rx", 0x0F0)):
            if reg == base:
                fir_index[side] = value
            elif reg in (base + 1, base + 2):
                fir_words[side][reg - base] = value
            elif reg == base + 5 and value & 2 and side in fir_index and len(fir_words[side]) == 2:
                code = fir_words[side][1] | (fir_words[side][2] << 8)
                fir[side][fir_index[side]] = code - 65536 if code >= 32768 else code
    def digest(values):
        return hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()
    fir_detail = {}
    for side, values in fir.items():
        ordered = [values[i] for i in sorted(values)]
        config = int(final[0x065 if side == "tx" else 0x0F5]["table_literal"], 16)
        taps = 16 * (((config >> 5) & 7) + 1)
        active = [values[i] for i in range(taps)] if all(i in values for i in range(taps)) else []
        fir_detail[side] = {
            "loaded_index_range": [min(values), max(values)] if values else [], "coefficient_count": len(values),
            "loaded_symmetric": bool(values) and ordered == list(reversed(ordered)),
            "configured_taps": taps, "active_symmetric": bool(active) and active == list(reversed(active)),
            "fingerprint_json_sha256": digest(sorted(values.items())),
        }
    detail = {
        "record_count": len(rows), "op_counts": dict(sorted(Counter(r["op"] for r in rows).items())),
        "distinct_radio_registers": len(final),
        "register_history": {f"0x{r:03x}": h for r, h in sorted(history.items())},
        "gain_entries": len(gain), "gain_index_range": [min(gain), max(gain)] if gain else [],
        "gain_fingerprint_json_sha256": digest(sorted(gain.items())),
        "fir": fir_detail,
        "tx_rx_fir_equal": fir["tx"] == fir["rx"] and bool(fir["tx"]),
    }
    return final, detail, gain


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--air", type=Path, default=ROOT / "firmware/P3X_FW_V01.11.0020_m0900.bin")
    ap.add_argument("--ground", type=Path, default=ROOT / "firmware/C1_FW_V01.06.0000_m1400.bin")
    ap.add_argument("--adi-source", type=Path, help="optional public ADI no-OS ad9361.c for gain-table comparison")
    ap.add_argument("--out", type=Path, default=ROOT / "docs/data")
    a = ap.parse_args()
    images = {"air": verified_image(a.air, "air"), "ground": verified_image(a.ground, "ground")}
    names = {}
    for line in (ROOT / "scripts/re/ad9361_regs.tsv").read_text().splitlines():
        if line and not line.startswith("#"):
            addr, name, *_ = line.split("\t")
            names[int(addr, 16)] = name
    traces = ROOT / "tmp/radio-inventory"
    traces.mkdir(parents=True, exist_ok=True)
    summary, maps = {"firmware_sha256": HASHES, "evidence": "static script values, not hardware capture", "profiles": {}}, {}
    adi = None
    if a.adi_source:
        text = a.adi_source.read_text()
        part = text.split("static const uint8_t full_gain_table", 1)[1].split("static const uint8_t split_gain_table", 1)[0]
        adi = [tuple(int(x, 16) for x in t) for t in re.findall(r"\{(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+),\s*(0x[0-9a-fA-F]+)\}", part)]
        if len(adi) != 231:
            raise ValueError("unexpected ADI gain-table layout; expected 3 x 77 entries")
        summary["adi_source_sha256"] = hashlib.sha256(a.adi_source.read_bytes()).hexdigest()
    for label, kind, offset, size in PROFILES:
        rows = list(records(images[kind], offset, size))
        maps[label], detail, gain = analyse(rows)
        # Complete ordered operation log is generated locally, not a firmware dump in git.
        (traces / f"{label}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        detail.update({"file_offset": f"0x{offset:x}", "byte_length": size})
        if adi:
            detail["adi_full_gain_table_aligned_matches"] = {str(band): sum(gain.get(i) == item for i, item in enumerate(adi[band * 77:(band + 1) * 77])) for band in range(3)}
        summary["profiles"][label] = detail
    a.out.mkdir(parents=True, exist_ok=True)
    # Keep the full write history local. Publish setting facts plus first/last source locations.
    for label, detail in summary["profiles"].items():
        (traces / f"{label}-history.json").write_text(json.dumps(detail["register_history"], indent=2) + "\n")
        del detail["register_history"]
    with (a.out / "lightbridge-radio-registers.tsv").open("w") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        labels = list(maps)
        writer.writerow(["register", "name"] + [f"{label}_{field}" for label in labels for field in ("table_literal", "applied", "file_offset")])
        for reg in sorted(set().union(*(set(m) for m in maps.values()))):
            writer.writerow([f"0x{reg:03x}", names.get(reg, "UNKNOWN")] + [maps[label].get(reg, {}).get(field, "") for label in labels for field in ("table_literal", "applied", "file_offset")])
    # Inventory the remaining ground branches without pretending their register map is AD9363.
    summary["other_ground_profiles"] = [{"label": label, "file_offset": f"0x{offset:x}", "record_count": len(list(records(images["ground"], offset, size)))} for label, offset, size in (("mode0_unidentified_map", 0x20310, 0x91C), ("mode3_conditional_fpga_overlay", 0x23D68, 0x64))]
    (a.out / "lightbridge-radio-inventory.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({label: {k: v for k, v in detail.items() if k in ("record_count", "distinct_radio_registers", "gain_entries", "adi_full_gain_table_aligned_matches", "tx_rx_fir_equal")} for label, detail in summary["profiles"].items()}, indent=2))


if __name__ == "__main__":
    main()
