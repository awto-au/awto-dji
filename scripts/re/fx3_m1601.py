#!/usr/bin/env python3
"""Ground USB firmware m1601 (Cypress FX3 / CYUSB2014, GL300b/c RC): descriptors, DMA channels,
DJI threads and the RC->phone chunk header. Backs docs/ground-fx3-m1601.md.

Static only: parses the Cypress "CY" boot image into a flat SYSMEM image (base 0x40000000),
then capstone ARM-mode sweeps. Function roles were identified in the doc (SDK calls by their
argument shapes, DJI code by strings/literals); this script re-derives the facts the doc relies
on and asserts them, so a different build fails loudly.

Usage:  python3 scripts/re/fx3_m1601.py P3X_FW_V01.03.0020_m1601.bin
Get it: python3 scripts/re/xv4_extract.py P3X_FW_V01.03.0020.bin OUT m1601   (data-manifest.md)
"""
import hashlib
import struct
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM
from capstone.arm import ARM_OP_IMM, ARM_OP_MEM, ARM_OP_REG, ARM_REG_PC

SHA256 = "4eb9d11374336047542ece7ace7a4be050fc03d87a2810aed281b6c1cda0a114"  # m1601 02.00.0002
BASE = 0x40000000
CHANNEL_CREATE = 0x40012B84   # CyU3PDmaChannelCreate(handle, type, &cfg)
THREAD_CREATE = 0x400233E8    # tx_thread_create(thread, name, entry, ...)
DMA_TYPES = ["AUTO", "AUTO_SIGNAL", "MANUAL", "MANUAL_IN", "MANUAL_OUT", "AUTO_MANY_TO_ONE",
             "AUTO_ONE_TO_MANY", "MANUAL_MANY_TO_ONE", "MANUAL_ONE_TO_MANY", "MULTICAST"]

md = Cs(CS_ARCH_ARM, CS_MODE_ARM)
md.detail = True


def load_cy(path):
    d = open(path, "rb").read()
    print(f"# {path}\n# sha256 {hashlib.sha256(d).hexdigest()}"
          f" ({'matches 02.00.0002' if hashlib.sha256(d).hexdigest() == SHA256 else 'DIFFERENT BUILD'})")
    assert d[:2] == b"CY", "not a Cypress FX3 boot image"
    img, o = bytearray(0x80000), 4
    while True:
        n, addr = struct.unpack_from("<II", d, o)
        o += 8
        if n == 0:
            print(f"  entry {addr:#010x}")
            return bytes(img)
        if addr >= BASE:
            img[addr - BASE:addr - BASE + 4 * n] = d[o:o + 4 * n]
        print(f"  section {addr:#010x} len {4 * n:#x}")
        o += 4 * n


def word(img, a):
    return struct.unpack_from("<I", img, a - BASE)[0]


def cstr(img, a):
    o = a - BASE
    return img[o:img.find(b"\0", o)].decode(errors="replace")


def sock(v):
    if v is None:
        return "?(runtime)"
    if 0x100 <= v <= 0x11F:
        return f"FPGA PIB{v - 0x100}"
    if 0x300 <= v <= 0x30F:
        return f"USB EP{v - 0x300} IN (to phone)"
    if 0x400 <= v <= 0x40F:
        return f"USB EP{v - 0x400} OUT (from phone)"
    return {0x3F00: "CPU (consumer)", 0x3F01: "CPU (producer)",
            0x0003: "UART (consumer)", 0x0006: "UART (producer)"}.get(v, hex(v))


def descriptors(img):
    print("\n## USB descriptors (V)")
    i = img.find(b"\x12\x01\x00\x02")
    v, p = struct.unpack_from("<HH", img, i + 8)
    print(f"  device @{BASE + i:#x}: VID {v:04x} PID {p:04x}")
    assert (v, p) == (0x0547, 0x1002)
    i, seen = 0, []
    while (i := img.find(b"\x09\x02", i)) != -1:
        tot = struct.unpack_from("<H", img, i + 2)[0]
        if 18 <= tot <= 128 and 1 <= img[i + 4] <= 4:
            j, out = i, []
            while j < i + tot and img[j] >= 2:
                if img[j + 1] == 4:
                    out.append(f"IF{img[j + 2]} alt{img[j + 3]} class {img[j + 5]:#x}/{img[j + 6]:#x}/{img[j + 7]:#x}")
                elif img[j + 1] == 5:
                    ea = img[j + 2]
                    out.append(f"EP{ea & 0xF}{'IN' if ea & 0x80 else 'OUT'} {struct.unpack_from('<H', img, j + 4)[0]}B")
                j += img[j]
            seen.append(out)
            print(f"  config @{BASE + i:#x}: " + ", ".join(out))
        i += 1
    for s in ("com.dji.common", "iAP Interface", "MFI"):
        assert s.encode("utf-16-le") in img, s
    for s in (b"DJI\0", b"T600\0", b"DJI Inspire 1\0", b"www.dji.com\0"):
        assert s in img, s
    print("  strings: 'iAP Interface', 'com.dji.common' (Apple MFi iAP2 + EA native transport);"
          " AOA identity DJI/T600/'DJI Inspire 1'/v1.2.3.4/www.dji.com/12345678")


