# Jython: find function-pointer tables (handler registration) and their referencing dispatchers.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
mem=currentProgram.getMemory(); sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
B=0x08020000; E=B+mem.getSize() if False else 0x080f8000
def rd32(a):
    try: return mem.getInt(A(a)) & 0xffffffff
    except: return None
def is_fn(v):
    if not v or (v&1)==0: return False
    f=fm.getFunctionContaining(A(v&~1)); return f is not None and f.getEntryPoint().getOffset()==(v&~1)
# scan .text/.rodata for runs of >=6 consecutive function pointers (4-byte stride)
tables=[]; a=B
while a < E-4:
    v=rd32(a)
    if is_fn(v):
        start=a; cnt=0
        while a<E-4 and is_fn(rd32(a)): cnt+=1; a+=4
        if cnt>=6: tables.append((start,cnt))
    else: a+=4
print("function-pointer tables (>=6):")
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/fc_tables_dump.txt","w")
for start,cnt in tables:
    refs=[r.getFromAddress() for r in refm.getReferencesTo(A(start))]
    reffns=set()
    for fr in refs:
        cf=fm.getFunctionContaining(fr); 
        if cf: reffns.add(cf)
    print("  table @%#x x%d  referenced by: %s"%(start,cnt,[f.getName() for f in reffns][:4]))
    # dump first entries
    out.write("\n/* table @%#x x%d, refs=%s */\n"%(start,cnt,[f.getName() for f in reffns][:4]))
    for i in range(min(cnt,40)):
        v=rd32(start+4*i); f=fm.getFunctionContaining(A(v&~1))
        out.write("  [%2d] %#010x %s\n"%(i, v&~1, f.getName() if f else '?'))
    # decompile the referencing fn(s) (the dispatcher)
    for f in list(reffns)[:2]:
        res=dec.decompileFunction(f,60,mon)
        if res and res.decompileCompleted():
            out.write("\n/* ---- referencing dispatcher %s @ %s ---- */\n"%(f.getName(),f.getEntryPoint()))
            out.write(res.getDecompiledFunction().getC())
out.close(); print("tables+dispatchers -> fc_tables_dump.txt")
