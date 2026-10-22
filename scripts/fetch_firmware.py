#!/usr/bin/env python3
"""Download DJI xV4 firmware packages for every product, into firmware/raw/.

Source of truth: dji-firmware-tools' supported_firmwares_xv4.csv (product,
binary file, download page, download link, download name, test flags,
publish date, size, comment). One session's worth of download URLs, already
collected by that project from DJI's CDN.

Default: latest publish date per product (one FPGA/board sample per product
family is enough for cross-product pattern matching). --all-versions fetches
every listed file instead.

Usage:
    python3 scripts/fetch_firmware.py --csv /mnt/2tb/git/dji-firmware-tools/supported_firmwares_xv4.csv
    python3 scripts/fetch_firmware.py --csv ... --all-versions
    python3 scripts/fetch_firmware.py --csv ... --product P3X C1 WM610
"""
import argparse
import csv
import hashlib
import logging
import os
import subprocess
import sys
import time
import urllib.request
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
    logger = logging.getLogger("fetch_firmware")
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    fh = logging.FileHandler(log_path)
    fh.setFormatter(fmt)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(fh)
    logger.addHandler(sh)
    return logger


def load_entries(csv_path: Path):
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader if row.get("download link")]


def pick_latest_per_product(rows):
    best = {}
    for row in rows:
        product = row["product"]
        date = row.get("publish date") or ""
        cur = best.get(product)
        if cur is None or date > (cur.get("publish date") or ""):
            best[product] = row
    return list(best.values())


# This project's HTTP timeout: DJI's S3 CDN serves firmware files up to ~110 MB
# (go4.apk-sized outliers aside; firmware itself tops out ~75 MB for WM610).
# Measured single-file transfer on this link is well under 60s even for the
# largest entries; 120s is ~2x that observed worst case, not a round number.
REQUEST_TIMEOUT_S = 120


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_one(row, dest_dir: Path, logger: logging.Logger, retries: int = 3):
    product = row["product"]
    url = row["download link"]
    name = row.get("download name") or row.get("binary file") or os.path.basename(url)
    out_dir = dest_dir / product
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / name

    expected_size = None
    size_field = row.get("bin file size [B]")
    if size_field:
        try:
            expected_size = int(size_field)
        except ValueError:
            pass

    if out_path.exists():
        if expected_size and out_path.stat().st_size == expected_size:
            logger.info(f"SKIP {product}/{name} (already present, size matches)")
            return out_path, None
        if not expected_size:
            logger.info(f"SKIP {product}/{name} (already present)")
            return out_path, None

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            logger.info(f"GET {product}/{name} <- {url} (attempt {attempt}/{retries})")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp, open(out_path, "wb") as f:
                f.write(resp.read())
            size = out_path.stat().st_size
            if expected_size and size != expected_size:
                logger.warning(
                    f"SIZE MISMATCH {product}/{name}: got {size}, expected {expected_size}"
                )
            digest = sha256_file(out_path)
            logger.info(f"OK {product}/{name} size={size} sha256={digest}")
            return out_path, digest
        except Exception as exc:
            last_err = exc
            logger.warning(f"FAIL {product}/{name} attempt {attempt}: {exc}")
            if out_path.exists():
                out_path.unlink()
    logger.error(f"GIVE UP {product}/{name}: {last_err}")
    return None, None


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", required=True, type=Path,
                     help="path to dji-firmware-tools supported_firmwares_xv4.csv")
    ap.add_argument("--all-versions", action="store_true",
                     help="fetch every listed version, not just the latest per product")
    ap.add_argument("--product", nargs="*", default=None,
                     help="restrict to these product codes (e.g. P3X C1 WM610)")
    ap.add_argument("--dest", type=Path, default=None,
                     help="override destination dir (default: <repo>/firmware/raw)")
    args = ap.parse_args()

    root = repo_root()
    dest_dir = args.dest or (root / "firmware" / "raw")
    log_path = root / "tmp" / "logs" / "fetch_firmware.log"
    logger = setup_logging(log_path)

    rows = load_entries(args.csv)
    logger.info(f"Loaded {len(rows)} entries with download links from {args.csv}")

    if args.product:
        wanted = set(args.product)
        rows = [r for r in rows if r["product"] in wanted]
        logger.info(f"Filtered to products {sorted(wanted)}: {len(rows)} entries")

    if not args.all_versions:
        rows = pick_latest_per_product(rows)
        logger.info(f"Latest-per-product selection: {len(rows)} entries")

    rows.sort(key=lambda r: (r["product"], r.get("publish date") or ""))

    manifest_rows = []
    ok, failed, skipped = 0, 0, 0
    for row in rows:
        out_path, digest = download_one(row, dest_dir, logger)
        if out_path is None:
            failed += 1
            continue
        if digest is None:
            skipped += 1
            digest = sha256_file(out_path)
        else:
            ok += 1
        manifest_rows.append({
            "product": row["product"],
            "file": out_path.name,
            "sha256": digest,
            "size": out_path.stat().st_size,
            "publish_date": row.get("publish date") or "",
            "source_url": row["download link"],
        })

    manifest_path = dest_dir / "MANIFEST.csv"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["product", "file", "sha256", "size", "publish_date", "source_url"])
        w.writeheader()
        for r in sorted(manifest_rows, key=lambda r: (r["product"], r["file"])):
            w.writerow(r)

    logger.info(f"Done. ok={ok} skipped={skipped} failed={failed} manifest={manifest_path}")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
