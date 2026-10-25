# Reset weak batch-1 names to default; keep only clearly-meaningful ones. Export keepers.
import re
from ghidra.program.model.symbol import SourceType
fm=currentProgram.getFunctionManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
JUNK=set("unknown start disable critical motor stick send this each frag task_a max_r camera camera_2 r a b".split())
def good(nm):
    if nm.startswith("isr_"): return True
    core=nm[3:] if nm.startswith("fc_") else nm
    if core.lower() in JUNK: return False
    if core.count('_')>=1 and len(core)>=7: return True   # compound, informative
    if len(core)>=10: return True
    return False
keep=[]; reset=0
for line in open(SC+"/fc_autoname_batch1.tsv"):
    line=line.strip()
    if not line or line.startswith("addr"): continue
    a,nm=line.split('\t')
    f=fm.getFunctionContaining(A(int(a,16)))
    if not f: continue
    if good(nm):
        keep.append((int(a,16),nm))
    else:
        try: f.setName("FUN_%08x"%int(a,16),SourceType.DEFAULT); reset+=1
        except: pass
out=open(SC+"/fc_batch1_keep.tsv","w"); out.write("addr\tname\n")
for a,n in sorted(keep): out.write("%#010x\t%s\n"%(a,n))
out.close()
print("kept %d, reset %d -> fc_batch1_keep.tsv"%(len(keep),reset))
