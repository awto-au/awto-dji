#!/usr/bin/env python3
"""Full UBIFS extraction of the camera (m0100) `rfs` partition - issue #35.

Reuses the UBI/UBIFS walker in air_survey.py (read-only, untrusted input) but
writes EVERY reconstructed file/symlink, not just the hand-picked subset
scripts/re/fpga_write_path.py pulled for its own (different) task.

Input : tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_rfs.a9s (26 MB UBI image,
        already split from m0100 by amba_fwpak via air_survey.py's amba_extract())
Output: tmp/air/rfs_P3X0020_full/<rootfs tree>, tmp/logs/rfs_full_extract.log
Run   : python3 -I scripts/re/rfs_full_extract.py   (local file IO only, no network)
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import air_survey as A  # noqa: E402  (ubi_volumes/ubifs_tree walker + repo_root)

ROOT = A.repo_root()
RFS = os.path.join(ROOT, "tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_rfs.a9s")
OUT = os.path.join(ROOT, "tmp/air/rfs_P3X0020_full")
LOG = os.path.join(ROOT, "tmp/logs/rfs_full_extract.log")


def log(lines, *a):
    line = " ".join(str(x) for x in a)
    lines.append(line)
    print(line)


def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    lines = []
    t0 = time.time()
    img = open(RFS, "rb").read()
    log(lines, f"input {RFS} size={len(img)}")
    vols, leb_size = A.ubi_volumes(img)
    log(lines, f"UBI volumes found: {sorted(vols.keys())} leb_size={leb_size}")
    for vol_id, vol in sorted(vols.items()):
        log(lines, f"  vol {vol_id}: {len(vol)} LEBs")

    total_files, total_links = {}, {}
    for vol_id, vol in sorted(vols.items()):
        try:
            files, links = A.ubifs_tree(vol)
        except Exception as e:
            log(lines, f"  vol {vol_id}: ubifs_tree failed: {e}")
            continue
        log(lines, f"  vol {vol_id}: UBIFS tree -> {len(files)} files, {len(links)} symlinks")
        if len(files) > len(total_files):
            total_files, total_links = files, links  # the real rootfs volume dominates

    log(lines, f"selected volume: {len(total_files)} files, {len(total_links)} symlinks")

    n_written = 0
    for path, data in sorted(total_files.items()):
        dst = OUT + path
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(data)
        n_written += 1
    with open(os.path.join(OUT, "_SYMLINKS.txt"), "w") as f:
        for path, target in sorted(total_links.items()):
            f.write(f"{path} -> {target}\n")

    log(lines, f"wrote {n_written} files + {len(total_links)} symlinks to {OUT} in {time.time()-t0:.1f}s")
    with open(LOG, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
