# m0306 FC: decompile is_prod_activated / check_activation_authority and walk UP to
# find the actual motor-start gate ("Product not activation,stop motor!").
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
out = open(SC + "/fc_activation_gate_dump.txt", "w")


def decomp(addr, label):
    f = fm.getFunctionContaining(A(addr))
    out.write("\n\n/* ===== %s @ %#x -> %s ===== */\n" % (label, addr, f.getName() if f else "?"))
    if f is None:
        out.write("  no function\n")
        return None
    res = dec.decompileFunction(f, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")
    return f


def callers_of(f, label):
    if f is None:
        return []
    refs = list(refmgr.getReferencesTo(f.getEntryPoint()))
    out.write("\n-- callers of %s @ %s: %d refs --\n" % (label, f.getEntryPoint(), len(refs)))
    caller_funcs = set()
    for r in refs:
        out.write("   from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
        cf = fm.getFunctionContaining(r.getFromAddress())
        if cf is not None:
            caller_funcs.add(cf)
    return list(caller_funcs)


f1 = decomp(0x08047c2c, "is_prod_activated")
f2 = decomp(0x08047d5e, "check_activation_authority")

callers1 = callers_of(f1, "is_prod_activated")
callers2 = callers_of(f2, "check_activation_authority")

seen = set()
for cf in set(callers1 + callers2):
    key = cf.getEntryPoint().toString()
    if key in seen:
        continue
    seen.add(key)
    out.write("\n\n/* ----- caller %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_activation_gate_dump.txt")
