# The log-record table at 0x080f2cd8 pairs {call_site_pc, string_ptr, id}. For the
# "Product not activation,stop motor!" string (0x080fba67) the call_site_pc is
# 0x0809dd73. Decompile the function containing that call site -- this is the real
# motor-start activation gate in THIS firmware build.
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
out = open(SC + "/fc_motorstop4_dump.txt", "w")

call_site = A(0x0809dd73)
f = fm.getFunctionContaining(call_site)
out.write("function containing call site 0x0809dd73: %s (entry %s)\n" % (f, f.getEntryPoint() if f else None))
if f is not None:
    res = dec.decompileFunction(f, 180, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

    # callers of this gate function
    refs = list(refmgr.getReferencesTo(f.getEntryPoint()))
    out.write("\n\n-- callers of %s @ %s: %d refs --\n" % (f.getName(), f.getEntryPoint(), len(refs)))
    caller_funcs = set()
    for r in refs:
        out.write("   from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
        cf = fm.getFunctionContaining(r.getFromAddress())
        if cf is not None:
            caller_funcs.add(cf)
    for cf in caller_funcs:
        out.write("\n/* ----- caller %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
        res = dec.decompileFunction(cf, 180, mon)
        if res and res.decompileCompleted():
            out.write(res.getDecompiledFunction().getC())
        else:
            out.write("/* decompile failed */\n")

out.close()
print("-> fc_motorstop4_dump.txt")
