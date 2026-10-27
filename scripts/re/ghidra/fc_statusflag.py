# Find who READS the status flag at *DAT_0e861450 (written 0/1/2 by FUN_0e860560,
# which is fed the A9Mac+CheckSN pass/fail result) and decompile those readers, to see
# whether a fail value gates anything beyond a reported status.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.symbol import SourceType

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
out = open(SC + "/fc_statusflag_dump.txt", "w")

# FUN_0e860560 does: *DAT_0e861450 = param_1;  -- find the pointer variable DAT_0e861450
# and then where IT is defined (what address it actually points to), then refs to that addr.

f = fm.getFunctionContaining(A(0x0e860560))
out.write("FUN_0e860560 body refs (data) within function body:\n")
insns = listing.getInstructions(f.getBody(), True)
for ins in insns:
    for ref in ins.getReferencesFrom():
        out.write("  %s -> %s (%s)\n" % (ins.getAddress(), ref.getToAddress(), ref.getReferenceType()))

out.close()
print("-> fc_statusflag_dump.txt")
