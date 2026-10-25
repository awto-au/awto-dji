# Jython: confirm m0305's VERIFY (FUN_20008d14) and search for a READ/dump-flash command.
# Decompile the verify + boot-gate + erase-by-type command processor, and flag any function that
# reads a flash span (0x08xxxxxx) and also calls a CAN/DUML transmit (a read-back/dump path).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_verify_dump.txt", "w")

want = [0x20008d14, 0x20006f04, 0x20008c88, 0x20008cd0]
# plus callers of the erase-by-type FUN_20008c88 (the command processor)
for r in refm.getReferencesTo(A(0x20008c88)):
    if r.getReferenceType().isCall():
        f = fm.getFunctionContaining(r.getFromAddress())
        if f: want.append(f.getEntryPoint().getOffset())

seen = set()
for off in want:
    if off in seen: continue
    seen.add(off)
    f = fm.getFunctionContaining(A(off))
    if not f: continue
    if f.getBody().getNumAddresses() > 3000:
        out.write("\n/* skip big %s @ %s */\n" % (f.getName(), f.getEntryPoint())); continue
    res = dec.decompileFunction(f, 90, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> m0305_verify_dump.txt")
