#!/usr/bin/env python3
import sys
import capstone

BASE = 0x08020000
path = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad/dec/P3X_FW_V01.11.0020_m0306.bin"
data = open(path, "rb").read()

lo = int(sys.argv[1], 16)
hi = int(sys.argv[2], 16)

md = capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB)
md.detail = False

off = lo - BASE
chunk = data[off:hi - BASE]
addr = lo
for ins in md.disasm(chunk, addr):
    print("0x%08x:  %-28s %s" % (ins.address, ins.mnemonic, ins.op_str))
