from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import PointerDataType, CategoryPath
from ghidra.program.model.listing import ParameterImpl, Function
from ghidra.program.model.symbol import SourceType
dtm=currentProgram.getDataTypeManager(); fm=currentProgram.getFunctionManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
def dt(name): return dtm.getDataType(CategoryPath("/fc"),name)
agency=dt("CtrlAgency"); duml=dt("DumlFrame")
# 1) type the agency pointer literal 0x080559b8 as CtrlAgency*
pa=PointerDataType(agency)
try:
    clearListing(A(0x080559b8),A(0x080559bb)); createData(A(0x080559b8),pa); print("typed 0x080559b8 as CtrlAgency*")
except Exception as e: print("agency ptr fail:",e)
# 2) set arg0 = DumlFrame* on raw-frame handlers via signature replace
pd=PointerDataType(duml)
for a,nm in ((0x08044d2a,"fc_real_name_info_handler"),(0x08044dfa,"fc_set_rc_lost_action")):
    f=fm.getFunctionContaining(A(a))
    if not f: continue
    try:
        params=[ParameterImpl("pkt",pd,currentProgram)]
        # keep remaining params as-is
        for i in range(1,f.getParameterCount()):
            p=f.getParameter(i); params.append(ParameterImpl(p.getName(),p.getDataType(),currentProgram))
        f.replaceParameters(params, Function.FunctionUpdateType.DYNAMIC_STORAGE_FORMAL_PARAMS, True, SourceType.USER_DEFINED)
        print("retyped arg0 of %s -> DumlFrame*"%f.getName())
    except Exception as e: print("retype %s fail: %s"%(nm,e))
# 3) verify propagation: decompile agency handler + a config toucher
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
for a,lbl in ((0x08055680,"agency handler"),(0x08044dfa,"set_rc_lost_action")):
    f=fm.getFunctionContaining(A(a)); res=dec.decompileFunction(f,60,mon)
    if res and res.decompileCompleted():
        c=res.getDecompiledFunction().getC()
        hits=[t for t in ("->active","->holder_id","->granted","cmd_set","cmd_id","receiver","g_config","protect_action","fail_safe") if t in c]
        print("%s renders: %s"%(lbl, hits))
