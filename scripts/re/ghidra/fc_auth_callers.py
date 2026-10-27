# Find and decompile the CALLERS of the three A9 auth-check functions in m0100sys,
# to see what each caller does with a nonzero (fail) return value.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.symbol import RefType

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_auth_callers_dump.txt", "w")

targets = [
    (0x0e85f370, "DjiMsgAuthorizedMac"),
    (0x0e871ae0, "DjiEncryptCheckA9Mac"),
    (0x0e8731cc, "DjiEncryptCheckSN"),
]

seen_funcs = set()

for addr, name in targets:
    target_addr = A(addr)
    tf = fm.getFunctionContaining(target_addr)
    out.write("\n\n########## CALLERS OF %s @ %#x ##########\n" % (name, addr))
    refs = list(refmgr.getReferencesTo(tf.getEntryPoint() if tf else target_addr))
    # also catch refs directly to the literal address in case function start differs
    if not refs:
        refs = list(refmgr.getReferencesTo(target_addr))
    call_sites = []
    for r in refs:
        if r.getReferenceType().isCall() or r.getReferenceType().isFlow():
            call_sites.append(r.getFromAddress())
    out.write("  raw ref count=%d call-type count=%d\n" % (len(refs), len(call_sites)))
    caller_funcs = set()
    for a in call_sites:
        cf = fm.getFunctionContaining(a)
        if cf is not None:
            caller_funcs.add(cf)
    out.write("  distinct caller functions: %d\n" % len(caller_funcs))
    for cf in caller_funcs:
        key = cf.getEntryPoint().toString()
        out.write("\n/* ----- caller %s @ %s calls %s ----- */\n" % (cf.getName(), cf.getEntryPoint(), name))
        if key in seen_funcs:
            out.write("  (already decompiled above, skipping body)\n")
            continue
        seen_funcs.add(key)
        res = dec.decompileFunction(cf, 120, mon)
        if res and res.decompileCompleted():
            out.write(res.getDecompiledFunction().getC())
        else:
            out.write("/* decompile failed */\n")

out.close()
print("-> fc_auth_callers_dump.txt")
