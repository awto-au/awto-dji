#!/usr/bin/env python3
"""Full Ghidra ARM Cortex-M headless pass over the m1400 (ground/RC radio MCU, LPC1765)
firmware. awto-dji#39: m1400 was wrongly documented as STM32F103 (corrected,
docs/ground-upgrade-path.md); this is the first Ghidra pass on the correct chip, with real
LPC176x SVD register labelling (docs/data/lpc176x5x-register-map.tsv, from
awto-dan/docs/embedded/reversing/lpc17xx/svd/LPC176x5x.svd via scripts/re/svd_to_labels.py)
instead of the earlier word-window literal scan's [oss] guessed bases.

Loader: raw binary, ARM:LE:32:Cortex, base 0xA000 (flash address = file offset + 0xA000,
verified in docs/ground-upgrade-path.md "Addressing" - reset handler + default-handler stub
alignment). LPC17xx flash starts at 0x00000000 (unlike STM32's 0x08000000), so this is the
direct flash base, not a bootloader-relative one.

Output: tmp/m1400_ghidra/m1400_dump.txt (SVD label count, function list, named peripheral
xrefs, full disassembly, full decompilation).
Log: ./tmp/logs/m1400_ghidra_disasm.log
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
FW = REPO / "firmware" / "unpacked" / "C1_FW_V01.06.0000" / "C1_FW_V01.06.0000_m1400.bin"
SVD_LABELS = REPO / "docs" / "data" / "lpc176x5x-register-map.tsv"
BASE_ADDR = "0xA000"
OUT_DIR = REPO / "tmp" / "m1400_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"


def run_ghidra() -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m1400_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M1400Project",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", BASE_ADDR,
        "-postScript", "DumpLPC17xx.java", str(dump_path), str(SVD_LABELS),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m1400_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # 155 KB Cortex-M3 image, same order of magnitude as m0900 (75 KB, 6 s full
        # auto-analysis + decompile-all). No timeout wrapper: headless Ghidra gives no
        # stall-watchable progress line (awto-dan agent-rules host-process note), and this
        # image is small enough that Ghidra's analyzers are not the slow part on this class
        # of target.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def report(dump_path: Path) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    label_line = next((l for l in text.splitlines() if l.startswith("=== SVD LABELS")), "")
    log(label_line)
    section = text.split("=== NAMED PERIPHERAL BASE XREFS ===", 1)[-1].split("=== FULL DISASSEMBLY ===", 1)[0]
    log("--- NAMED PERIPHERAL BASE XREFS (Ghidra) ---")
    for line in section.splitlines():
        if line.strip():
            log(line)
    func_count_line = next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), "")
    log(func_count_line)
    insn_line = next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), "")
    log(insn_line)


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW}", level="ERROR")
        return 1
    if not SVD_LABELS.exists():
        log(f"SVD label TSV not found at {SVD_LABELS} - run scripts/re/svd_to_labels.py first", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    dump_path = run_ghidra()
    report(dump_path)
    log(f"full dump: {dump_path}")
    archive = archive_project(REPO, OUT_DIR / "proj", "m1400_radio")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
