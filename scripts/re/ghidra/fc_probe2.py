from ghidra.util.task import ConsoleTaskMonitor

sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
listing = currentProgram.getListing()
fm = currentProgram.getFunctionManager()


def A(x):
    return sp.getAddress(x)


SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_probe2_dump.txt", "w")

for addr in [0x0809dd4b, 0x0809dd57, 0x0809dd65, 0x0809dd73, 0x0809dd83, 0x0809dceb, 0x0809dd91]:
    a = A(addr)
    cu = listing.getCodeUnitAt(a)
    ins = listing.getInstructionAt(a)
    f = fm.getFunctionContaining(a)
    out.write("%#x: codeunit=%s instr=%s func=%s\n" % (addr, cu, ins, f))

out.close()
print("-> fc_probe2_dump.txt")
