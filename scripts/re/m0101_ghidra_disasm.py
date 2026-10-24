#!/usr/bin/env python3
"""Ghidra ARMv7-A disassembly pass over the m0101 (ThreadX camera loader) module.

Issue #37: m0101 had zero investigation beyond a toolchain fingerprint (IAR +
ThreadX). A `strings` triage (see docs/m0101-threadx-reversing.md) already found
the "ThreadX Cortex-A9/IAR" copyright string and a full Ambarella NAND/SD firmware-
updater symbol set (AmbaFwUpdaterTask, DjiUegFwStageSet, AmbaNFTL_*, ...). This
script runs full Ghidra auto-analysis to get real function boundaries and confirm
those strings' call sites, rather than relying on `strings` proximity alone.

Loader: raw binary, ARM:LE:32:v7 (generic ARMv7-A - Ghidra has no Cortex-A9-specific
variant; Cortex-A9 is a standard ARMv7-A core, no Thumb-2 extensions needed here).
Base address is NOT known (no public Ambarella A9SE loader-header spec found) - 00
loaded at file offset 0, so addresses in the dump are FILE OFFSETS, not a real
runtime base. Function boundaries/call graph (found via prologue patterns, not
base-dependent) are still valid; absolute literal-pool loads are not trustworthy.

Output: tmp/m0101_ghidra/m0101_dump.txt (function list + target string xrefs).
Log: ./tmp/logs/m0101_ghidra_disasm.log
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
FW = REPO / "tmp" / "air" / "P3X0006" / "P3X_FW_V01.01.0006_m0101.bin"
OUT_DIR = REPO / "tmp" / "m0101_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"


def run_ghidra() -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m0101_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M0101Project",
        "-import", str(FW),
        "-processor", "ARM:LE:32:v7",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", "0x0",
        "-postScript", "DumpM0101.java", str(dump_path),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0101_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # Full auto-analysis on a 400 KB ARMv7-A image (~5x the m0900 Cortex-M pass).
        # No timeout wrapper - headless Ghidra gives no stall-watchable progress line
        # (awto-dan agent-rules host-process note); this is still a small image by
        # Ghidra analyzer standards.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def report(dump_path: Path) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    func_count_line = next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), "")
    log(func_count_line)
    insn_line = next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), "")
    log(insn_line)
    section = text.split("=== TARGET STRING XREFS ===", 1)[-1]
    log("--- TARGET STRING XREFS ---")
    for line in section.splitlines():
        if line.strip():
            log(line)


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW} - see docs/data-manifest.md", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    dump_path = run_ghidra()
    report(dump_path)
    log(f"full dump: {dump_path}")
    archive = archive_project(REPO, OUT_DIR / "proj", "m0101_threadx_loader")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
