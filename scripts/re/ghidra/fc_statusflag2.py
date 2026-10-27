# The security status flag actually lives in RAM at 0x109d00b8 (written by
# FUN_0e860560). Find every reader/writer of that address across the whole program.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_statusflag2_dump.txt", "w")

ram_addr = A(0x109d00b8)
out.write("refs TO 0x109d00b8:\n")
refs = list(refmgr.getReferencesTo(ram_addr))
out.write("count=%d\n" % len(refs))
caller_funcs = set()
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    cf = fm.getFunctionContaining(r.getFromAddress())
    if cf is not None:
        caller_funcs.add(cf)

out.write("\ndistinct functions touching it: %d\n" % len(caller_funcs))
for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_statusflag2_dump.txt")
