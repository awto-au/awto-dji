#!/usr/bin/env python3
"""Unpack every downloaded DJI firmware, find FPGA-candidate modules, decode
each against every Mistral Cyclone-V die, and log resolved-route fractions.

Goal: the air Lightbridge FPGA (m1900, P3X) has an unidentified die (see
awto-au/awto-dji#3). If any other DJI product's FPGA module decodes cleanly
against a known die, that narrows which Cyclone-V family DJI used across the
Lightbridge line, even without physical hardware access to m1900's board.

FPGA-candidate heuristic: module >= 512 KiB (MCU firmware modules are smaller;
FPGA bitstreams for this era are multi-MB) AND NOT a known non-FPGA target
(m0100/m0101 camera Linux, m0800 video codec Linux, which are also large).

Usage:
    python3 scripts/fpga_corpus_scan.py
"""
import argparse
import csv
import json
import logging
import os
import re
import struct
import subprocess
import sys
from pathlib import Path


def repo_root() -> Path:
    env = os.environ.get("AWTO_DJI_REPO")
    if env:
        return Path(env)
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except Exception:
        return Path(__file__).resolve().parent.parent


def setup_logging(log_path: Path) -> logging.Logger:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("fpga_corpus_scan")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


# Non-FPGA targets known to also produce large modules (Linux SoC images),
# so size alone would misclassify them. From docs/firmware-overview.md module map.
# m1301 (DaVinci Dm385 Linux video decoder) confirmed by this scan: saturates every
# Mistral die at 100% resolved (large generic binary data, not a real bitstream match).
NON_FPGA_LARGE_TARGETS = {"m0100", "m0101", "m0800", "m1300", "m1301"}
MIN_FPGA_SIZE = 512 * 1024

# Mistral's 7 unique Cyclone-V dies (from libmistral/generator.cc cinfo table),
# one representative orderable part per die for the `models`/`routes` CLI arg.
DIES = {
    "e50f": "5CEBA4U19C8",
    "gt75f": "5CEBA5U19C8",
    "gt150f": "5CEBA7U19C8",
    "gt300f": "5CEBA9U19C8",
    "gx25f": "5CGXFC3B6U19C7",
    "sx50f": "5CSEBA4U19C8",
    "sx120f": "5CSEBA6U19C7",
}


def unpack_firmware(fwcon_py: Path, bin_path: Path, out_dir: Path, logger: logging.Logger):
    out_dir.mkdir(parents=True, exist_ok=True)
    venv_python = fwcon_py.parent / ".venv" / "bin" / "python3"
    python_bin = str(venv_python) if venv_python.exists() else sys.executable
    try:
        result = subprocess.run(
            [python_bin, str(fwcon_py), "-x", "-p", str(bin_path)],
            cwd=out_dir, capture_output=True, text=True, timeout=120,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"UNPACK TIMEOUT {bin_path.name}")
        return False
    if result.returncode != 0:
        logger.warning(f"UNPACK FAIL {bin_path.name}: {result.stderr[-500:]}")
        return False
    return True


def find_fpga_candidates(out_dir: Path):
    candidates = []
    for ini in out_dir.glob("*_m*.ini"):
        text = ini.read_text(errors="replace")
        m = re.search(r"target\s*=\s*(m\d+)", text)
        if not m:
            continue
        target = m.group(1)
        bin_path = ini.with_suffix(".bin")
        if not bin_path.exists():
            continue
        size = bin_path.stat().st_size
        if size < MIN_FPGA_SIZE or target in NON_FPGA_LARGE_TARGETS:
            continue
        name_m = re.search(r"Stores firmware for (.+)", text)
        candidates.append((target, bin_path, size, name_m.group(1).strip() if name_m else ""))
    return candidates


def depack(bin_path: Path, out_path: Path, logger: logging.Logger):
    data = bin_path.read_bytes()
    i = 0
    while i < len(data) and data[i] == 0xFF:
        i += 1
    j = len(data) - 1
    while j >= 0 and data[j] == 0xFF:
        j -= 1
    if j + 1 <= i:
        logger.warning(f"DEPACK EMPTY {bin_path.name}: all-0xFF or inverted bounds")
        return None
    payload = data[i:j + 1]
    out_path.write_bytes(payload)
    return i, j + 1, len(payload)


