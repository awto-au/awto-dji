# Jython (bounded): second, independent library-ID probe via the init path.
# Callers of the RCC clock-enable fn (0x0806d716) are peripheral bring-up functions; they call
# GPIO_Init / USART_Init style helpers. Decompile up to ~12 callers and the 2-arg helpers they
# invoke, so the init-struct layout (SPL vs HAL vs LL fingerprint) is visible.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/fc_lib_id2_dump.txt", "w")

callers = set()
for a in (0x0806d716, 0x0806d752, 0x0806d766):   # AHB1 / APB1 / APB2 clock cmd
    for r in refm.getReferencesTo(A(a)):
        if r.getReferenceType().isCall():
            f = fm.getFunctionContaining(r.getFromAddress())
            if f: callers.add(f)

out.write("== %d callers of RCC clock-enable ==\n" % len(callers))
done = set(); callees = set()
for f in sorted(callers, key=lambda x: x.getEntryPoint().getOffset())[:12]:
    ln = f.getBody().getNumAddresses()
    if ln > 1500:
        out.write("\n/* skip %s (%d B) */\n" % (f.getName(), ln)); continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== CALLER %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), ln))
        hf = res.getHighFunction()
        out.write(res.getDecompiledFunction().getC())
        done.add(f.getEntryPoint().getOffset())
        # collect direct callees (candidate GPIO_Init/USART_Init)
        for c in f.getCalledFunctions(mon):
            callees.add(c)

out.write("\n\n==== candidate init helpers (callees) ====\n")
for f in sorted(callees, key=lambda x: x.getEntryPoint().getOffset()):
    if f.getEntryPoint().getOffset() in done: continue
    ln = f.getBody().getNumAddresses()
    if ln > 900 or ln < 20: continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        c = res.getDecompiledFunction().getC()
        # only keep helpers that look like peripheral init (write via a pointer param)
        if ("param_1" in c and ("0x20" in c or "0x24" in c or "MODER" in c or "<< " in c)) or "BRR" in c:
            out.write("\n/* ===== HELPER %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), ln))
            out.write(c)
out.close(); print("-> fc_lib_id2_dump.txt (%d callers, %d callees)" % (len(callers), len(callees)))
