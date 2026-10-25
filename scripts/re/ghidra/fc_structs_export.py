from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
from ghidra.program.model.data import CategoryPath
dtm=currentProgram.getDataTypeManager(); fm=currentProgram.getFunctionManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
out=open(SC+"/fc_structs.h","w")
cat=dtm.getCategory(CategoryPath("/fc"))
if cat:
    for dt in cat.getDataTypes():
        out.write("// %s (size %d)\n"%(dt.getName(),dt.getLength()))
        try: out.write(str(dt.toString())+"\n\n")
        except: pass
        # manual field dump
        if hasattr(dt,'getComponents'):
            out.write("struct %s {  // 0x%x bytes\n"%(dt.getName(),dt.getLength()))
            for c in dt.getComponents():
                if c.getFieldName():
                    out.write("  +0x%02x %-10s %s; %s\n"%(c.getOffset(), c.getDataType().getName(), c.getFieldName(), ("// "+c.getComment()) if c.getComment() else ""))
            out.write("};\n\n")
out.close()
# verify member rendering in the agency handler
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
f=fm.getFunctionContaining(A(0x08055680))
res=dec.decompileFunction(f,60,mon)
if res and res.decompileCompleted():
    c=res.getDecompiledFunction().getC()
    print("agency handler references CtrlAgency fields:", "active" in c or "holder_id" in c or "granted" in c)
print("-> fc_structs.h")
