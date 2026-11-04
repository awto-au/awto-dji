"""Repo roots for the m2001 FPGA scripts. These scripts need the pluribus engine checkout (lifters/, scripts/, lift artefacts in its tmp/).

  PLURIBUS  engine checkout:  $PLURIBUS_REPO -> sibling ../pluribus of this repo -> error (never a hardcoded path)
  DJI       this repo (awto-dji): git toplevel of this file, else file-relative
  BOARD     fpga/m2001/board (pins.tsv, nets.tsv, functional_*.tsv)

Importing this module puts PLURIBUS and PLURIBUS/scripts on sys.path (lifters, patterns, functrace, cycloneiv_clean_image_sim ...).
Logs go to DJI/tmp/logs; lift artefacts (nl.pkl, regions/, partition.json) stay under PLURIBUS/tmp where the lift writes them.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _dji() -> Path:
    try:
        out = subprocess.run(["git", "-C", str(HERE), "rev-parse", "--show-toplevel"], capture_output=True, text=True, timeout=1.0)   # local .git read; 1 s covers a cold exec
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return HERE.parents[2]


def _pluribus(dji: Path) -> Path:
    env = os.environ.get("PLURIBUS_REPO")
    for cand in ([Path(env).expanduser()] if env else []) + [dji.parent / "pluribus"]:
        if (cand / "lifters" / "cycloneiv_clean").is_dir():
            return cand.resolve()
    raise SystemExit("pluribus checkout not found: set PLURIBUS_REPO (looked for lifters/cycloneiv_clean in $PLURIBUS_REPO and ../pluribus)")


DJI = _dji()
PLURIBUS = _pluribus(DJI)
BOARD = str(DJI / "fpga" / "m2001" / "board")
for _p in (str(PLURIBUS / "scripts"), str(PLURIBUS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)
DJI, PLURIBUS = str(DJI), str(PLURIBUS)
