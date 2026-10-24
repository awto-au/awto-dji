#!/usr/bin/env python3
"""Decode m0900's CAN TX routing table (packet_send, issue #36 payload-meaning question).

packet_send (FUN_080098d0 in the issue-#36 CAN-focused Ghidra pass, tmp/m0900_can_ghidra/)
dispatches an outbound DUML frame by `byte5 & 0x1f` (the DUML receiver-type byte, masked)
through a 31-entry Thumb `tbb [pc,r0]` table at flash 0x080098e4 (target = table_addr +
2*byte). This reads that table directly out of the firmware image (no Ghidra needed - the
table is flash data, not an opcode) and prints receiver-type -> target-address.

Also dereferences the literal pool slots that resolve `FUN_080030a4`'s reason-code (1/2/3)
to a concrete USART TX-DMA buffer address, confirming reason 1/2/3 = USART1/2/3 (cross-
checked against docs/data/m0900-buses.tsv's documented DMA buffer addresses).

Firmware: firmware/P3X_FW_V01.11.0020_m0900.bin (sha256 in docs/dataflow.md section 7
header). Addresses are from that image; see docs/dataflow.md section 7.11 for the full
analysis this supports.

Output: tmp/m0900_can_ghidra/routing_table.txt. Log: tmp/logs/m0900_can_routing_decode.log.
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
BASE = 0x08000000
TABLE_ADDR = 0x080098E4
TABLE_ENTRIES = 31  # tbb guards r0 >= 0x1f (31) -> default, so only 0..30 are real

# DUML DeviceType values this table's targets correspond to (docs/data/apk-cmdset-devicetype.tsv).
DEVICE_TYPE = {
    0: "WHO", 1: "CAMERA", 2: "APP", 3: "FLYC", 4: "GIMBAL", 5: "CENTER", 6: "RC", 7: "WIFI",
    8: "DM368", 9: "OFDM", 10: "PC", 11: "BATTERY", 12: "DIGITAL", 13: "DM368_G", 14: "OSD",
    15: "TRANSFORM", 16: "TRANSFORM_G", 17: "SINGLE", 18: "DOUBLE", 19: "FPGA", 20: "FPGA_G",
}

# FUN_080030a4's reason-code -> USARTx TX-DMA buffer literal (dereferenced below), per
# docs/data/m0900-buses.tsv's documented DMA buffer addresses (0x200001d0/4d0/7d0).
REASON_LITERALS = {
    1: 0x08003234,  # -> 0x200001d0 = USART1 TX DMA buf
    2: 0x08003238,  # -> 0x200004d0 = USART2 TX DMA buf
    3: 0x08003224,  # -> 0x200007d0 = USART3 TX DMA buf
}
USART_BUF = {0x200001D0: "USART1", 0x200004D0: "USART2", 0x200007D0: "USART3"}


def main() -> int:
    if not FW.exists():
        log(f"firmware not found: {FW}", level="ERROR")
        return 1
    data = FW.read_bytes()
    out_dir = REPO / "tmp" / "m0900_can_ghidra"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "routing_table.txt"

    lines = []
    lines.append(f"packet_send tbb @ {TABLE_ADDR:#010x}, {TABLE_ENTRIES} entries "
                  f"(table_addr + 2*byte = target)\n")
    targets: dict[int, list[int]] = {}
    off = TABLE_ADDR - BASE
    for i in range(TABLE_ENTRIES):
        b = data[off + i]
        target = TABLE_ADDR + 2 * b
        targets.setdefault(target, []).append(i)
    for target, idxs in sorted(targets.items(), key=lambda kv: kv[1][0]):
        names = [f"{i}({DEVICE_TYPE.get(i, '?')})" for i in idxs]
        lines.append(f"target {target:#010x}: receiver types {', '.join(names)}")
    lines.append("")
    lines.append("FUN_080030a4 reason-code -> USART TX-DMA buffer (cross-check):")
    for reason, lit_addr in sorted(REASON_LITERALS.items()):
        val = struct.unpack_from("<I", data, lit_addr - BASE)[0]
        lines.append(f"  reason {reason}: [{lit_addr:#010x}] = {val:#010x} "
                      f"({USART_BUF.get(val, 'unknown')})")

    text = "\n".join(lines) + "\n"
    out_path.write_text(text)
    log(f"wrote {out_path}")
    for line in lines:
        log(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
