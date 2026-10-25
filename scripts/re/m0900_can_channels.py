#!/usr/bin/env python3
"""m0900: which DUML channels exist, what IDs/ports they use, and where each receiver type goes.

Answers (docs/m0900-can-channels.md):
  1. what StdId the CAN queue object 0x20002538 carries (and its RX partner),
  2. whether CAN RX 0x413 and 0x415 reach the same DUML parser/dispatch,
  3. which DUML receiver types select each CAN queue / UART port (packet_send tbb),
  4. whether every channel uses the same 0x55 framing + CRC8/CRC16 checks.

Static only: capstone linear disasm + a tiny constant tracker (literal-pool loads, mov/movw
immediates, add/sub immediates; r0-r3 clobbered by bl). Asserts each claim so a different image
fails loudly instead of printing a wrong table.

Usage:  python3 scripts/re/m0900_can_channels.py [m0900.bin]
Default image: firmware/P3X_FW_V01.11.0020_m0900.bin (SHA-256 in docs/data-manifest.md).
"""
import hashlib
import os
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_OP_IMM, CS_OP_MEM, CS_OP_REG
from capstone.arm import ARM_REG_PC

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from m0900_trace import BASE, ROOT  # noqa: E402

SHA256 = "72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d"

CAN_QUEUE_INIT = 0x0800B3EC   # (obj, std_id, is_tx, size, [sp]=buf)
PARSER_INIT = 0x08011A7E      # (parser, buf, frame_cb, bufsize)
PARSER_FEED = 0x08011A8E      # (parser, byte) -> 2 on a complete, CRC-good frame
RING_COUNT = 0x0800C24C       # (ring) -> bytes available
DUML_DISPATCH = 0x0801198A    # (buf, len): table 0x0801a120, else packet_send
CRC16_CB = 0x08011BE7         # frame callback: CRC16 seed 0x3692 over len-2
ROUTE_TBB = 0x080118E4
BOOT_INIT = 0x0800DAC4

md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
md.detail = True


def load():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin")
    img = open(path, "rb").read()
    h = hashlib.sha256(img).hexdigest()
    print(f"# image {path}\n# sha256 {h} ({'matches manifest' if h == SHA256 else 'DIFFERENT IMAGE'})")
    return img


def insns(img, start, end):
    return list(md.disasm(img[start - BASE:end - BASE], start))


def word(img, a):
    return int.from_bytes(img[a - BASE:a - BASE + 4], "little")


def track(img, start, end):
    """Yield (insn, regs) for each insn, regs = known constant values before the insn."""
    regs = {}
    for i in insns(img, start, end):
        yield i, dict(regs)
        ops = i.operands
        m = i.mnemonic.split(".")[0]
        dst = i.reg_name(ops[0].reg) if ops and ops[0].type == CS_OP_REG else None
        if m in ("bl", "blx"):
            for r in ("r0", "r1", "r2", "r3"):
                regs.pop(r, None)
        elif m == "ldr" and len(ops) == 2 and ops[1].type == CS_OP_MEM and ops[1].mem.base == ARM_REG_PC:
            regs[dst] = word(img, ((i.address + 4) & ~3) + ops[1].mem.disp)
        elif m in ("movs", "mov", "movw") and len(ops) == 2 and ops[1].type == CS_OP_IMM:
            regs[dst] = ops[1].imm & 0xFFFFFFFF
        elif m in ("mov", "movs") and len(ops) == 2 and ops[1].type == CS_OP_REG:
            src = i.reg_name(ops[1].reg)
            if src in regs:
                regs[dst] = regs[src]
            else:
                regs.pop(dst, None)
        elif m in ("adds", "add", "subs", "sub") and ops[-1].type == CS_OP_IMM:
            src = i.reg_name(ops[1].reg) if len(ops) == 3 else dst
            sign = -1 if m.startswith("sub") else 1
            if src in regs:
                regs[dst] = (regs[src] + sign * ops[-1].imm) & 0xFFFFFFFF
            else:
                regs.pop(dst, None)
        elif m == "str" and len(ops) == 2 and ops[1].type == CS_OP_MEM and \
                i.reg_name(ops[1].mem.base) == "sp" and ops[1].mem.disp == 0 and dst in regs:
            regs["[sp]"] = regs[dst]
        elif dst and m not in ("cmp", "cbz", "cbnz", "str", "strb", "strh", "push", "b", "bne", "beq"):
            regs.pop(dst, None)


def calls_to(img, start, end, target):
    out = []
    for i, regs in track(img, start, end):
        if i.mnemonic in ("bl", "b.w") and i.operands[0].imm == target:
            out.append((i.address, regs))
    return out


