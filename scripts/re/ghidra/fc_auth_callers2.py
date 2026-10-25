# Second hop: find and decompile the callers of the two wrapper functions that call
# DjiEncryptCheckA9Mac / DjiEncryptCheckSN, to see what the next level up does with a
# nonzero return.
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
out = open(SC + "/fc_auth_callers2_dump.txt", "w")

targets = [
    (0x0e8734fc, "FUN_0e8734fc (CheckA9Mac+CheckSN wrapper)"),
    (0x0e83c59c, "FUN_0e83c59c (CheckSN caller, cmd-table style)"),
]

for addr, name in targets:
    target_addr = A(addr)
    tf = fm.getFunctionContaining(target_addr)
    out.write("\n\n########## CALLERS OF %s @ %#x ##########\n" % (name, addr))
    refs = list(refmgr.getReferencesTo(tf.getEntryPoint() if tf else target_addr))
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

out.close()
print("-> fc_auth_callers2_dump.txt")
