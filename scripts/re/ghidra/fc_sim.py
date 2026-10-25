from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import StringDataType
from ghidra.program.model.symbol import SourceType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
listing=currentProgram.getListing()
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
keys=["try to start simulator","Agree to run","SimulatorStop","refuse to start simulator","the simulator is running","[SIM]try to start"]
targets={}
for d in listing.getDefinedData(True):
    if not isinstance(d.getDataType(),StringDataType): continue
    try: s=str(d.getValue())
    except: continue
    if s and any(k in s for k in keys):
        for r in refm.getReferencesTo(d.getAddress()):
            f=fm.getFunctionContaining(r.getFromAddress())
            if f: targets[f.getEntryPoint().getOffset()]=f
out=open(SC+"/fc_sim_dump.txt","w")
print("sim handler fns: %d"%len(targets))
for ep,f in sorted(targets.items()):
    nm=f.getName()
    if nm.startswith("FUN_"):
        try: f.setName("fc_sim_handler_%08x"%ep,SourceType.USER_DEFINED)
        except: pass
    res=dec.decompileFunction(f,90,mon)
    cal=len([r for r in refm.getReferencesTo(f.getEntryPoint()) if r.getReferenceType().isCall()])
    print("  %s @ %#x callers=%d"%(f.getName(),ep,cal))
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %#x callers=%d ===== */\n"%(f.getName(),ep,cal))
        out.write(res.getDecompiledFunction().getC())
out.close(); print("-> fc_sim_dump.txt")
