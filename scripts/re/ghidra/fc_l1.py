from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
crc=fm.getFunctionContaining(A(0x0804f024))
l1=set()
for r in refm.getReferencesTo(crc.getEntryPoint()):
    if r.getReferenceType().isCall():
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: l1.add(cf)
out=open(SC+"/fc_l1_dump.txt","w")
# score each by presence of byte-field reads suggestive of DUML frame parse
import re
for f in sorted(l1,key=lambda x:x.getEntryPoint().getOffset()):
    res=dec.decompileFunction(f,60,mon)
    if not res or not res.decompileCompleted(): continue
    c=res.getDecompiledFunction().getC()
    # heuristics
    score=0
    for pat in ["& 0x1f","& 0x1fU","0x55","[9]","[10]","[5]","[0xa]","cmd","set","switch"]:
        score+=c.count(pat)
    ncallers=len([r for r in refm.getReferencesTo(f.getEntryPoint()) if r.getReferenceType().isCall()])
    out.write("\n/* ===== %s @ %s  score=%d callers=%d len=%d ===== */\n"%(f.getName(),f.getEntryPoint(),score,ncallers,len(c)))
    out.write(c)
    print("%s @ %s score=%d callers=%d len=%d"%(f.getName(),f.getEntryPoint(),score,ncallers,len(c)))
out.close(); print("-> fc_l1_dump.txt")
