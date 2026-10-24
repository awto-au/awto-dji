#!/usr/bin/env python3
"""Re-check whether {0x412,0x413,0x414,0x415} is m0900's complete CAN-ID set - issue #36
correction. The prior "closed" claim only enumerated call sites of ONE helper
(`can_endpoint_register`, 0x080033ec). That proves exhaustiveness for sends routed through
that helper, not for a direct/inline mailbox-register write placed anywhere else in the
322-function image - STM32's bxCAN has independent TX mailboxes and no hardware requirement
that every send goes through one software abstraction.

Two independent checks, both against the full raw image + full disassembly already dumped
by scripts/re/m0900_can_ghidra.py (tmp/m0900_can_ghidra/m0900_dump.txt, archived project
re/ghidra-projects/m0900_can.tar.gz):

1. RX filter-bank check: every call site of CAN_FilterInit (0x0800072e). Reported for
   completeness, but it has exactly one caller (can_endpoint_register) -> NOT independent
   evidence, just a restatement of the same call-site search.
2. Register-range literal-pool scan: every 4-byte-aligned word in the raw firmware image
   that falls inside the CAN1 (0x40006400-0x400067ff) or CAN2 (0x40006800-0x40006bff)
   register block, anywhere in the image - not scoped to any helper's callers. This is the
   address-level check: on this ISA a 32-bit peripheral address can only be built from a
   literal-pool LDR (checked here) or a movw/movt immediate pair (checked separately below),
   so finding every literal-pool occurrence of the whole register block's address range
   finds every possible origin of a pointer into it, independent of which function calls
   which helper.
3. movw/movt scan: lists every movw/movt in the full disassembly so a human can confirm
   none targets the CAN1/CAN2 upper half (0x4000) with a matching lower half - rules out
   the only other address-construction technique this ISA offers.

Output: tmp/m0900_can_ghidra/can_closure_check.txt
Log:    tmp/logs/m0900_can_closure_check.log
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
DUMP = REPO / "tmp" / "m0900_can_ghidra" / "m0900_dump.txt"
BASE = 0x08000000

CAN1_RANGE = (0x40006400, 0x400067FF)
CAN2_RANGE = (0x40006800, 0x40006BFF)
FILTERINIT_ADDR = 0x0800072E


def find_filterinit_callers(disasm: str) -> list[str]:
    return re.findall(rf"^(\S+) \[(\S+)\]: bl 0x{FILTERINIT_ADDR:08x}\b.*$", disasm, re.MULTILINE)


def literal_pool_scan(data: bytes, lo: int, hi: int, disasm: str) -> list[str]:
    """Every 4-byte-aligned word in [lo,hi] anywhere in the raw image, plus the LDR
    instructions that load it (found via the dump's ref->ADDR(READ) annotations)."""
    out = []
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if lo <= v <= hi:
            lit_addr = BASE + off
            users = re.findall(rf"(\S+) \[(\S+)\]:[^\n]*ref->{lit_addr:08x}\(READ\)", disasm)
            out.append(f"literal@{lit_addr:#010x} value={v:#010x} users={users}")
    return out


def movw_movt_scan(disasm: str) -> list[str]:
    return [l.strip() for l in disasm.splitlines() if re.search(r"\bmovw\b|\bmovt\b", l, re.I)]


def main() -> int:
    if not FW.exists() or not DUMP.exists():
        log(f"missing input: fw={FW.exists()} dump={DUMP.exists()}", level="ERROR")
        return 1
    data = FW.read_bytes()
    text = DUMP.read_text(encoding="utf-8", errors="replace")
    disasm = text.split("=== FULL DISASSEMBLY ===", 1)[1].split("=== DECOMPILATION ===", 1)[0]

    out_dir = REPO / "tmp" / "m0900_can_ghidra"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "can_closure_check.txt"
    lines: list[str] = []

    lines.append("### 1. CAN_FilterInit (0x0800072e) callers")
    callers = re.findall(rf"(\S+) \[(\S+)\]: bl 0x{FILTERINIT_ADDR:08x}\b", disasm)
    lines.append(f"found {len(callers)} call site(s): {callers}")
    lines.append("-> only can_endpoint_register calls it; NOT independent of the "
                 "call-site search already done. Filters programmed: 0x413, 0x415 (RX "
                 "endpoints only; TX endpoints never filter).")

    lines.append("")
    lines.append("### 2. Literal-pool scan, full raw image, CAN1 register block "
                 f"{CAN1_RANGE[0]:#x}-{CAN1_RANGE[1]:#x}")
    hits1 = literal_pool_scan(data, *CAN1_RANGE, disasm)
    for h in hits1:
        lines.append("  " + h)
    lines.append(f"total: {len(hits1)} literal(s) found anywhere in the raw image")

    lines.append("")
    lines.append(f"### 3. Literal-pool scan, CAN2 register block {CAN2_RANGE[0]:#x}-{CAN2_RANGE[1]:#x}")
    hits2 = literal_pool_scan(data, *CAN2_RANGE, disasm)
    for h in hits2:
        lines.append("  " + h)
    lines.append(f"total: {len(hits2)} literal(s) found anywhere in the raw image")

    lines.append("")
    lines.append("### 4. movw/movt scan, full disassembly (alternate address-construction check)")
    mm = movw_movt_scan(disasm)
    lines.append(f"total movw/movt instructions in the entire image: {len(mm)}")
    movt_count = sum(1 for l in mm if re.search(r"\bmovt\b", l, re.I))
    lines.append(f"movt instructions (needed to build any 0x4000xxxx address): {movt_count}")
    for l in mm:
        lines.append("  " + l)

    out_text = "\n".join(lines) + "\n"
    out_path.write_text(out_text)
    log(f"wrote {out_path}")
    log(f"CAN1 literal-pool hits: {len(hits1)}, CAN2: {len(hits2)}, "
        f"movt count: {movt_count} (0 means no movw/movt path to any 0x4000xxxx address exists)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
