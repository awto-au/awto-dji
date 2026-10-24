#!/usr/bin/env python3
"""Full Ghidra ARM disassembly pass over m1601 (ground FX3), issue #42.

First FX3 (ARM9, ARMv5TEJ) Ghidra target in this project - FX2/FX2LP (m1500,
m1600) used the native 8051 processor module; this chip needs ARM instead.
Ghidra has no "CY" FX3 boot-image loader, so the real memory map is NOT built
by -import: a tiny dummy blob is imported just to create the Program (language/
compiler selection), then the postScript (DumpFX3.java) rebuilds the real
section map by reading byte ranges straight off the original .bin, using the
same "CY" section-record format scripts/re/fx3_trace.py already parses for the
capstone-based static-analysis pass in docs/fx3-usb-modes.md.

Output: tmp/m1601_ghidra/m1601_dump.txt.
Log: ./tmp/logs/m1601_fx3_disasm.log
"""
from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
FW = REPO / "firmware" / "unpacked" / "C1_FW_V01.06.0000" / "C1_FW_V01.06.0000_m1601.bin"
OUT_DIR = REPO / "tmp" / "m1601_ghidra"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"


def parse_sections(data: bytes) -> tuple[list[tuple[int, int, int]], int]:
    """Parse a Cypress FX3 "CY" boot image: ([(va, file_offset, length), ...], entry).

    Same record format scripts/re/fx3_trace.py's `sections()` parses (not
    imported, to keep this script runnable standalone without capstone - only
    needed here to get section offsets, not to disassemble).
    """
    if data[:2] != b"CY" or data[3:4] != b"\xb0":
        raise ValueError("expected executable CY boot image")
    offset = 4
    secs = []
    while offset + 8 <= len(data):
        words, address = struct.unpack_from("<II", data, offset)
        if words == 0:
            return secs, address  # entry-point record
        start = offset + 8
        end = start + words * 4
        if end > len(data):
            raise ValueError("truncated CY section")
        secs.append((address, start, words * 4))
        offset = end
    raise ValueError("missing CY entry record")


def build_manifest() -> tuple[Path, int]:
    data = FW.read_bytes()
    secs, entry = parse_sections(data)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = OUT_DIR / "m1601_sections.tsv"
    with manifest.open("w") as fh:
        for va, off, length in secs:
            fh.write(f"{va:#010x}\t{off:#010x}\t{length}\n")
    log(f"parsed {len(secs)} CY section(s), entry={entry:#010x}: "
        f"{[(hex(va), hex(off), length) for va, off, length in secs]}")
    return manifest, entry


def run_ghidra(manifest: Path, entry: int) -> Path:
    proj_dir = OUT_DIR / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dummy = OUT_DIR / "dummy_bootstrap.bin"
    dummy.write_bytes(b"\x00" * 16)
    dump_path = OUT_DIR / "m1601_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), "M1601Project",
        "-import", str(dummy),
        "-processor", "ARM:LE:32:v5t",
        "-loader", "BinaryLoader",
        "-loader-baseAddr", "0x90000000",
        "-postScript", "DumpFX3.java", str(dump_path), str(FW), str(manifest), f"{entry:#010x}",
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / "m1601_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # 190 KB image, 5 sections, full auto-analysis. m0400's comparable-size
        # STM32F4 pass (issue #41) finished in well under a minute - no timeout
        # wrapper, see awto-dan agent-rules host-process note; watch the log on stall.
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed, see {headless_log}")
    return dump_path


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW} - see docs/data-manifest.md to re-fetch/unpack", level="ERROR")
        return 1
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    manifest, entry = build_manifest()
    dump_path = run_ghidra(manifest, entry)
    log(f"full dump: {dump_path}")
    archive = archive_project(REPO, OUT_DIR / "proj", "m1601_fx3")
    log(f"project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
