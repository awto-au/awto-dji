from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import StringDataType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
mem=currentProgram.getMemory(); listing=currentProgram.getListing()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
B=0x08020000; SZ=mem.getSize() if False else 0x8120000-B
out=open(SC+"/fc_simid_dump.txt","w")

def callers(ep):
    return [fm.getFunctionContaining(r.getFromAddress()) for r in refm.getReferencesTo(A(ep))
            if r.getReferenceType().isCall() and fm.getFunctionContaining(r.getFromAddress())]

def find_ptr_records(ep):
    # search whole image for the 4-byte LE value ep (and ep|1); dump +/- bytes to read set/id record
    recs=[]
    for want in (ep, ep|1):
        needle=bytearray()
        for k in range(4): needle.append((want>>(8*k))&0xff)
        data=mem
        # brute scan via getBytes in chunks
        buf=bytearray(mem.getSize() if False else 0)
    return recs

# 1) sim start wrapper + set/id
simh=0x080585ec
out.write("=== callers of fc_sim_start_handler %#x ===\n"%simh)
for f in callers(simh):
    out.write("  caller %s @ %s\n"%(f.getName(),f.getEntryPoint()))
    res=dec.decompileFunction(f,90,mon)
    if res and res.decompileCompleted(): out.write(res.getDecompiledFunction().getC())
# search memory for pointer to the wrapper(s) and to simh -> dispatch record
targets=set([simh, simh|1])
for f in callers(simh): targets.add(f.getEntryPoint().getOffset()); targets.add(f.getEntryPoint().getOffset()|1)
# read whole image bytes
raw=bytearray(SZ)
mem.getBytes(A(B),raw) if False else None
import jarray
barr=jarray.zeros(SZ,'b')
got=mem.getBytes(A(B),barr)
def u32(o): return (barr[o]&0xff)|((barr[o+1]&0xff)<<8)|((barr[o+2]&0xff)<<16)|((barr[o+3]&0xff)<<24)
out.write("\n=== dispatch records pointing at sim wrapper/handler ===\n")
for o in range(0,SZ-4,2):
    v=u32(o)&0xffffffff
    if v in targets:
        rec=[ (barr[o+k]&0xff) for k in range(-8,12)]
        out.write("  @%#x ptr=%#x  ctx bytes[-8..+12]: %s\n"%(B+o, v, ' '.join('%02x'%b for b in rec)))
out.close()
print("sim id trace -> fc_simid_dump.txt")
