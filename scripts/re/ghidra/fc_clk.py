# Jython: decompile the clock/peripheral init so the I/O inventory has real numbers.
# RCC clock-init (around the RCC_PLLCFGR/CFGR writers fc_io.py found), plus the CAN / USART /
# SDIO / TIM setup functions, and a raw instruction dump around each RCC writer so the
# runtime-computed PLL words can be read from the constant loads feeding them.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager()
refm = currentProgram.getReferenceManager()
listing = currentProgram.getListing()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()

out = open(SC + "/fc_clk_dump.txt", "w")

# 1) functions that write RCC_PLLCFGR / RCC_CFGR (clock tree) + the peripheral base addrs
#    whose init we want. Resolve each seed address to its containing function.
seeds = [0x0806d5f6, 0x0806d616, 0x0806d646, 0x0806d658, 0x0806d668]
targets = set()
for a in seeds:
    f = fm.getFunctionContaining(A(a))
    if f: targets.add(f)

out.write("==== RCC clock-init decompiled ====\n")
for f in sorted(targets, key=lambda x: x.getEntryPoint().getOffset()):
    res = dec.decompileFunction(f, 120, mon)
    if not res or not res.decompileCompleted():
        out.write("\n/* %s @ %s : decompile failed */\n" % (f.getName(), f.getEntryPoint())); continue
    out.write("\n/* ===== %s @ %s ===== */\n" % (f.getName(), f.getEntryPoint()))
    out.write(res.getDecompiledFunction().getC())

# 2) raw instruction window around each RCC writer (constant loads feed the store)
out.write("\n\n==== raw instructions around RCC writers ====\n")
for a in seeds:
    out.write("\n-- window @ %08x --\n" % a)
    ins = listing.getInstructionAt(A(a - 0x28))
    n = 0
    while ins is not None and n < 32:
        off = ins.getAddress().getOffset()
        if off > a + 0x10: break
        out.write("  %08x  %s\n" % (off, ins.toString()))
        ins = ins.getNext(); n += 1

out.close()
print("-> fc_clk_dump.txt")
