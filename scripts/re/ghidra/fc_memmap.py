from ghidra.util.task import ConsoleTaskMonitor

mem = currentProgram.getMemory()
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_memmap_dump.txt", "w")
for b in mem.getBlocks():
    out.write("%s start=%s end=%s size=%#x init=%s\n" % (b.getName(), b.getStart(), b.getEnd(), b.getSize(), b.isInitialized()))
out.close()
print("-> fc_memmap_dump.txt")
