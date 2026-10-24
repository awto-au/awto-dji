#!/usr/bin/env python3
"""Apply m0101_threadx_api_scan.py's findings (docs/m0101-threadx-reversing.md 8.1) into
the existing m0101 Ghidra project as real function names/comments, not just doc prose -
the Ghidra project is the actual RE deliverable per re/ghidra-projects/README conventions.
Reuses the project scripts/re/m0101_ghidra_disasm.py already built (no re-import).

Repro: python3 scripts/re/m0101_rename_threadx.py
Log: ./tmp/logs/m0101_rename_threadx.log
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
PROJ_DIR = REPO / "tmp" / "m0101_ghidra" / "proj"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"


def main() -> int:
    if not (PROJ_DIR / "M0101Project.gpr").exists():
        log(f"project not found at {PROJ_DIR} - run m0101_ghidra_disasm.py first", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1

    cmd = [
        str(ANALYZE_HEADLESS), str(PROJ_DIR), "M0101Project",
        "-process", "*",
        "-noanalysis",
        "-postScript", "RenameM0101ThreadX.java",
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0101_rename_threadx_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0:
        raise RuntimeError(f"Ghidra headless rename run failed, see {headless_log}")

    archive = archive_project(REPO, PROJ_DIR, "m0101_threadx_loader")
    log(f"project re-archived with renames: {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