def main():
    img = load()

    print("\n## 1. CAN queue objects (can_queue_init 0x0800b3ec call sites)")
    queues = {}
    for fn, end in ((0x080113A8, 0x08011404), (0x08011828, 0x08011874)):
        for site, r in calls_to(img, fn, end, CAN_QUEUE_INIT):
            obj, sid, tx, size, buf = r["r0"], r["r1"], r["r2"], r["r3"], r["[sp]"]
            queues[sid] = obj
            print(f"  site {site:#010x} (fn {fn:#010x}): obj {obj:#010x} StdId {sid:#05x} "
                  f"{'TX' if tx else 'RX'} ring {size} B buf {buf:#010x}")
    assert queues[0x414] == 0x20002538, "0x20002538 is not the 0x414 queue"
    assert queues[0x415] == 0x20002554 and queues[0x412] == 0x20002330 and queues[0x413] == 0x2000234C
    boot = {i.operands[0].imm: i.address for i in insns(img, 0x0800DB90, 0x0800DBA4) if i.mnemonic == "bl"}
    print(f"  boot init {BOOT_INIT:#010x} calls 0x080113a8 at {boot[0x080113A8]:#x} "
          f"(board-gated inside: 4/5/6/2) and 0x08011828 at {boot[0x08011828]:#x} (no board gate)")

    print("\n## 2. RX path: ring -> parser -> dispatch")
    # CAN RX0 IRQ matches StdId against every registered RX object; no per-ID branch.
    rx = insns(img, 0x0800B23C, 0x0800B298)
    assert any(i.mnemonic == "cmp" and i.op_str == "r1, r0" for i in rx)
    print("  can_rx0 0x0800b23c: loops 13-slot RX table 0x200015d0, StdId==obj[0] -> push DLC bytes to obj+4 (ID-agnostic)")
    parsers = {}
    for fn, end in ((0x080113A8, 0x0801141C), (0x08011828, 0x08011876), (0x0801260C, 0x0801261C)):
        for site, r in calls_to(img, fn, end, PARSER_INIT):
            parsers[r["r0"]] = (r["r1"], r["r3"])
            print(f"  parser_init at {site:#010x}: parser {r['r0']:#010x} cb {r['r1']:#010x} bufsize {r['r3']}")
    assert all(cb == CRC16_CB for cb, _ in parsers.values()), "channels use different frame callbacks"
    # UART RX IRQs push into rings at 0x20000017 + 0x14/0x3c/0x64 (USART1/2/3).
    uart_rings = {}
    for irq, name in ((0x0800AB86, "USART1"), (0x0800ABE4, "USART2"), (0x0800AC42, "USART3")):
        put = [r["r0"] for _, r in calls_to(img, irq, irq + 0x5C, 0x0800C274)]
        uart_rings[put[0]] = name
    known = dict(uart_rings)
    known.update({obj + 4: f"CAN {sid:#x}" for sid, obj in queues.items()})
    print("  rx rings: " + ", ".join(f"{a:#010x}={n}" for a, n in sorted(known.items())))
    for pump, end, label in ((0x0801148C, 0x08011540, "CAN 0x413 (boards 2/4/5/6) / USART2 (board 7)"),
                             (0x08011882, 0x080118B8, "CAN 0x415"),
                             (0x08012626, 0x0801267C, "USART1")):
        # Branch-insensitive tracker: collect every known ring the pump loads into r0.
        rings = sorted({r["r0"] for i, r in track(img, pump, end) if r.get("r0") in known})
        feeds = [r["r0"] for _, r in calls_to(img, pump, end, PARSER_FEED)]
        disp = calls_to(img, pump, end, DUML_DISPATCH)
        assert disp, f"pump {pump:#x} does not reach dispatch"
        print(f"  pump {pump:#010x} [{label}]: ring(s) {', '.join(f'{x:#010x}({known[x]})' for x in rings)} -> "
              f"parser {', '.join(f'{x:#010x}' for x in feeds)} -> duml_dispatch {DUML_DISPATCH:#010x}")

    print("\n## 3. packet_send routing (tbb 0x080118e4, index = pkt[5] & 0x1f)")
    tail = {}
    for t in (0x08011904, 0x08011938, 0x0801194E, 0x08011942):
        b = next(i for i in insns(img, t, t + 0x20) if i.mnemonic == "b.w")
        tail[t] = b.operands[0].imm
    assert tail[0x08011938] == 0x0801261C and tail[0x08011942] == 0x08011876
    u1 = insns(img, 0x0801261C, 0x08012626)
    assert [i.op_str for i in u1 if i.mnemonic == "movs"] == ["r0, #1"] and u1[-1].operands[0].imm == 0x0800B0A4
    q414 = [r["r0"] for _, r in calls_to(img, 0x08011876, 0x08011882, 0x0800B468)]
    assert q414 == [0x20002538]
    sink = {
        0x08011988: "drop",
        0x08011904: "path A 0x0801141c: CAN 0x412 queue (boards 2/4/5/6); UART (board 7)",
        0x0801194E: "uart_send(3) USART3",
        0x08011938: "0x0801261c = uart_send(1) USART1, every board",
        0x0801195C: "boards 2/4/5/6: USART1; board 7: path A",
        0x0801190E: "boards 2/4/5/6: 0x08011876 = CAN 0x414 queue 0x20002538; board 7: USART1",
    }
    groups = {}
    for t in range(31):
        dest = ROUTE_TBB + 2 * img[ROUTE_TBB - BASE + t]
        groups.setdefault(sink[dest], []).append(t)
    for s, ts in groups.items():
        print(f"  types {','.join(map(str, ts)):<32} -> {s}")

    print("\n## 4. Framing (shared parser 0x08011a8e)")
    p = insns(img, 0x08011A8E, 0x08011BE6)
    assert any(i.mnemonic == "cmp" and i.op_str == "r1, #0x55" for i in p)
    crc8 = insns(img, 0x08011E0E, 0x08011E30)
    assert any(i.op_str == "r2, #0x77" for i in crc8)
    crc16 = insns(img, 0x08011BE6, 0x08011BF0)
    assert any(i.mnemonic == "movw" and i.op_str == "r2, #0x3692" for i in crc16)
    print("  sync 0x55; len = u16[1] & 0x3ff, len > bufsize => resync; version (b2>>2) in {0,1};")
    print("  header CRC8 seed 0x77 over bytes 0..2 (0x08011e0e); frame CRC16 seed 0x3692 over len-2 (0x08011be6)")
    print("  => one framing for CAN 0x413, CAN 0x415, USART1, USART2; only bufsize differs "
          + ", ".join(f"{k:#x}:{v[1]}B" for k, v in parsers.items()))


if __name__ == "__main__":
    main()
