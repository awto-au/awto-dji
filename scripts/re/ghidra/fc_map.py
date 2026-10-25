# Ghidra post-script: map m0306 DUML receive/dispatch. Jython.
# Anchors (from capstone): CRC16 fn 0x0804f024, DUML frame validator 0x080304fc,
# response build 0x08028d30, send 0x0804f862.
from ghidra.program.model.symbol import RefType
fm = currentProgram.getFunctionManager()
refmgr = currentProgram.getReferenceManager()
listing = currentProgram.getListing()
af = currentProgram.getAddressFactory()
def A(x): return af.getDefaultAddressSpace().getAddress(x)
def fn_at(x):
    f = fm.getFunctionContaining(A(x))
    return f
def callers(x):
    out=[]
    for r in refmgr.getReferencesTo(A(x)):
        ft = r.getReferenceType()
        caller = fm.getFunctionContaining(r.getFromAddress())
        out.append((r.getFromAddress(), ft.getName(), caller.getEntryPoint() if caller else None, caller.getName() if caller else '?'))
    return out
print("=== function stats ===")
print("total functions: %d" % fm.getFunctionCount())
for nm,addr in [("crc16",0x0804f024),("validator",0x080304fc),("respbuild",0x08028d30),("send",0x0804f862)]:
    f=fn_at(addr)
    print("\n### %s %#x  fn=%s@%s" % (nm, addr, f.getName() if f else '?', f.getEntryPoint() if f else '?'))
    cs=callers(f.getEntryPoint().getOffset() if f else addr)
    print("  %d refs:" % len(cs))
    for frm,rt,cefn,cenm in cs[:30]:
        print("    %s  %-10s  in %s@%s" % (frm, rt, cenm, cefn))
