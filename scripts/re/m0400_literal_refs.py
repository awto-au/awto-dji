#!/usr/bin/env python3
"""Literal-pool xref check for m0400 addresses (issue #41).

For each target address:
  - find every 4-byte word in the image equal to it (literal pool / table entry),
  - find every LDR/ADR-style instruction in the Ghidra dump whose operand is the
    literal's own address (i.e. a code site that loads that literal),
  - dump the bytes at the target and decode them as little-endian words.

Reads tmp/m0400_ghidra/m0400_dump.txt (run m0400_ghidra_disasm.py first).
Log: tmp/logs/m0400_literal_refs.log
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
DUMP = REPO / "tmp" / "m0400_ghidra" / "m0400_dump.txt"
BASE = 0x08008000
TARGETS = [0x0801D4AC, 0x08016254, 0x080C0000]


def range_words(data: bytes, code_lines: list[str], lo: int, hi: int) -> None:
    """Literal words whose value lies in [lo, hi) - catches base+offset table access."""
    log(f"=== words with value in [0x{lo:08x}, 0x{hi:08x}) ===")
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if lo <= v < hi:
            w = BASE + off
            pat = re.compile(rf"ldr[a-z.]* +\w+,\[0x{w:08x}\]")
            sites = [l for l in code_lines if pat.search(l)]
            log(f"  at 0x{w:08x} = 0x{v:08x}: {len(sites)} LDR site(s) {[s.split(':')[1][:8] for s in sites[:4]]}")


def main() -> int:
    data = FW.read_bytes()
    dump = DUMP.read_text(encoding="utf-8", errors="replace").splitlines()
    code_lines = [l for l in dump if l.startswith("CODE:")]
    range_words(data, code_lines, 0x0801D400, 0x0801D500)
    for t in TARGETS:
        log(f"=== target 0x{t:08x} ===")
        words = [BASE + off for off in range(0, len(data) - 3, 4)
                 if struct.unpack_from("<I", data, off)[0] == t]
        log(f"words equal to target: {[f'0x{w:08x}' for w in words]}")
        for w in words:
            pat = re.compile(rf"ldr[a-z.]* +\w+,\[0x{w:08x}\]")
            sites = [l for l in code_lines if pat.search(l)]
            log(f"  literal 0x{w:08x}: {len(sites)} LDR site(s)")
            for s in sites[:10]:
                log(f"    {s}")
        off = t - BASE
        if 0 <= off < len(data):
            blk = data[off:off + 48]
            words_at = [struct.unpack_from("<I", blk, i)[0] for i in range(0, len(blk) - 3, 4)]
            log("  bytes at target (12 words): " + " ".join(f"{v:08x}" for v in words_at[:12]))
        else:
            log("  target outside image")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
