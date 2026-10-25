# Jython: find the DUML RX dispatcher. Decompile callers (and their callers) of duml_crc16,
# flag those containing a switch; also list functions touching USART/CAN data registers.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"

def callers_of(ep):
    s=set()
    for r in refm.getReferencesTo(ep):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf and r.getReferenceType().isCall(): s.add(cf)
    return s

crc=fm.getFunctionContaining(A(0x0804f024))
lvl1=callers_of(crc.getEntryPoint())
lvl2=set()
for f in lvl1: lvl2|=callers_of(f.getEntryPoint())
cands=lvl1|lvl2
print("crc16 callers L1=%d, L2=%d, total cand=%d"%(len(lvl1),len(lvl2),len(cands)))

out=open(SC+"/fc_dispatch_dump.txt","w")
hits=[]
for f in cands:
    try: res=dec.decompileFunction(f,60,mon)
    except: continue
    if not res or not res.decompileCompleted(): continue
    c=res.getDecompiledFunction().getC()
    nsw=c.count("switch")
    if nsw>0:
        hits.append((nsw,len(c),f))
        out.write("\n/* ===== %s @ %s  switches=%d ===== */\n"%(f.getName(),f.getEntryPoint(),nsw))
        out.write(c)
hits.sort(reverse=True)
print("functions with switch(): %d"%len(hits))
for nsw,ln,f in hits[:12]: print("  %s @ %s  switches=%d  clen=%d"%(f.getName(),f.getEntryPoint(),nsw,ln))
out.close(); print("decompiled switch-functions -> fc_dispatch_dump.txt")

# which functions read USART/CAN data registers (RX entry)
import re
mmio={0x4001100c:"USART1_DR",0x4000440c:"USART2_DR",0x4000480c:"USART3_DR",0x40004c0c:"UART4_DR",0x4000500c:"UART5_DR",0x4001140c:"USART6_DR",0x40006400:"CAN1",0x40006800:"CAN2"}
print("functions touching serial/CAN:")
for addr,nm in mmio.items():
    fns=set()
    for r in refm.getReferencesTo(A(addr)):
        cf=fm.getFunctionContaining(r.getFromAddress())
        if cf: fns.add(cf.getName())
    if fns: print("  %s: %s"%(nm, ", ".join(sorted(fns)[:6])))
