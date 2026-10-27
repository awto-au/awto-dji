# Real (this-build) addresses recovered via raw capstone disassembly + the log-string
# table: the activation-check wrapper is at 0x0809dd72 (calls FUN_08046d54), registered
# in the ~29-entry preflight-check table consumed by the master loop at 0x0809dda4,
# whose own "any check failed?" wrapper is at 0x0809de70. Find callers of all three.
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
out = open(SC + "/fc_motorstop5_dump.txt", "w")


def handle(addr, label, create=False):
    a = A(addr)
    f = fm.getFunctionContaining(a)
    out.write("\n=== %s @ %#x -> %s ===\n" % (label, addr, f))
    if f is None and create:
        from ghidra.app.cmd.function import CreateFunctionCmd
        CreateFunctionCmd(a).applyTo(currentProgram)
        f = fm.getFunctionContaining(a)
        out.write("  (force-created) now: %s\n" % f)
    if f is None:
        return
    res = dec.decompileFunction(f, 180, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")
    refs = list(refmgr.getReferencesTo(f.getEntryPoint()))
    out.write("-- callers (%d refs) --\n" % len(refs))
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


handle(0x08046d54, "FUN_08046d54 (real activation-state check)", create=True)
handle(0x0809dd72, "wrapper @ dd72 (activation check, table entry)", create=True)
handle(0x0809dda4, "master preflight-check loop (29 entries)", create=True)
handle(0x0809de70, "any-check-failed accessor", create=True)

out.close()
print("-> fc_motorstop5_dump.txt")
