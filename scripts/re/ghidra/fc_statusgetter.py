# Find and decompile the callers of the status getter FUN_0e8605fc (reads the A9Mac/SN
# pass-fail status flag), to see where that status value is consumed.
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
out = open(SC + "/fc_statusgetter_dump.txt", "w")

target_addr = A(0x0e8605fc)
tf = fm.getFunctionContaining(target_addr)
refs = list(refmgr.getReferencesTo(tf.getEntryPoint()))
out.write("refs to FUN_0e8605fc: %d\n" % len(refs))
caller_funcs = set()
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    cf = fm.getFunctionContaining(r.getFromAddress())
    if cf is not None:
        caller_funcs.add(cf)

out.write("\ndistinct callers: %d\n" % len(caller_funcs))
for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_statusgetter_dump.txt")