def channels(img):
    print("\n## DMA channels: CyU3PDmaChannelCreate call sites (V)")
    rows = []
    for c in range(0x40003000, 0x40023000, 4):
        i = next(md.disasm(img[c - BASE:c - BASE + 4], c), None)
        if not (i and i.mnemonic == "bl" and i.operands[0].imm == CHANNEL_CREATE):
            continue
        regs, mem = {}, {}
        for j in md.disasm(img[c - BASE - 192:c - BASE], c - 192):
            ops, m = j.operands, j.mnemonic
            if m.startswith("bl"):
                for r in ("r0", "r1", "r2", "r3", "ip", "lr"):
                    regs.pop(r, None)
                continue
            if not ops or ops[0].type != ARM_OP_REG:
                continue
            d = j.reg_name(ops[0].reg)
            if m == "ldr" and ops[1].type == ARM_OP_MEM and ops[1].mem.base == ARM_REG_PC:
                regs[d] = word(img, j.address + 8 + ops[1].mem.disp)
            elif m in ("mov", "mvn") and ops[1].type == ARM_OP_IMM:
                regs[d] = (~ops[1].imm if m == "mvn" else ops[1].imm) & 0xFFFFFFFF
            elif m == "mov" and ops[1].type == ARM_OP_REG:
                regs[d] = regs.get(j.reg_name(ops[1].reg))
            elif m == "subs" and len(ops) == 3 and ops[2].type == ARM_OP_IMM and ops[2].imm == 0:
                regs[d] = 0  # 'subs rX, r0, #0' then branch-if-nonzero: rX is 0 on the fallthrough
            elif m in ("add", "orr") and len(ops) == 3 and ops[2].type == ARM_OP_IMM:
                s = j.reg_name(ops[1].reg)
                regs[d] = ("sp", ops[2].imm) if s == "sp" else None
            elif m in ("str", "strh") and ops[1].type == ARM_OP_MEM and j.reg_name(ops[1].mem.base) == "sp":
                v = regs.get(d)
                for k in range({"str": 4, "strh": 2}[m]):
                    mem[ops[1].mem.disp + k] = None if not isinstance(v, int) else (v >> (8 * k)) & 0xFF
            elif m.startswith("ldr"):
                regs.pop(d, None)
        cfg, t = regs.get("r2"), regs.get("r1")
        g = None
        if isinstance(cfg, tuple):
            def g(off, n, b=cfg[1]):
                bs = [mem.get(b + off + k) for k in range(n)]
                return None if None in bs else int.from_bytes(bytes(bs), "little")
        size, count, prod, cons = (g(0, 2), g(2, 2), g(4, 2), g(6, 2)) if g else (None,) * 4
        tn = DMA_TYPES[t] if isinstance(t, int) and t < len(DMA_TYPES) else "?"
        rows.append((c, tn, prod, cons, size, count))
        print(f"  {c:#x} {tn:11} {sock(prod):26} -> {sock(cons):26} buf {size if size is None else hex(size)} x {count}")
    by = {r[0]: r for r in rows}
    assert by[0x40005CD0][1] == "AUTO" and (by[0x40005CD0][2], by[0x40005CD0][3]) == (0x402, 0x100)
    assert by[0x40005CFC][1] == "AUTO" and (by[0x40005CFC][2], by[0x40005CFC][3]) == (0x102, 0x306)
    assert by[0x40004AB0][1:4] == ("MANUAL_IN", 0x102, 0x3F00) and by[0x40004AB0][4] == 0x800
    assert by[0x40005EFC][1:4] == ("MANUAL_OUT", 0x3F01, 0x303) and by[0x40005EFC][4] == 0x820
    assert by[0x40003334][1] == "MANUAL_OUT" and by[0x40003334][4] == 0x820
    assert by[0x4000ECCC][1:4] == ("MANUAL_IN", 0x0006, 0x3F00)
    assert by[0x4000ECF4][1:4] == ("MANUAL_OUT", 0x3F01, 0x0003)


