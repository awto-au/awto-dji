# Jython: (1) read the DAT_* constants feeding RCC_GetClocksFreq (HSE/HSI values, presc table),
# (2) find the real PLLCFGR / CFGR *writes* (SystemInit) by scanning for stores to 0x40023804/08,
# (3) decompile whatever function holds them.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
import struct
mem = currentProgram.getMemory()
fm = currentProgram.getFunctionManager()
listing = currentProgram.getListing()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
def u32(a):
    b = bytearray(4); mem.getBytes(A(a), b); return struct.unpack("<I", bytes(b))[0]
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_clk2_dump.txt", "w")

out.write("==== DAT constants (literal pool) ====\n")
for name, a in [("DAT_0806d828 (RCC base ptr)",0x0806d828),("DAT_0806d844 (HSI?)",0x0806d844),
                ("DAT_0806d848 (HSE?)",0x0806d848),("DAT_0806d84c (presc table ptr)",0x0806d84c)]:
    v = u32(a); out.write("  %-30s @%08x = 0x%08x (%d)\n" % (name, a, v, v))
# dump presc table bytes (AHB then APB), table pointer is value at 0806d84c
tbl = u32(0x0806d84c)
b = bytearray(24); mem.getBytes(A(tbl), b)
out.write("  presc table @%08x: %s\n" % (tbl, " ".join("%d"%x for x in b)))

# scan .text for stores feeding RCC+4 (PLLCFGR) / RCC+8 (CFGR). The compiler loads the full
# immediate from a literal pool then str to the register, so scan literal pools for 0x40023804/08
# base loads and for plausible PLLCFGR words. Simpler: find all 32-bit words in image equal to a
# PLLCFGR-shaped value is noisy; instead find functions that reference RCC base 0x40023800 AND
# contain a str with a large immediate. Fall back: decompile SystemInit candidates (called very
# early, write multiple RCC regs). We locate by: literal pool entries == 0x40023800 used as base.
RCC = 0x40023800
block = mem.getBlock(A(0x08020000))
start = block.getStart().getOffset(); end = block.getEnd().getOffset()
hits = []
a = start
data = bytearray(end - start + 1); mem.getBytes(A(start), data)
for i in range(0, len(data)-3, 4):
    w = struct.unpack_from("<I", data, i)[0]
    if w == RCC or w == 0x40023804 or w == 0x40023808:
        hits.append((start+i, w))
out.write("\n==== literal-pool refs to RCC base/PLLCFGR/CFGR ====\n")
for a, w in hits:
    out.write("  pool @%08x = 0x%08x\n" % (a, w))

out.close(); print("-> fc_clk2_dump.txt (%d pool hits)" % len(hits))
