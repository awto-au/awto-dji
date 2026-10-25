from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import StringDataType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager(); listing=currentProgram.getListing()
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out=open(SC+"/fc_wplost_dump.txt","w")
for key in ["[WP] RC lost, quit","go_home_when_running_gs","action_on_rc_lost","protect_action"]:
    done=False
    for d in listing.getDefinedData(True):
        if done: break
        if not isinstance(d.getDataType(),StringDataType): continue
        try: s=str(d.getValue())
        except: continue
        if s and key in s:
            for r in refm.getReferencesTo(d.getAddress()):
                cf=fm.getFunctionContaining(r.getFromAddress())
                if cf:
                    res=dec.decompileFunction(cf,90,mon)
                    if res and res.decompileCompleted():
                        out.write("\n/* [%s] %s @ %s */\n"%(key,cf.getName(),cf.getEntryPoint()))
                        out.write(res.getDecompiledFunction().getC()); done=True; break
out.close(); print("-> fc_wplost_dump.txt")
