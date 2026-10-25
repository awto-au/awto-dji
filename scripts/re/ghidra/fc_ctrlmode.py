# Jython: decompile the control-authority handlers and the fns referencing the REQ/AGENCY/REFUSE
# strings; dump C so we can see what is checked before granting control.
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import StringDataType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
targets=set()
# explicit entry points
for a in (0x08055cb8,0x08055b9c,0x08055b2e):
    f=fm.getFunctionContaining(A(a))
    if f: targets.add(f)
# functions referencing the key authority strings
keys=["REV REQ CMD AND SET AGENCY","SEND ACK REQ CMD REFUSE","api_ctrl_mode_status_request_handler","SEND ACK REQ CMD STATUS","REV REQ CMD STATUS"]
for d in listing.getDefinedData(True):
    if not isinstance(d.getDataType(),StringDataType): continue
    try: s=str(d.getValue())
    except: continue
    if s and any(k in s for k in keys):
        for r in refm.getReferencesTo(d.getAddress()):
            f=fm.getFunctionContaining(r.getFromAddress())
            if f: targets.add(f)
out=open(SC+"/fc_ctrlmode_dump.txt","w")
print("decompiling %d functions:"%len(targets))
for f in sorted(targets,key=lambda x:x.getEntryPoint().getOffset()):
    res=dec.decompileFunction(f,90,mon)
    if not res or not res.decompileCompleted(): continue
    c=res.getDecompiledFunction().getC()
    out.write("\n/* ===== %s @ %s  (callers=%d) ===== */\n"%(f.getName(),f.getEntryPoint(),
        len([r for r in refm.getReferencesTo(f.getEntryPoint()) if r.getReferenceType().isCall()])))
    out.write(c)
    print("  %s @ %s len=%d"%(f.getName(),f.getEntryPoint(),len(c)))
out.close(); print("-> fc_ctrlmode_dump.txt")
