# Jython: decompile m0305 (RAM-resident updater @0x20000000) flash-programming functions.
# Targets: functions referencing FLASH_IF MMIO (KEYR/OPTKEYR/SR/CR) and the flash region bases
# (0x08000000 loader, 0x08020000 app, 0x08100000 bank2). Answers: single-image vs A/B, does it
# reflash the loader, and what option bytes it writes.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/m0305_flash_dump.txt", "w")

targets = set()
# FLASH_IF registers + region bases referenced as literals/pointers
for a in (0x40023C00, 0x40023C04, 0x40023C08, 0x40023C0C, 0x40023C10, 0x40023C14,
          0x08000000, 0x08020000, 0x08100000):
    for r in refm.getReferencesTo(A(a)):
        f = fm.getFunctionContaining(r.getFromAddress())
        if f:
            targets.add(f)
out.write("== %d functions touch FLASH regs / region bases ==\n" % len(targets))
for f in sorted(targets, key=lambda x: x.getEntryPoint().getOffset()):
    out.write("  %s @ %s (%d B)\n" % (f.getName(), f.getEntryPoint(), f.getBody().getNumAddresses()))
out.write("\n")
for f in sorted(targets, key=lambda x: x.getEntryPoint().getOffset()):
    if f.getBody().getNumAddresses() > 2000:
        out.write("\n/* skip big %s */\n" % f.getName()); continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s ===== */\n" % (f.getName(), f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> m0305_flash_dump.txt (%d funcs)" % len(targets))
