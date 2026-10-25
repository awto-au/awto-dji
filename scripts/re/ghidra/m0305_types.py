# Jython: find what region/target "types" 0..7 are, and whether the slot is externally selectable.
# (1) decompile the initializer that populates the region/descriptor table (writes the 0x08.. bases
#     and the type/id fields) -> enumerates all targets.
# (2) decompile the boot-gate chain (FUN_20006f04 -> FUN_20008280) -> external force/select signal.
# (3) decompile the descriptor-setup siblings of FUN_20008cd0 (which wrote type=6).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_types_dump.txt", "w")

want = []
# who writes to the region table region (0x2000a490..0x2000a4f0)? -> the initializer(s)
for off in range(0x2000a490, 0x2000a4f0, 4):
    for r in refm.getReferencesTo(A(off)):
        if r.getReferenceType().isWrite():
            f = fm.getFunctionContaining(r.getFromAddress())
            if f: want.append(f.getEntryPoint().getOffset())
# boot-gate source + descriptor setup + anything referencing the region table pointers
want += [0x20008280, 0x20006f04, 0x20008cd0]
# callers of the descriptor setup FUN_20008cd0 (sibling setups / the selector)
for r in refm.getReferencesTo(A(0x20008cd0)):
    if r.getReferenceType().isCall():
        f = fm.getFunctionContaining(r.getFromAddress())
        if f: want.append(f.getEntryPoint().getOffset())

seen = set()
for off in want:
    if off in seen: continue
    seen.add(off)
    f = fm.getFunctionContaining(A(off))
    if not f: continue
    if f.getBody().getNumAddresses() > 3500:
        out.write("\n/* skip big %s @ %s (%dB) */\n" % (f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses())); continue
    res = dec.decompileFunction(f, 90, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%dB) ===== */\n" % (f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> m0305_types_dump.txt (%d fns)" % len(seen))
