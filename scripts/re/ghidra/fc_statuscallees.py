# Decompile the handful of helper functions referenced from the status-gated call
# sites, to identify what subsystem they touch (strings / register-like patterns).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_statuscallees_dump.txt", "w")

targets = [0x0e81aeac, 0x0e866470, 0x0e839690, 0x0e89a998, 0x0e8a5a78, 0x0e83c024, 0x0e864ca0]
for addr in targets:
    f = fm.getFunctionContaining(A(addr))
    out.write("\n\n/* ===== %#x -> %s ===== */\n" % (addr, f.getName() if f else "?"))
    if f is None:
        continue
    res = dec.decompileFunction(f, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_statuscallees_dump.txt")
