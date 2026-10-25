# Third hop: decompile FUN_0e860560 (the status-setter called with 0/1 after the
# A9Mac+SN retry loop) and find ITS callers/readers, plus the callers of FUN_0e872bb8
# and FUN_0e8475b8 one level further up, to see where the fail status ultimately lands.
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
out = open(SC + "/fc_auth_callers3_dump.txt", "w")


def dump_callers_of(addr, label):
    target_addr = A(addr)
    tf = fm.getFunctionContaining(target_addr)
    out.write("\n\n########## CALLERS OF %s @ %#x ##########\n" % (label, addr))
    if tf is None:
        out.write("  no function at this address\n")
        return
    refs = list(refmgr.getReferencesTo(tf.getEntryPoint()))
    out.write("  raw ref count=%d\n" % len(refs))
    for r in refs:
        out.write("    from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    caller_funcs = set()
    for r in refs:
        cf = fm.getFunctionContaining(r.getFromAddress())
        if cf is not None:
            caller_funcs.add(cf)
    out.write("  distinct caller functions: %d\n" % len(caller_funcs))
    for cf in caller_funcs:
        out.write("\n/* ----- caller %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
        res = dec.decompileFunction(cf, 120, mon)
        if res and res.decompileCompleted():
            out.write(res.getDecompiledFunction().getC())
        else:
            out.write("/* decompile failed */\n")


# First, the function itself
target_addr = A(0x0e860560)
tf = fm.getFunctionContaining(target_addr)
out.write("########## FUN_0e860560 itself ##########\n")
if tf is None:
    out.write("no function at 0x0e860560\n")
else:
    res = dec.decompileFunction(tf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

dump_callers_of(0x0e860560, "FUN_0e860560 (status setter)")
dump_callers_of(0x0e872bb8, "FUN_0e872bb8 (A9Mac/SN retry+status wrapper)")
dump_callers_of(0x0e8475b8, "FUN_0e8475b8 (cmd dispatch incl CheckSN case 3)")

out.close()
print("-> fc_auth_callers3_dump.txt")
