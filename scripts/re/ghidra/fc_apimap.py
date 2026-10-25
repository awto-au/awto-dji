# Jython: name FC command handlers from their debug strings; export TSV of (addr,name,string).
import re
from ghidra.program.model.data import StringDataType
from ghidra.program.model.symbol import SourceType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing(); mem=currentProgram.getMemory()
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
# extract a handler identifier from a log string
def ident(s):
    m=re.search(r'call\s+(api_[a-z0-9_]+?)(?:_handler|_handle)?\b',s)
    if m: return m.group(1)
    m=re.search(r'\b(api_[a-z0-9_]+?_handler|api_[a-z0-9_]+?_handle)\b',s)
    if m: return m.group(1)
    m=re.search(r'\b(reg_[a-z0-9_]+|sdk_[a-z0-9_]+)\b',s)
    if m: return m.group(1)
    return None
# iterate defined ASCII strings
di=listing.getDefinedData(True)
named={}; rows=[]
cnt=0
for d in di:
    dt=d.getDataType()
    if not isinstance(dt,StringDataType): continue
    try: s=d.getValue()
    except: continue
    if not s: continue
    nm=ident(str(s))
    if not nm: continue
    # referencing function = handler
    for r in refm.getReferencesTo(d.getAddress()):
        f=fm.getFunctionContaining(r.getFromAddress())
        if f and f.getName().startswith("FUN_"):
            base=nm; k=base; i=2
            while k in named and named[k]!=f.getEntryPoint().getOffset(): k="%s_%d"%(base,i); i+=1
            try:
                f.setName("fc_"+k,SourceType.USER_DEFINED); named[k]=f.getEntryPoint().getOffset()
                rows.append((f.getEntryPoint().getOffset(),"fc_"+k,str(s)[:70]))
            except: pass
# dedupe rows by addr
seen=set(); urows=[]
for a,n,s in sorted(rows):
    if a in seen: continue
    seen.add(a); urows.append((a,n,s))
out=open(SC+"/fc_apimap.tsv","w")
out.write("addr\tname\tlog_string\n")
for a,n,s in urows: out.write("%#010x\t%s\t%s\n"%(a,n,s))
out.close()
print("named %d handler functions -> fc_apimap.tsv"%len(urows))
for a,n,s in urows[:60]: print("  %#x %s"%(a,n))
