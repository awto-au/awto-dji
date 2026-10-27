# Base = 0x08020000 (confirmed via memory map). File offset of the
# "Product not activation,stop motor!" string in the raw .bin is 0x54a4, so its VA
# should be 0x080254a4. Verify directly and get references to it (and to the shorter
# "Product not activation" partial match) rather than relying on a bytearray scan.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()
mem = currentProgram.getMemory()
listing = currentProgram.getListing()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_motorstop2_dump.txt", "w")

va = 0x080254a4
addr = A(va)
out.write("addr=%s\n" % addr)
try:
    b = mem.getBytes(addr, 40)
    out.write("bytes: %s\n" % bytes(bytearray(b)))
except Exception as e:
    out.write("read error: %s\n" % e)

cu = listing.getCodeUnitAt(addr)
out.write("codeunit: %s\n" % cu)

refs = list(refmgr.getReferencesTo(addr))
out.write("direct refs to %#x: %d\n" % (va, len(refs)))
caller_funcs = set()
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    cf = fm.getFunctionContaining(r.getFromAddress())
    if cf is not None:
        caller_funcs.add(cf)

# Also scan a window around it for any ref landing within +/- 4 bytes (alignment slack)
for delta in range(-8, 9):
    a2 = addr.add(delta) if delta >= 0 else addr.subtract(-delta)
    rs = list(refmgr.getReferencesTo(a2))
    if rs:
        out.write("refs to %s (delta %d): %d\n" % (a2, delta, len(rs)))
        for r in rs:
            out.write("    from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
            cf = fm.getFunctionContaining(r.getFromAddress())
            if cf is not None:
                caller_funcs.add(cf)

out.write("\ndistinct functions: %d\n" % len(caller_funcs))
for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 120, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_motorstop2_dump.txt")
