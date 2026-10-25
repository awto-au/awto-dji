# Jython: apply SVD MMIO labels + known function names to m0306, re-query the DUML validator,
# export functions to TSV. Reads regs.csv / names.tsv from the scratchpad.
import csv
from ghidra.program.model.address import AddressSet
from ghidra.program.model.mem import MemoryBlockType
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.listing import CodeUnit
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
mem=currentProgram.getMemory(); fm=currentProgram.getFunctionManager()
st=currentProgram.getSymbolTable(); refm=currentProgram.getReferenceManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)

# 1. MMIO blocks for the peripheral ranges we need, then register labels
ranges=[(0x40000000,0x40080000,"PERIPH_APB_AHB1"),(0x50000000,0x50061000,"AHB2_OTG"),(0xE0000000,0xE0100000,"CORE_SCB_NVIC")]
for base,end,nm in ranges:
    if mem.getBlock(A(base)) is None:
        b=mem.createUninitializedBlock(nm,A(base),end-base,False)
        b.setRead(True); b.setWrite(True); b.setVolatile(True)
labeled=0
for row in csv.reader(open(SC+"/regs.csv"),delimiter='\t'):
    if not row: continue
    addr=int(row[0],16); name=row[1].replace('.','_').replace('[','_').replace(']','').replace('%s','n')
    if mem.getBlock(A(addr)) is not None:
        try: st.createLabel(A(addr),name,SourceType.USER_DEFINED); labeled+=1
        except: pass
print("MMIO registers labeled: %d"%labeled)

# 2. known function names (force-create function if missing)
named=0
for row in csv.reader(open(SC+"/names.tsv"),delimiter='\t'):
    if not row or not row[0].startswith('0x'): continue
    a=A(int(row[0],16)); nm=row[1]
    f=fm.getFunctionContaining(a)
    if f is None:
        f=createFunction(a,nm)
    if f is not None:
        try: f.setName(nm,SourceType.USER_DEFINED); named+=1
        except: pass
print("functions named: %d"%named)

# 3. validator callers (now that it's a function)
val=A(0x080304fc); f=fm.getFunctionContaining(val)
print("validator fn: %s @ %s"%(f.getName() if f else '?', f.getEntryPoint() if f else '?'))
if f:
    rs=list(refm.getReferencesTo(f.getEntryPoint()))
    print("  refs to validator: %d"%len(rs))
    for r in rs[:20]:
        cf=fm.getFunctionContaining(r.getFromAddress())
        print("    %s %s in %s"%(r.getFromAddress(), r.getReferenceType().getName(), cf.getName() if cf else '?'))

# 4. export all functions -> TSV
out=open(SC+"/m0306_functions.tsv","w")
out.write("addr\tname\tsize\n")
cnt=0
fi=fm.getFunctions(True)
for f in fi:
    out.write("%s\t%s\t%d\n"%(f.getEntryPoint(), f.getName(), f.getBody().getNumAddresses())); cnt+=1
out.close(); print("exported %d functions to m0306_functions.tsv"%cnt)
