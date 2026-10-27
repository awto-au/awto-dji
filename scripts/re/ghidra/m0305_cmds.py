# Jython: find m0305's DUML command dispatcher and enumerate the commands it accepts; look for a
# READ-memory / VERIFY (CRC-over-flash) handler. Strategy: the dispatcher is the common caller of
# the flash primitives (erase FUN_2000156c, the program fn, the boot fns 20007ec0/edc, blank-check
# 20007a08/81c8). Dump callers, then decompile the handler(s) + anything that reads a flash span.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_cmds_dump.txt", "w")

prims = {0x2000156c: "flash_erase_sector", 0x20007ec0: "boot_slotA", 0x20007edc: "boot_slotB",
         0x20007a08: "blankcheck_slotA", 0x200081c8: "blankcheck_slotB", 0x20001660: "ob_unlock"}
callers = {}
for a, nm in prims.items():
    cs = set()
    for r in refm.getReferencesTo(A(a)):
        if r.getReferenceType().isCall():
            f = fm.getFunctionContaining(r.getFromAddress())
            if f: cs.add(f.getEntryPoint().getOffset())
    out.write("callers of %-20s @%08x : %s\n" % (nm, a, [hex(x) for x in sorted(cs)]))
    for off in cs:
        callers[off] = callers.get(off, 0) + 1

# dispatcher = caller touching the most distinct primitives
ranked = sorted(callers.items(), key=lambda kv: -kv[1])
out.write("\n== candidate dispatchers (by # of flash/boot prims they call) ==\n")
for off, n in ranked[:8]:
    f = fm.getFunctionContaining(A(off))
    out.write("  %s @ %s : %d prims, %d B\n" % (f.getName(), f.getEntryPoint(), n, f.getBody().getNumAddresses()))

# decompile the top candidates + their immediate callers (the command switch is often one level up)
seen = set()
def emit(f):
    if f is None or f.getEntryPoint().getOffset() in seen: return
    seen.add(f.getEntryPoint().getOffset())
    if f.getBody().getNumAddresses() > 3000:
        out.write("\n/* skip big %s */\n" % f.getName()); return
    res = dec.decompileFunction(f, 90, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses()))
        out.write(res.getDecompiledFunction().getC())

for off, n in ranked[:4]:
    f = fm.getFunctionContaining(A(off)); emit(f)
    for r in refm.getReferencesTo(f.getEntryPoint()):
        if r.getReferenceType().isCall():
            emit(fm.getFunctionContaining(r.getFromAddress()))
out.close(); print("-> m0305_cmds_dump.txt")
