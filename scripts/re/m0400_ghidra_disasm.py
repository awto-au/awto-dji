#!/usr/bin/env python3
"""Full Ghidra ARM Cortex-M disassembly pass over the m0400 (gimbal MCU) firmware.

Issue #41. Loader: raw binary, ARM:LE:32:Cortex, base 0x08008000 (as recorded in
docs/air-id-and-stream-survey.md). Peripheral labels use the STM32F4 (RM0090)
map, since scripts/re/m0400_fingerprint.py found F4-layout literals (see
docs/code-provenance.md). Labels are a hypothesis until the literal-pool
xrefs are checked against the function context in the dump.

Output: tmp/m0400_ghidra/m0400_dump.txt
Log:    tmp/logs/m0400_ghidra_disasm.log (headless log: m0400_ghidra_headless.log)
Project archived (not deleted) to re/ghidra-projects/m0400_gimbal.tar.gz.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
BASE_ADDR = "0x08008000"
OUT_DIR = REPO / "tmp" / "m0400_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"

# STM32F4 (RM0090) peripheral bases. Passed to DumpARM.java as a TSV.
F4_PERIPHS = {
    0x40023800: "RCC", 0x40023C00: "FLASH_IF", 0x40020000: "GPIOA",
    0x40020400: "GPIOB", 0x40020800: "GPIOC", 0x40011000: "USART1",
    0x40004400: "USART2", 0x40004800: "USART3", 0x40013000: "SPI1",
    0x40003800: "SPI2", 0x40026000: "DMA1", 0x40026400: "DMA2",
    0x40012000: "ADC1", 0x40006400: "CAN1", 0x40005400: "I2C1",
    0x40000000: "TIM2", 0x40000400: "TIM3", 0x40000800: "TIM4",
    0x40010000: "TIM1", 0x40012C00: "SDIO",
}


def run_ghidra() -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        shutil.rmtree(proj_dir)  # regenerated from the import every run
    proj_dir.mkdir(parents=True)
    periph_tsv = OUT_DIR / "f4_periphs.tsv"
    periph_tsv.write_text("".join(f"0x{a:08x} {n}\n" for a, n in F4_PERIPHS.items()),
                          encoding="utf-8")
    dump_path = OUT_DIR / "m0400_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M0400Project",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", BASE_ADDR,
        "-postScript", "DumpARM.java", str(dump_path), str(periph_tsv), "vectors",
        "0x0801D46C:27",
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0400_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # No timeout wrapper: a 97 KB Cortex-M image; progress is in the headless log.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def report(dump_path: Path) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    section = text.split("=== NAMED PERIPHERAL LITERAL XREFS ===", 1)[-1]
    log("--- NAMED PERIPHERAL LITERAL XREFS (Ghidra, F4 map) ---")
    for line in section.splitlines():
        if line.strip():
            log(line)
    log(next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), ""))
    log(next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), ""))


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
    archive = archive_project(REPO, OUT_DIR / "proj", "m0400_gimbal")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
