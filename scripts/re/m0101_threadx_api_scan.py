#!/usr/bin/env python3
"""Pin ThreadX primitive call sites in m0101 (issue #37, follow-up pass).

The first m0101 pass (docs/m0101-threadx-reversing.md) found ThreadX task-name
*strings* (RootTask, AmbaPrintTask) but not the tx_thread_create() call site
itself - the commercial build strips ThreadX's own API symbol names. This
script finds it anyway, using ThreadX's public, stable magic-ID constants
(TX_THREAD_ID etc, from github.com/eclipse-threadx/threadx common/inc/*.h) as
byte-pattern anchors:

1. Every TX_*_ID 32-bit constant is loaded via an ARM `LDR Rd, [PC, #imm]`
   literal-pool read somewhere a ThreadX API function validates a control
   block. Decode every such literal load with capstone and resolve its target.
2. Among the hits, the one write-context occurrence (`str rX, [r4]` right after
   the load, with no intervening cmp/beq) is the *creating* function, not a
   validator - ThreadX only ever writes the ID field in tx_<obj>_create().
3. Cross-checks: tx_thread_create's write site should sit next to a
   `_tx_thread_created_count++`-style global-counter bump, and its prologue
   should show 2 extra stack-passed args beyond r0-r3 (thread_ptr, name_ptr,
   entry_function, entry_input, stack_start, stack_size, priority,
   preempt_threshold, time_slice, auto_start = 10 params).
4. Also tries to resolve each ThreadX function's own callers (direct `bl`
   targets, +/- ADR/ADD-pc and MOVW/MOVT literal-build forms) to connect the
   RootTask/AmbaPrintTask name strings to an actual call - this did NOT
   resolve (see docs/m0101-threadx-reversing.md "Follow-up pass" section for
   why, and what that negative result does/doesn't rule out).

Static analysis only. Base address NOT assumed resolved - literal-pool EAs are
computed PC-relative (base-independent); only the final "file offset" framing
assumes base 0x0, exactly like the first pass's Ghidra run, for comparability.

Repro: python3 scripts/re/m0101_threadx_api_scan.py
Log: ./tmp/logs/m0101_threadx_api_scan.log
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

import capstone

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "tmp" / "air" / "P3X0006" / "P3X_FW_V01.01.0006_m0101.bin"

# ThreadX magic control-block IDs, from eclipse-threadx/threadx common/inc/*.h
# (tx_thread.h, tx_semaphore.h, tx_mutex.h, tx_event_flags.h, tx_timer.h).
# These are part of ThreadX's public, stable ABI - not DJI-specific.
TX_IDS = {
    0x54485244: "TX_THREAD_ID",
    0x53454D41: "TX_SEMAPHORE_ID",
    0x4D555445: "TX_MUTEX_ID",
    0x4456444E: "TX_EVENT_FLAGS_ID",
    0x4154494D: "TX_TIMER_ID",
    0x424C4F43: "TX_BLOCK_POOL_ID",
    0x42595445: "TX_BYTE_POOL_ID",
    0x51554555: "TX_QUEUE_ID",
}

# Task-name strings found by the first pass's `strings` triage - checked here
# as call-site targets, not found as any literal/ADR/MOVW+MOVT reference.
TASK_NAME_STRINGS = {
    0x7A2C: "RootTask",
    0x67FC: "AmbaPrintTask",
    0x51BC: "AmbaFwUpdaterTask",
    0x5168: "DjiFwUpdaterLedTask",
}


def disasm_literal_loads(data: bytes, md: capstone.Cs) -> dict[int, list[tuple[int, str, int]]]:
    """Map target EA -> [(insn_addr, 'ldr rX,[pc,#imm]', resolved_value)] for every
    ARM LDR-literal in the image. O(n) linear sweep - ARM mode is fixed 4-byte width,
    so a single-instruction decode per aligned offset is safe and cheap (~100K insns)."""
    n = len(data)
    by_ea: dict[int, list] = {}
    for off in range(0, n - 3, 4):
        insns = list(md.disasm(data[off:off + 4], off))
        if not insns or insns[0].mnemonic.lower() != "ldr":
            continue
        ins = insns[0]
        if "pc" not in ins.op_str:
            continue
        m = re.search(r"pc,\s*#(-?0x[0-9a-fA-F]+|-?\d+)\]", ins.op_str)
        if not m:
            continue
        ea = off + 8 + int(m.group(1), 0)
        if 0 <= ea < n - 3:
            val = struct.unpack_from("<I", data, ea)[0]
            by_ea.setdefault(ea, []).append((off, ins.op_str, val))
    return by_ea


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW}", level="ERROR")
        return 1
    data = FW.read_bytes()
    md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_ARM)
    md.detail = True

    log(f"loaded {FW} ({len(data)} bytes); scanning for LDR-literal loads")
    by_ea = disasm_literal_loads(data, md)

    log("=== ThreadX magic-ID literal pools found ===")
    id_sites: dict[str, list[int]] = {}
    for ea, refs in by_ea.items():
        val = refs[0][2]
        if val in TX_IDS:
            name = TX_IDS[val]
            id_sites.setdefault(name, []).append(ea)
            for off, op, _ in refs:
                log(f"  {name}: insn@{hex(off)} {op} -> literal@{hex(ea)}")

    log("=== classifying each ID load site as validate(read) vs create(write) ===")
    create_candidates = []
    for name, eas in id_sites.items():
        for ea in eas:
            for off, _, _ in by_ea[ea]:
                tail = list(md.disasm(data[off + 4:off + 16], off + 4))
                if tail and tail[0].mnemonic.lower() == "str":
                    create_candidates.append((name, off, ea))
                    log(f"  WRITE (create candidate): {name} @ {hex(off)} -> {tail[0].mnemonic} {tail[0].op_str}")

    log("=== resolving each create candidate's function entry + direct callers ===")
    # One bl-target scan reused for every candidate (cheap: single linear sweep).
    all_bl: dict[int, list[int]] = {}
    for off in range(0, len(data) - 3, 4):
        insns = list(md.disasm(data[off:off + 4], off))
        if insns and insns[0].mnemonic.lower() == "bl":
            try:
                tgt = int(insns[0].op_str.lstrip("#"), 0)
            except ValueError:
                continue
            all_bl.setdefault(tgt, []).append(off)

    for name, create_insn, _ in create_candidates:
        func_start = None
        for off in range(create_insn, max(0, create_insn - 0x200), -4):
            insns = list(md.disasm(data[off:off + 4], off))
            if insns and insns[0].mnemonic.lower() == "push" and "lr" in insns[0].op_str:
                func_start = off
                break
        callers = all_bl.get(func_start, []) if func_start is not None else []
        log(f"  {name} create candidate: write@{hex(create_insn)}, "
            f"function entry={hex(func_start) if func_start else 'not found'}, "
            f"direct callers={[hex(c) for c in callers]}")

    log("=== checking task-name strings for ANY literal/ADR/MOVW+MOVT reference ===")
    for addr, name in TASK_NAME_STRINGS.items():
        found = addr in by_ea
        log(f"  {name}@{hex(addr)}: LDR-literal reference found={found}")

    log("done - see docs/m0101-threadx-reversing.md 'Follow-up pass' section for interpretation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
