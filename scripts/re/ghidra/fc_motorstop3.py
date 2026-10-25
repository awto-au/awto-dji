# Found via raw-byte search: the pointer-to-the-"Product not activation,stop motor!"
# string actually lives at VA 0x080f2cd8 (a DAT_ slot), referencing the string copy at
# VA 0x080fba67 (near end of image -- the first copy at 0x080254a4 is unreferenced /
# dead, likely leftover/duplicate data). Find who reads DAT_080f2cd8.
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
out = open(SC + "/fc_motorstop3_dump.txt", "w")

ptr_addr = A(0x080f2cd8)
out.write("refs to DAT_080f2cd8 (ptr to motor-stop string):\n")
refs = list(refmgr.getReferencesTo(ptr_addr))
out.write("count=%d\n" % len(refs))
caller_funcs = set()
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    cf = fm.getFunctionContaining(r.getFromAddress())
    if cf is not None:
        caller_funcs.add(cf)

out.write("\ndistinct functions: %d\n" % len(caller_funcs))
for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_motorstop3_dump.txt")