def resolved_fraction(mistral_cv: Path, die_part: str, rbf_path: Path, logger: logging.Logger, timeout=120):
    try:
        result = subprocess.run(
            [str(mistral_cv), "routes", die_part, str(rbf_path)],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        logger.warning(f"DECODE TIMEOUT die={die_part} file={rbf_path.name}")
        return None
    lines = result.stdout.splitlines() or result.stderr.splitlines()
    total = len(lines)
    unresolved = sum(1 for l in lines if l.startswith("Source unknown"))
    if total == 0:
        return None
    return {"total": total, "resolved": total - unresolved, "fraction": (total - unresolved) / total}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fwcon", type=Path,
                     default=Path("/mnt/2tb/git/dji-firmware-tools/dji_xv4_fwcon.py"))
    ap.add_argument("--mistral-cv", type=Path,
                     default=Path("/mnt/2tb/git/mistral/build/mistral-cv/mistral-cv"))
    args = ap.parse_args()

    root = repo_root()
    raw_root = root / "firmware" / "raw"
    unpacked_root = root / "firmware" / "unpacked" / "corpus_scan"
    log_path = root / "tmp" / "logs" / "fpga_corpus_scan.log"
    results_path = root / "tmp" / "fpga_corpus_scan_results.json"
    logger = setup_logging(log_path)

    # One file per product directory (the largest .bin — DJI packages are usually a
    # single real firmware file per product dir; avoids rescanning every historical
    # version, e.g. C1's 49 versions, when one representative is enough per product).
    fw_rows = []
    for product_dir in sorted(p for p in raw_root.iterdir() if p.is_dir()):
        bins = sorted(product_dir.glob("*.bin"), key=lambda p: p.stat().st_size, reverse=True)
        if not bins:
            continue
        fw_rows.append({"product": product_dir.name, "file": bins[0].name})
    logger.info(f"{len(fw_rows)} products with firmware under {raw_root}")

    all_results = []
    for row in fw_rows:
        product = row["product"]
        bin_path = (root / "firmware" / "raw" / product / row["file"])
        if not bin_path.exists():
            logger.warning(f"MISSING {bin_path}")
            continue
        out_dir = unpacked_root / product
        if not any(out_dir.glob("*_head.ini")):
            logger.info(f"UNPACK {product}/{row['file']}")
            if not unpack_firmware(args.fwcon, bin_path, out_dir, logger):
                continue

        candidates = find_fpga_candidates(out_dir)
        if not candidates:
            logger.info(f"{product}: no FPGA-candidate modules")
            continue

        for target, mod_bin, size, desc in candidates:
            logger.info(f"{product}/{target} ({desc}): {size} bytes — depacking")
            depack_path = out_dir / f"{target}.depack.bin"
            bounds = depack(mod_bin, depack_path, logger)
            if bounds is None:
                continue
            start, end, plen = bounds
            logger.info(f"{product}/{target}: payload {plen} bytes [{hex(start)}:{hex(end)}]")

            die_results = {}
            for die_name, die_part in DIES.items():
                r = resolved_fraction(args.mistral_cv, die_part, depack_path, logger)
                if r:
                    logger.info(f"{product}/{target} die={die_name}: "
                                f"{r['resolved']}/{r['total']} ({r['fraction']:.1%})")
                    die_results[die_name] = r

            best_die = max(die_results, key=lambda d: die_results[d]["fraction"]) if die_results else None
            fractions = [r["fraction"] for r in die_results.values()]
            # Noise signature: every die resolves near-100% (real bitstreams are
            # fabric-specific — a genuine match stands out sharply from the rest,
            # the way m2001/e50f did at 56337/443322 vs <1% on other dies).
            all_saturated = bool(fractions) and min(fractions) > 0.95
            all_results.append({
                "product": product, "target": target, "desc": desc,
                "module_size": size, "payload_size": plen,
                "die_results": die_results, "best_die": best_die,
                "best_fraction": die_results[best_die]["fraction"] if best_die else None,
                "likely_noise": all_saturated,
            })

    results_path.write_text(json.dumps(all_results, indent=2))
    logger.info(f"Done. {len(all_results)} FPGA-candidate modules scanned. Results: {results_path}")

    print("\n=== Summary (best die per module) ===")
    for r in sorted(all_results, key=lambda r: -(r["best_fraction"] or 0)):
        if not r["best_die"]:
            print(f"{r['product']:15s} {r['target']:6s} {r['desc'][:35]:35s} no decode")
            continue
        flag = " [NOISE: saturates all dies]" if r["likely_noise"] else ""
        print(f"{r['product']:15s} {r['target']:6s} {r['desc'][:35]:35s} "
              f"best={r['best_die']:8s} {r['best_fraction']:.1%}{flag}")


if __name__ == "__main__":
    main()
