# Jython: find m0305's DUML command parser / dispatcher and the descriptor-type assignment, to
# enumerate the upgrade command surface and target types 0..7 (6/7 known = bank1/bank2).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_parser_dump.txt", "w")

# FUN_2000723c is a frame handler (reads sender type, calls descriptor setup). Walk its callers up
# to the dispatcher, and decompile the dispatcher + the descriptor-type setters (callers of the
# erase-by-type FUN_20008c88 and descriptor setup FUN_20008cd0).
roots = set([0x2000723c, 0x20008c88, 0x20008cd0])
frontier = list(roots)
for _ in range(2):  # two levels of callers
    nxt = []
    for off in frontier:
        f = fm.getFunctionContaining(A(off))
        if not f: continue
        for r in refm.getReferencesTo(f.getEntryPoint()):
            if r.getReferenceType().isCall():
                cf = fm.getFunctionContaining(r.getFromAddress())
                if cf and cf.getEntryPoint().getOffset() not in roots:
                    roots.add(cf.getEntryPoint().getOffset()); nxt.append(cf.getEntryPoint().getOffset())
    frontier = nxt

seen = set()
for off in sorted(roots):
    if off in seen: continue
    seen.add(off)
    f = fm.getFunctionContaining(A(off))
    if not f: continue
    n = f.getBody().getNumAddresses()
    if n > 2600:
        out.write("\n/* skip big %s @ %s (%dB) */\n" % (f.getName(), f.getEntryPoint(), n)); continue
    res = dec.decompileFunction(f, 90, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%dB) ===== */\n" % (f.getName(), f.getEntryPoint(), n))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> m0305_parser_dump.txt (%d fns)" % len(seen))