def threads(img):
    print("\n## DJI threads: tx_thread_create(name, entry) (V)")
    for c in range(0x40003000, 0x40024000, 4):
        i = next(md.disasm(img[c - BASE:c - BASE + 4], c), None)
        if not (i and i.mnemonic == "bl" and i.operands[0].imm == THREAD_CREATE):
            continue
        r = {}
        for j in md.disasm(img[c - BASE - 64:c - BASE], c - 64):
            if j.mnemonic == "ldr" and j.operands[1].type == ARM_OP_MEM and j.operands[1].mem.base == ARM_REG_PC:
                r[j.reg_name(j.operands[0].reg)] = word(img, j.address + 8 + j.operands[1].mem.disp)
        name = cstr(img, r["r1"]) if "r1" in r else "(SDK)"
        print(f"  {c:#x}: {name!r:18} entry {r.get('r2', 0):#x}")


def routing(img):
    print("\n## DUML sessions and the RC->phone chunk header (V)")
    # duml_session_init(ctx, read, write, other, [sp]...) at 0x4000ed4c (UART) and 0x4000f5f0 (phone)
    for site, (lo, hi), want in ((0x4000ED4C, (0x4000ED20, 0x4000ED4C), {0x40033A24, 0x4000E764, 0x4000E83C, 0x4000F830, 0x4000E64C}),
                                 (0x4000F5F0, (0x4000F5C4, 0x4000F5F0), {0x40033BCC, 0x4000F02C, 0x4000F510, 0x4000E83C})):
        lits = {word(img, j.address + 8 + j.operands[1].mem.disp)
                for j in md.disasm(img[lo - BASE:hi - BASE], lo)
                if j.mnemonic == "ldr" and j.operands[1].type == ARM_OP_MEM and j.operands[1].mem.base == ARM_REG_PC}
        assert want <= lits, (hex(site), sorted(map(hex, want - lits)))
    print("  UART session (ctx 0x40033a24): read 0x4000e764 / write 0x4000e83c; local handler 0x4000e64c"
          " (receiver type 13); everything else -> 0x4000f830 = UART->phone aggregator")
    print("  phone session (ctx 0x40033bcc): read 0x4000f02c; everything not for the FX3 -> 0x4000e83c = UART write")
    # Android write: 0x55 / 0xCC header bytes, then type and length memcpy
    seq = [(i.mnemonic, i.op_str) for i in md.disasm(img[0x40003520 - BASE:0x40003564 - BASE], 0x40003520)]
    assert ("mov", "sl, #0x55") in seq and ("mvn", "r3, #0x33") in seq
    lits = [word(img, a) for a in range(0x4000f920, 0x4000f940, 4)]
    assert 0x5749 in lits, "DUML chunk type literal not found"
    print("  phone write (Android 0x400034e8): chunk = 55 CC <u16 type> <u32 len> <payload>;"
          " type 0x5749 = DUML (from 0x4000f830), 0x574A = video (from FPGA PIB2 buffers)")


def gpio_strap(img):
    print("\n## GPIO 41 boot strap selects the USB personality (V)")
    flag = [i for i in md.disasm(img[0x40008288 - BASE:0x40008294 - BASE], 0x40008288)]
    assert flag[0].mnemonic == "ldr" and word(img, 0x40008288 + 8 + flag[0].operands[1].mem.disp) == 0x40031626
    setup = [(i.mnemonic, i.op_str) for i in md.disasm(img[0x40008170 - BASE:0x40008184 - BASE], 0x40008170)]
    assert ("mov", "r0, #0x29") in setup  # GPIO 41 read via CyU3PGpioGetValue
    lo = {word(img, a) for a in range(0x400069c0, 0x40006a10, 4)}
    assert {0x40010440, 0x400104a0} <= lo, "pin-low path should load the iAP2 configs"
    hi = {word(img, a) for a in range(0x400069c0, 0x40006a20, 4)}
    assert {0x40010520, 0x40010560} <= hi, "pin-high path should load the plain-vendor configs"
    print("  GPIO41 low  -> iPhone iAP2 / Android AOA, UART DUML + 55 CC chunking (threads uart, usbsocket)")
    print("  GPIO41 high -> plain 0547:1002 device, AUTO EP2->PIB0 / PIB2->EP6 (DaVinci/HDMI-board RC)")


def main():
    img = load_cy(sys.argv[1])
    descriptors(img)
    channels(img)
    threads(img)
    routing(img)
    gpio_strap(img)


if __name__ == "__main__":
    main()
