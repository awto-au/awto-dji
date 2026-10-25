from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/fc_enable_dump.txt","w")
for a in (0x08064c9c,0x08064d9c,0x08055b9c,0x0805ca9a):
    f=fm.getFunctionContaining(A(a))
    if not f: print("no fn %#x"%a); continue
    res=dec.decompileFunction(f,90,mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s ===== */\n"%(f.getName(),f.getEntryPoint()))
        out.write(res.getDecompiledFunction().getC()); print("%s @ %s"%(f.getName(),f.getEntryPoint()))
out.close(); print("-> fc_enable_dump.txt")
