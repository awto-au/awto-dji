# Jython (m0306 app): find where the app reads the STM32 UID (0x1FFF7A10) and where it calls/reads
# into the resident loader region (0x08000000-0x0801FFFF). Answers: is there a loader handoff / a
# UID-derived secret, and does the app call fixed loader entry points.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
listing = currentProgram.getListing()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/fc_loader_reads_dump.txt", "w")

# (1) UID: function(s) referencing the literal at 0x080852cc (holds 0x1FFF7A10)
targets = set()
for r in refm.getReferencesTo(A(0x080852cc)):
    f = fm.getFunctionContaining(r.getFromAddress())
    if f: targets.add(("UID", f))
# also any direct ref to 0x1FFF7A10
for r in refm.getReferencesTo(A(0x1FFF7A10)):
    f = fm.getFunctionContaining(r.getFromAddress())
    if f: targets.add(("UID", f))

# (2) calls/branches whose target lands in the loader region
out.write("== app refs that TARGET the loader region 0x08000000-0x0801FFFF ==\n")
lostart, loend = 0x08000000, 0x08020000
cnt = 0
it = refm.getReferenceIterator(A(lostart))
r = it.next() if it.hasNext() else None
# iterate all references in program whose toAddr is in loader range (bounded scan via refs to each)
# cheaper: walk functions, check their called/branched targets
for f in fm.getFunctions(True):
    for ref in []:
        pass
# fallback: scan references to a sample of loader addresses we found as pointers
for la in (0x0800f04e, 0x0800f04f, 0x0801e9c6, 0x0801f1a8, 0x08000100, 0x08000300, 0x0801f1a8):
    for r in refm.getReferencesTo(A(la)):
        f = fm.getFunctionContaining(r.getFromAddress())
        rt = r.getReferenceType()
        out.write("  loader %#010x <- %s %s (%s)\n" % (la, f.getName() if f else "?", r.getFromAddress(), rt))
        if f: targets.add(("LOADER:%08x" % la, f))

out.write("\n")
seen = set()
for tag, f in sorted(targets, key=lambda t: t[1].getEntryPoint().getOffset()):
    key = f.getEntryPoint().getOffset()
    if key in seen: continue
    seen.add(key)
    if f.getBody().getNumAddresses() > 2500:
        out.write("\n/* [%s] skip big %s @ %s */\n" % (tag, f.getName(), f.getEntryPoint())); continue
    res = dec.decompileFunction(f, 90, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== [%s] %s @ %s ===== */\n" % (tag, f.getName(), f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> fc_loader_reads_dump.txt (%d fns)" % len(seen))
