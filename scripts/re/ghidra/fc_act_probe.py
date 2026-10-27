# Probe exactly what's at 0x08047c2c / 0x08047d5e: symbol table entries, function
# objects (getFunctionAt vs getFunctionContaining), and raw disassembly around them.
from ghidra.util.task import ConsoleTaskMonitor

fm = currentProgram.getFunctionManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
sym = currentProgram.getSymbolTable()
listing = currentProgram.getListing()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_act_probe_dump.txt", "w")

for addr in [0x08047c2c, 0x08047d5e, 0x0805a964]:
    a = A(addr)
    out.write("\n=== %#x ===\n" % addr)
    fat = fm.getFunctionAt(a)
    fcont = fm.getFunctionContaining(a)
    out.write("getFunctionAt: %s\n" % fat)
    out.write("getFunctionContaining: %s (entry=%s)\n" % (fcont, fcont.getEntryPoint() if fcont else None))
    syms = sym.getSymbols(a)
    for s in syms:
        out.write("  symbol: %s type=%s\n" % (s.getName(), s.getSymbolType()))
    cu = listing.getCodeUnitAt(a)
    out.write("codeunit@addr: %s\n" % cu)
    # dump a few instructions before/after
    ins = listing.getInstructionAt(a)
    out.write("instructionAt: %s\n" % ins)

out.close()
print("-> fc_act_probe_dump.txt")
