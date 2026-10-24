#!/usr/bin/env python3
"""Thin dji.pilot-specific wrapper over scripts/re/apk_memscan.py (generalized
2026-10-24). Kept for backward compat with existing invocations/output paths
(tmp/apk/pilot_dynamic/) - new work should call apk_memscan.py directly with
--package for other apps.

Usage: python3 -I scripts/re/pilot_memscan.py --device <serial> [--decompile]
Output: tmp/apk/pilot_dynamic/ (carved_*.dex, decompiled/) - same as before.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from apk_memscan import ROOT, decompile, log, memscan  # noqa: E402

PKG = "dji.pilot"
OUT = ROOT / "tmp/apk/pilot_dynamic"
LOG = ROOT / "tmp/logs/pilot_memscan.log"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--decompile", action="store_true")
    args = ap.parse_args()

    carved = memscan(args.device, PKG, OUT, LOG)
    if args.decompile:
        if carved == 0:
            log(LOG, "0 dex carved - skipping decompile, nothing to decompile")
        else:
            decompile(OUT, LOG)


if __name__ == "__main__":
    main()
