from ghidra.program.model.symbol import RefType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager()
mem=currentProgram.getMemory(); sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
# DAT_0806506c holds a pointer; the gate reads *(ptr-1). Resolve the pointer value.
ptr=mem.getInt(A(0x0806506c))&0xffffffff
gate=ptr-1
print("gate pointer DAT_0806506c -> %#x ; gate byte @ %#x"%(ptr,gate))
for addr,lab in ((gate,"gate_byte"),(ptr,"mode_struct")):
    ws=[]
    for r in refm.getReferencesTo(A(addr)):
        f=fm.getFunctionContaining(r.getFromAddress())
        ws.append((r.getReferenceType().getName(), f.getName() if f else '?', str(r.getFromAddress())))
    print("%s %#x refs: %s"%(lab,addr,ws[:12]))
