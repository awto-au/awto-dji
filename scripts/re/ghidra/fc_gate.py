from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/fc_gate_dump.txt","w")
for a in (0x08064d38,0x0805cb70,0x0805ca9a):
    f=fm.getFunctionContaining(A(a))
    if not f: 
        print("no fn at %#x"%a); continue
    res=dec.decompileFunction(f,90,mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s ===== */\n"%(f.getName(),f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC())
        print("%s @ %s len=%d"%(f.getName(),f.getEntryPoint(),len(res.getDecompiledFunction().getC())))
out.close(); print("-> fc_gate_dump.txt")
