from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); mem=currentProgram.getMemory()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
def r32(a): return mem.getInt(A(a))&0xffffffff
def r8(a): return mem.getByte(A(a))&0xff
tbl=r32(0x08065074)
print("arbitration table @ %#x (stride 0xc):"%tbl)
for i in range(4):
    base=tbl+i*0xc
    code=r8(base); pred=r32(base+4)
    f=fm.getFunctionContaining(A(pred&~1)) if pred else None
    print("  [%d] device_code=%d predicate=%#x %s"%(i,code,pred&~1 if pred else 0, f.getName() if f else '-'))
# decompile predicates
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out=open(SC+"/fc_arb_dump.txt","w")
seen=set()
for i in range(4):
    pred=r32(tbl+i*0xc+4)
    if not pred or pred in seen: continue
    seen.add(pred); f=fm.getFunctionContaining(A(pred&~1))
    if f:
        res=dec.decompileFunction(f,60,mon)
        if res and res.decompileCompleted():
            out.write("\n/* pred[%d] code=%d %s @ %s */\n"%(i,r8(tbl+i*0xc),f.getName(),f.getEntryPoint()))
            out.write(res.getDecompiledFunction().getC())
out.close(); print("-> fc_arb_dump.txt")
