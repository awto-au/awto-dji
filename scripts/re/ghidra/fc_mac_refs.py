# Dump ALL references (any type) to DjiMsgAuthorizedMac, in case it's called via
# a function-pointer table (cam_server dispatch) rather than a direct BL.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()
sym = currentProgram.getSymbolTable()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_mac_refs_dump.txt", "w")

addr = A(0x0e85f370)
f = fm.getFunctionContaining(addr)
out.write("function containing 0xe85f370: %s\n" % f)
if f:
    entry = f.getEntryPoint()
else:
    entry = addr

out.write("entry = %s\n" % entry)

# references TO the entry point
refs = list(refmgr.getReferencesTo(entry))
out.write("refs to entry: %d\n" % len(refs))
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))

# also check symbols at this address (any aliases) and references to those
symbols = sym.getSymbols(entry)
for s in symbols:
    out.write("symbol: %s\n" % s.getName())

# Scan a window around for any data reference landing exactly on entry (defensive)
out.close()
print("-> fc_mac_refs_dump.txt")
