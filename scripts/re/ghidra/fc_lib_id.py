# Jython (fast, bounded): decompile the function cluster around rcc_get_clocks_freq to identify
# the ST register library (SPL vs LL vs HAL). No image scan, no getReferencesTo sweep: just walk
# getFunctionAfter/Before from the anchor and decompile <=16 small functions.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/fc_lib_id_dump.txt", "w")

anchor = fm.getFunctionContaining(A(0x0806d5f0))
allf = [x for x in fm.getFunctions(True)]
idx = next(i for i, x in enumerate(allf) if x.getEntryPoint().equals(anchor.getEntryPoint()))
funcs = allf[max(0, idx - 8): idx + 9]

for f in funcs:
    ln = f.getBody().getNumAddresses()
    if ln > 1200:
        out.write("\n/* skip %s @ %s (%d B) */\n" % (f.getName(), f.getEntryPoint(), ln)); continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), ln))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> fc_lib_id_dump.txt (%d funcs)" % len(funcs))
