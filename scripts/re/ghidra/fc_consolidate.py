# Jython: apply all function names from the repo TSV; resolve+label key globals/structs;
# export functions + data TSVs. Creates SRAM/CCM blocks so RAM labels can be placed.
import csv
from ghidra.program.model.symbol import SourceType
from ghidra.program.model.data import StringDataType
fm=currentProgram.getFunctionManager(); st=currentProgram.getSymbolTable()
mem=currentProgram.getMemory(); sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
REPO="/home/user/awto-dji"
def r32(a):
    try: return mem.getInt(A(a))&0xffffffff
    except: return None
# 1) RAM blocks
for base,sz,nm in ((0x20000000,0x30000,"SRAM"),(0x10000000,0x10000,"CCM")):
    if mem.getBlock(A(base)) is None:
        b=mem.createUninitializedBlock(nm,A(base),sz,False); b.setRead(True); b.setWrite(True)
# 2) apply function names from repo TSV
applied=0
for row in csv.reader(open(REPO+"/docs/symbols/m0306.tsv"),delimiter='\t'):
    if not row or not row[0].startswith("0x"): continue
    try: a=A(int(row[0],16))
    except: continue
    nm=row[1]
    f=fm.getFunctionContaining(a)
    if f is None: f=createFunction(a,nm)
    if f is not None:
        try: f.setName(nm,SourceType.USER_DEFINED); applied+=1
        except: pass
print("function names applied: %d"%applied)
# 3) globals/structs: (name, addr) where addr may be direct RAM or resolved from a code literal
def lbl(addr,nm):
    try:
        if mem.getBlock(A(addr)) is None: return False
        st.createLabel(A(addr),nm,SourceType.USER_DEFINED); return True
    except: return False
data_rows=[]
# direct, known-meaning globals
agency=r32(0x080559b8)       # ptr to control-agency struct
mode_ptr=r32(0x0806506c)     # ptr to ctrl mode struct (byte -1 = active device, +0 = src flags)
arb_tbl=r32(0x08065074)      # ptr to arbitration table (stride 0xc)
rc_base=r32(0x080451e0)      # rc-lost cfg base (+0x1af = action)
nav_fs =r32(0x08065634)      # nav failsafe struct
known=[]
if mode_ptr: known += [(mode_ptr-1,"g_ctrl_active_device","gate byte; ==2 => API/nav is active controller"),
                       (mode_ptr,"g_ctrl_src_flags","per-source eligibility bits: bit1=src1, bit2=API/nav")]
if agency:  known += [(agency,"g_ctrl_agency","control-agency struct: [0]=active, [3]=holder id, +0x20=granted flag")]
if arb_tbl: known += [(arb_tbl,"g_ctrl_arb_table","arbitration table, stride 0xc {u8 code,.,pred_fn@+4}")]
if rc_base: known += [(rc_base+0x1af,"g_rc_lost_action","stored RC-lost action (1|2)")]
if nav_fs:  known += [(nav_fs,"g_nav_failsafe_state","nav/failsafe state struct (fc_nav_failsafe_exec)")]
known += [(0x080ef3d8,"g_ctrl_arb_rom","ROM: arbitration predicate table (code1/code2=API)"),
          (0x080ef734,"g_duml_crc16_table","DUML CRC16 lookup table"),
          (0x08043b90,"g_cmd_handler_tbl_sim","handler-ptr table containing fc_sim_cmd_wrapper")]
for addr,nm,note in known:
    if lbl(addr,nm): data_rows.append((addr,nm,note))
print("data labels placed: %d"%len(data_rows))
# 4) exports
outf=open(SC+"/m0306_functions_named.tsv","w"); outf.write("addr\tname\tsize\n")
cnt=0
for f in fm.getFunctions(True):
    if not f.getName().startswith("FUN_"):
        outf.write("%s\t%s\t%d\n"%(f.getEntryPoint(),f.getName(),f.getBody().getNumAddresses())); cnt+=1
outf.close()
outd=open(SC+"/m0306_data.tsv","w"); outd.write("addr\tname\tnote\n")
for addr,nm,note in sorted(data_rows): outd.write("%#010x\t%s\t%s\n"%(addr,nm,note))
outd.close()
print("exported %d named functions, %d data symbols"%(cnt,len(data_rows)))
for addr,nm,note in sorted(data_rows): print("  %#010x %s"%(addr,nm))
