from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import StringDataType
import jarray
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
mem=currentProgram.getMemory(); listing=currentProgram.getListing()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
B=0x08020000; SZ=0x8120000-B
barr=jarray.zeros(SZ,'b'); mem.getBytes(A(B),barr)
def u32(a):
    o=a-B; return (barr[o]&0xff)|((barr[o+1]&0xff)<<8)|((barr[o+2]&0xff)<<16)|((barr[o+3]&0xff)<<24)
def is_fn(v):
    if not v or (v&1)==0: return False
    f=fm.getFunctionContaining(A(v&~1)); return f and f.getEntryPoint().getOffset()==(v&~1)
# extent of pointer table containing 0x8043b90
a=0x8043b90
start=a
while start-4>=B and is_fn(u32(start-4)&0xffffffff): start-=4
end=a
while end<B+SZ-4 and is_fn(u32(end)&0xffffffff): end+=4
n=(end-start)//4
idx=(0x8043b90-start)//4
print("table @%#x .. %#x  entries=%d ; sim wrapper 0x0805893f is index %d"%(start,end,n,idx))
# dump table
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/fc_simtab_dump.txt","w")
out.write("table @%#x entries=%d (index -> handler):\n"%(start,n))
for i in range(n):
    v=u32(start+4*i)&0xffffffff; f=fm.getFunctionContaining(A(v&~1))
    out.write("  [%2d] %#010x %s\n"%(i, v&~1, f.getName() if f else '?'))
# who references the table base?
print("refs to table base %#x:"%start)
for r in refm.getReferencesTo(A(start)):
    cf=fm.getFunctionContaining(r.getFromAddress())
    print("   from %s in %s"%(r.getFromAddress(), cf.getName() if cf else '?'))
    if cf:
        res=dec.decompileFunction(cf,90,mon)
        if res and res.decompileCompleted():
            out.write("\n/* dispatcher %s @ %s */\n"%(cf.getName(),cf.getEntryPoint()))
            out.write(res.getDecompiledFunction().getC())
# RC-lost action enum: fn referencing "set rc lost action:%d" and the WP-quit string
for key in ["set rc lost action","[WP] RC lost, quit","get rc lost action","Get RC LOST ACT","Set RC LOST ACT"]:
    for d in listing.getDefinedData(True):
        if not isinstance(d.getDataType(),StringDataType): continue
        try: s=str(d.getValue())
        except: continue
        if s and key in s:
            for r in refm.getReferencesTo(d.getAddress()):
                cf=fm.getFunctionContaining(r.getFromAddress())
                if cf:
                    res=dec.decompileFunction(cf,90,mon)
                    if res and res.decompileCompleted():
                        out.write("\n/* RC-LOST [%s] %s @ %s */\n"%(key,cf.getName(),cf.getEntryPoint()))
                        out.write(res.getDecompiledFunction().getC())
            break
out.close(); print("-> fc_simtab_dump.txt")
