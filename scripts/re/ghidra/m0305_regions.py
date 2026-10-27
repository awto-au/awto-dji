# Jython: find and decompile the function(s) that use the region descriptor table (loader/app/bank2
# bases at 0x2000a498/a4ac/a4c8) to see target selection: single image vs A/B, loader reflash.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
listing = currentProgram.getListing()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_regions_dump.txt", "w")

# dump the region table bytes
out.write("== region table @0x2000a490..0x2000a4e0 ==\n")
mem = currentProgram.getMemory()
import struct
b = bytearray(0x60); mem.getBytes(A(0x2000a490), b)
for i in range(0, 0x60, 4):
    out.write("  0x%08x: 0x%08x\n" % (0x2000a490 + i, struct.unpack_from("<I", b, i)[0]))

targets = set()
for a in (0x2000a490, 0x2000a498, 0x2000a4ac, 0x2000a4c8, 0x2000a4a0, 0x2000a4b0):
    for r in refm.getReferencesTo(A(a)):
        f = fm.getFunctionContaining(r.getFromAddress())
        if f: targets.add(f)
out.write("\n== %d functions reference the region table ==\n" % len(targets))
for f in sorted(targets, key=lambda x: x.getEntryPoint().getOffset()):
    if f.getBody().getNumAddresses() > 2500:
        out.write("\n/* skip big %s */\n" % f.getName()); continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s ===== */\n" % (f.getName(), f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> m0305_regions_dump.txt (%d funcs)" % len(targets))
