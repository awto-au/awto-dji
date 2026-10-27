# Decompile the two (+two) A9 MAC functions in the m0100 sys partition (base 0x0E600000).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm=currentProgram.getFunctionManager()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC="/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec=DecompInterface(); dec.openProgram(currentProgram); mon=ConsoleTaskMonitor()
out=open(SC+"/m0100_mac_dump.txt","w")
targets=[(0x0e85f370,"DjiMsgAuthorizedMac"),(0x0e871ae0,"DjiEncryptCheckA9Mac"),
         (0x0e8731cc,"DjiEncryptCheckSN"),(0x0e8dd194+0x90,"MCCTRL_AuthorizedMacUpdate?")]
for addr,name in targets:
    f=fm.getFunctionContaining(A(addr))
    if f is None:
        # force-create a function at the address
        from ghidra.app.cmd.function import CreateFunctionCmd
        CreateFunctionCmd(A(addr)).applyTo(currentProgram)
        f=fm.getFunctionContaining(A(addr))
    if f is None:
        out.write("\n/* %s @ %#x: no function */\n"%(name,addr)); continue
    res=dec.decompileFunction(f,120,mon)
    out.write("\n/* ===== %s @ %s (want %#x, %d B) ===== */\n"%(name,f.getEntryPoint(),addr,f.getBody().getNumAddresses()))
    if res and res.decompileCompleted():
        out.write(res.getDecompiledFunction().getC())
    else:
        out.write("/* decompile failed */\n")
out.close(); print("-> m0100_mac_dump.txt")
