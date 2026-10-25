import re
from ghidra.program.model.symbol import SourceType
mem=currentProgram.getMemory(); st=currentProgram.getSymbolTable()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
# ensure RAM blocks
for base,sz,nm in ((0x20000000,0x30000,"SRAM"),(0x2003f000,0x1000,"SRAM2"),(0x10000000,0x10000,"CCM"),(0x2001c000,0x4000,"SRAM_b")):
    if mem.getBlock(A(base)) is None:
        try:
            b=mem.createUninitializedBlock(nm,A(base),sz,False); b.setRead(True); b.setWrite(True)
        except: pass
n=0; seen=set()
for line in open(SC+"/m0306_params.tsv"):
    line=line.rstrip('\n')
    if not line or line.startswith("addr"): continue
    a,nm,ty,sz=line.split('\t')
    addr=int(a,16)
    label=re.sub(r'[^A-Za-z0-9_]','_',nm).strip('_')
    if addr in seen: continue
    if mem.getBlock(A(addr)) is None: continue
    try: st.createLabel(A(addr),label,SourceType.USER_DEFINED); n+=1; seen.add(addr)
    except: pass
print("param globals labeled: %d"%n)
