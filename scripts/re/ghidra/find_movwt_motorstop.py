#!/usr/bin/env python3
"""Scan P3X_FW_V01.11.0020_m0306.bin (Thumb-2, base 0x08020000) for
MOVW/MOVT pairs that build the address of the "Product not activation,stop
motor!" string (0x080254a4), to find the real caller(s) in THIS firmware
build (the doc's cached addresses are from a different build's symbol map).
"""
import sys
import capstone

BASE = 0x08020000
TARGET = 0x080254a4

path = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad/dec/P3X_FW_V01.11.0020_m0306.bin"
data = open(path, "rb").read()

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
md.detail = True

# naive linear disasm over the whole image; track last MOVW dest reg -> imm
pending = {}  # reg -> low16
hits = []

addr = BASE
offset = 0
while offset < len(data) - 4:
    chunk = data[offset:offset + 4]
    try:
        insns = list(md.disasm(chunk, addr, count=1))
    except Exception:
        insns = []
    if not insns:
        offset += 2
        addr += 2
        continue
    ins = insns[0]
    mnem = ins.mnemonic
    if mnem == "movw" and ins.operands:
        # operand 0 = reg, operand 1 = imm
        try:
            reg = ins.reg_name(ins.operands[0].reg)
            imm = ins.operands[1].imm
            pending[reg] = (imm, ins.address)
        except Exception:
            pass
    elif mnem == "movt" and ins.operands:
        try:
            reg = ins.reg_name(ins.operands[0].reg)
            imm = ins.operands[1].imm
            if reg in pending:
                low, lo_addr = pending[reg]
                full = (imm << 16) | low
                if full == TARGET:
                    hits.append((lo_addr, ins.address, reg))
        except Exception:
            pass
    offset += ins.size
    addr += ins.size

print("MOVW/MOVT hits constructing 0x%08x: %d" % (TARGET, len(hits)))
for lo, hi, reg in hits:
    print("  movw @ 0x%08x / movt @ 0x%08x -> %s" % (lo, hi, reg))
