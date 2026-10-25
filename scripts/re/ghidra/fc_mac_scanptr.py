# DjiMsgAuthorizedMac has zero references found via getReferencesTo -> likely called
# through a function-pointer table (dispatch table for DUML/"DjiMsg*" handlers) that
# Ghidra hasn't resolved as a reference. Scan all of memory for raw occurrences of the
# little-endian pointer value 0x0e85f370 and report the containing memory block + any
# function/data at that location, so we can inspect the table.
from ghidra.program.model.address import AddressSet

SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out = open(SC + "/fc_mac_scanptr_dump.txt", "w")

mem = currentProgram.getMemory()
fm = currentProgram.getFunctionManager()

target = 0x0e85f370
pat = bytearray([target & 0xff, (target >> 8) & 0xff, (target >> 16) & 0xff, (target >> 24) & 0xff])

hits = []
for block in mem.getBlocks():
    if not block.isInitialized():
        continue
    start = block.getStart()
    size = block.getSize()
    try:
        data = bytearray(size)
        mem.getBytes(start, data)
    except Exception as e:
        out.write("skip block %s: %s\n" % (block.getName(), e))
        continue
    idx = 0
    n = len(data)
    while True:
        idx = data.find(pat, idx)
        if idx == -1:
            break
        hitaddr = start.add(idx)
        hits.append(hitaddr)
        idx += 1

out.write("total raw pointer hits for 0x%08x: %d\n" % (target, len(hits)))
for h in hits:
    blk = mem.getBlock(h)
    f = fm.getFunctionContaining(h)
    out.write("  @ %s  block=%s  inFunc=%s\n" % (h, blk.getName() if blk else "?", f.getName() if f else "-"))

out.close()
print("-> fc_mac_scanptr_dump.txt (%d hits)" % len(hits))
