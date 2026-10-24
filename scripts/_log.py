"""Shared progress/result logger for scripts/ and scripts/re/ (CLAUDE.md: tmp/logs mandatory).

log(msg) -> stderr + ./tmp/logs/<script>.log, ISO 8601 local time with offset.
Import from scripts/re/ with: sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
Machine-readable payloads stay on stdout; only status/result lines go through log().
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


def _repo() -> Path:
    # $AWTO_DJI_REPO -> git toplevel -> file-relative (awto-dan#35). Never VSCODE_CWD.
    env = os.environ.get("AWTO_DJI_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    here = Path(__file__).resolve().parent
    try:
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=0.25)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return here.parent


REPO = _repo()


def log(msg: str, level: str = "INFO", name: str | None = None) -> None:
    """Print to stderr and append to tmp/logs/<name>.log. Never raises on I/O failure."""
    name = name or Path(sys.argv[0]).stem or "script"
    stamp = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{stamp}  {level:<5} [{name}] {msg}"
    try:
        print(line, file=sys.stderr, flush=True)
    except OSError:
        pass
    try:
        logs = REPO / "tmp" / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        with (logs / f"{name}.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass
