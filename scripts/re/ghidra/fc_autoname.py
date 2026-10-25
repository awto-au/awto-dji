# Jython batch 1: name peripheral ISRs + functions uniquely identified by a debug string.
# Conservative: only rename FUN_* functions; only when a string yields a clean identifier and
# exactly one FUN_ references it. Exports applied names to TSV.
import re
from ghidra.program.model.data import StringDataType
from ghidra.program.model.symbol import SourceType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing(); mem=currentProgram.getMemory()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
applied={}; rows=[]
def setname(f,nm):
    base=re.sub(r'[^A-Za-z0-9_]','_',nm)[:48].strip('_')
    if not base or not re.match(r'[A-Za-z_]',base): return
    k=base; i=2
    while k in applied and applied[k]!=f.getEntryPoint().getOffset(): k="%s_%d"%(base,i); i+=1
    try:
        f.setName(k,SourceType.USER_DEFINED); applied[k]=f.getEntryPoint().getOffset()
        rows.append((f.getEntryPoint().getOffset(),k))
    except: pass

# 1) ISRs from the vector table
irq={19:"CAN1_RX0",20:"CAN1_RX1",21:"CAN1_SCE",63:"CAN2_RX0",64:"CAN2_RX1",37:"USART1",38:"USART2",
     39:"USART3",52:"UART4",53:"UART5",71:"USART6",82:"UART7",83:"UART8",28:"TIM2",29:"TIM3",30:"TIM4",50:"TIM5",
     -3:"SysTick",-2:"PendSV",-14:"HardFault"}
for n,nm in irq.items():
    off=0x40+n*4 if n>=0 else (0x3c if n==-3 else 0x38 if n==-2 else 0x0c)
    try: v=mem.getInt(A(0x08020000+off))&0xffffffff
    except: continue
    f=fm.getFunctionContaining(A(v&~1))
    if f and f.getName().startswith("FUN_"): setname(f,"isr_%s"%nm)

# 2) string-identified functions
def ident_from(s):
    s=s.strip()
    m=re.match(r'call\s+([A-Za-z_]\w{3,})',s)                       # "call foo_bar..."
    if m: return m.group(1)
    if re.match(r'^[A-Za-z_]\w{4,}$',s): return s                   # bare identifier
    m=re.match(r'^\[([A-Za-z0-9_ /]{2,20})\]\s*([A-Za-z_]\w{3,})',s)# "[TAG] ident..."
    if m: return (m.group(1)+"_"+m.group(2)).replace(" ","_")
    m=re.match(r'^([A-Za-z_]\w{4,})[:\s].{0,6}(fail|failed|error|start|init|enter|exit|done|ok|timeout)',s,re.I)
    if m: return m.group(1)
    return None
cand={}
for d in listing.getDefinedData(True):
    if not isinstance(d.getDataType(),StringDataType): continue
    try: s=str(d.getValue())
    except: continue
    if not s or '%' in s[:3]: continue
    idt=ident_from(s)
    if not idt or len(idt)<5: continue
    funcs=set()
    for r in refm.getReferencesTo(d.getAddress()):
        f=fm.getFunctionContaining(r.getFromAddress())
        if f and f.getName().startswith("FUN_"): funcs.add(f)
    if len(funcs)==1:
        f=list(funcs)[0]
        cand.setdefault(f.getEntryPoint().getOffset(),(f,idt))
for ep,(f,idt) in cand.items():
    if f.getName().startswith("FUN_"): setname(f,"fc_%s"%idt)
out=open(SC+"/fc_autoname_batch1.tsv","w"); out.write("addr\tname\n")
for a,n in sorted(rows): out.write("%#010x\t%s\n"%(a,n))
out.close()
print("batch1 named: %d functions -> fc_autoname_batch1.tsv"%len(rows))
