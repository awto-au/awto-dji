#!/usr/bin/env python3
"""Full Ghidra ARM Cortex-M4 disassembly pass over the m0306 (A3 flight controller)
firmware. Issue #40: no function-level RE existed for this chip at all - only the
vector-table-derived chip/RTOS fingerprint in docs/code-provenance.md. This produces
the peripheral map (CAN1/CAN2/SPI/USART/GPIO/etc literal xrefs) and the function/
instruction inventory needed to characterise the software stack beyond "uC/OS-III
confirmed".

Loader: raw binary, ARM:LE:32:Cortex, base 0x08020000 - confirmed (not the
0x08008000/0x08000000 figures floating in some earlier notes) by decoding the
PendSV handler (0x0802c79f -> file offset 0xc79e -> `cpsid i`, a context-switch
prologue) and the SysTick handler (0x08029de3 -> file offset 0x9de2 -> push
{r4,lr}; bl tick-counter-incr; bl scheduler) under this base - both decode to
sane handler prologues only at 0x08020000, not at 0x08000000.

Reuses DumpARM.java (written for m0900) with its optional arg[1] TSV override
pointed at m0306_periph_map.tsv (STM32F42x/F43x bxCAN1/2 + full peripheral set,
RM0090 addresses) instead of m0900's hardcoded STM32F103 SPI/GPIO/RCC map.

Output: tmp/m0306_ghidra/m0306_dump.txt (function list + full disassembly +
named-peripheral literal xrefs for CAN1/CAN2/SPI/USART/GPIO/RCC/DMA/I2C/ADC/TIM/FSMC).
Log: ./tmp/logs/m0306_ghidra_disasm.log
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
FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0306.bin"
BASE_ADDR = "0x08020000"
OUT_DIR = REPO / "tmp" / "m0306_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"
PERIPH_TSV = REPO / "scripts" / "re" / "m0306_periph_map.tsv"


def run_ghidra() -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = OUT_DIR / "m0306_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M0306Project",
        "-import", str(FW),
        "-processor", "ARM:LE:32:Cortex",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", BASE_ADDR,
        "-postScript", "DumpARM.java", str(dump_path), str(PERIPH_TSV),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m0306_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # 885 KB image (~12x m0900's 75 KB). No timeout wrapper - headless Ghidra
        # gives no stall-watchable progress line (agent-rules host-process note);
        # monitored via the Monitor tool's stall/elapsed check instead of a blind cap.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def report(dump_path: Path) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    section = text.split("=== NAMED PERIPHERAL LITERAL XREFS ===", 1)[-1]
    log("--- NAMED PERIPHERAL LITERAL XREFS (Ghidra) ---")
    for line in section.splitlines():
        if line.strip():
            log(line)
    func_count_line = next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), "")
    log(func_count_line)
    insn_line = next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), "")
    log(insn_line)


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
    archive = archive_project(REPO, OUT_DIR / "proj", "m0306_flight_controller")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
