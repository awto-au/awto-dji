from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/fc_uid_users_dump.txt","w")
cs=set()
for r in refm.getReferencesTo(A(0x0808527a)):
    if r.getReferenceType().isCall():
        f=fm.getFunctionContaining(r.getFromAddress())
        if f: cs.add(f.getEntryPoint().getOffset())
out.write("callers of uid96_read: %s\n"%[hex(x) for x in sorted(cs)])
for off in sorted(cs):
    f=fm.getFunctionContaining(A(off))
    if f.getBody().getNumAddresses()>2500:
        out.write("\n/* skip big %s */\n"%f.getName()); continue
    res=dec.decompileFunction(f,90,mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s ===== */\n"%(f.getName(),f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> fc_uid_users_dump.txt")
