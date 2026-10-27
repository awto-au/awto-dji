# Find who WRITES the activation-state byte that FUN_08046d54 reads
# (*(byte*)(DAT_08047028 + 0x28)), to see the producer side (SDK key / activation
# authority check equivalent in this build).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
refmgr = currentProgram.getReferenceManager()
listing = currentProgram.getListing()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface()
dec.openProgram(currentProgram)
mon = ConsoleTaskMonitor()
out = open(SC + "/fc_actflag_writers_dump.txt", "w")

# First find the pointer DAT_08047028 value (what it points to)
f = fm.getFunctionContaining(A(0x08046d54))
out.write("FUN_08046d54 refs:\n")
for ins in listing.getInstructions(f.getBody(), True):
    for ref in ins.getReferencesFrom():
        out.write("  %s -> %s (%s)\n" % (ins.getAddress(), ref.getToAddress(), ref.getReferenceType()))

# refs to the pointer slot itself
refs = list(refmgr.getReferencesTo(A(0x08047028)))
out.write("\nrefs to DAT slot 0x08047028: %d\n" % len(refs))
caller_funcs = set()
for r in refs:
    out.write("  from=%s type=%s\n" % (r.getFromAddress(), r.getReferenceType()))
    cf = fm.getFunctionContaining(r.getFromAddress())
    if cf is not None:
        caller_funcs.add(cf)

for cf in caller_funcs:
    out.write("\n/* ----- %s @ %s ----- */\n" % (cf.getName(), cf.getEntryPoint()))
    res = dec.decompileFunction(cf, 150, mon)
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")

out.close()
print("-> fc_actflag_writers_dump.txt")
