# Find the "Product not activation" string in m0306, who references it, and decompile
# that function plus its caller(s) to nail down the real motor-start activation gate.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.util import DefinedDataIterator

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()
mem = currentProgram.getMemory()

SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_motorstop_dump.txt", "w")

needle = b"Product not activation"
hits = []
for block in mem.getBlocks():
    if not block.isInitialized():
        continue
    start = block.getStart()
    size = block.getSize()
    try:
        data = bytearray(size)
        mem.getBytes(start, data)
    except Exception:
        continue
    idx = 0
    bdata = bytes(data)
    while True:
        idx = bdata.find(needle, idx)
        if idx == -1:
            break
        hits.append(start.add(idx))
        idx += 1

out.write("string hits: %d\n" % len(hits))
for h in hits:
    out.write("  @ %s\n" % h)

caller_funcs = set()
for h in hits:
    refs = list(refmgr.getReferencesTo(h))
    out.write("\nrefs to string @ %s: %d\n" % (h, len(refs)))
    for r in refs:
        out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
        cf = fm.getFunctionContaining(r.getFromAddress())
        if cf is not None:
            caller_funcs.add(cf)

out.write("\ndistinct functions referencing the string: %d\n" % len(caller_funcs))
for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_motorstop_dump.txt (%d string hits, %d funcs)" % (len(hits), len(caller_funcs)))
