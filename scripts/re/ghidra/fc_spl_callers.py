# Jython: enumerate callers of the identified SPL functions and decompile the config-bearing
# ones, so the full peripheral pin/baud/CS map falls out of the call arguments. Also trace
# usart_open callers (to reach the per-port descriptor: which USART = GPS/RC/OSD + baud).
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor
fm = currentProgram.getFunctionManager(); refm = currentProgram.getReferenceManager()
sp = currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
SC = "/tmp/claude-0/-home-user-awto-dji/31c9c192-9a51-52a8-a402-e3e1c80291da/scratchpad"
dec = DecompInterface(); dec.openProgram(currentProgram); mon = ConsoleTaskMonitor()
out = open(SC + "/fc_spl_callers_dump.txt", "w")

SPL = {
    0x0806396c: "GPIO_Init", 0x08063a54: "GPIO_PinAFConfig",
    0x0803b5d8: "USART_Init", 0x0803ae02: "CAN_Init",
    0x0806d716: "RCC_AHB1ClockCmd", 0x0806d752: "RCC_APB1ClockCmd", 0x0806d766: "RCC_APB2ClockCmd",
    0x080343cc: "usart_open",
}

# Phase 1: caller census
out.write("==== caller census ====\n")
callers_of = {}
for a, nm in sorted(SPL.items()):
    cs = set()
    for r in refm.getReferencesTo(A(a)):
        if r.getReferenceType().isCall():
            f = fm.getFunctionContaining(r.getFromAddress())
            if f: cs.add(f.getEntryPoint().getOffset())
    callers_of[a] = cs
    out.write("  %-18s @%08x : %d callers\n" % (nm, a, len(cs)))

# Phase 2: decompile config-bearing callers (USART_Init, CAN_Init, usart_open, GPIO_PinAFConfig)
# and the callers of usart_open (descriptor trace). Dedup, cap, skip huge.
want = set()
for a in (0x0803b5d8, 0x0803ae02, 0x080343cc, 0x08063a54):
    want |= callers_of.get(a, set())
# plus callers-of-usart_open's callers -> who fills the descriptor
uo_callers = callers_of.get(0x080343cc, set())
for off in list(uo_callers):
    f = fm.getFunctionContaining(A(off))
    for r in refm.getReferencesTo(f.getEntryPoint()):
        if r.getReferenceType().isCall():
            cf = fm.getFunctionContaining(r.getFromAddress())
            if cf: want.add(cf.getEntryPoint().getOffset())

out.write("\n==== %d config-bearing callers decompiled ====\n" % len(want))
done = 0
for off in sorted(want):
    f = fm.getFunctionContaining(A(off))
    if not f: continue
    ln = f.getBody().getNumAddresses()
    if ln > 1800 or done > 60:
        out.write("\n/* skip %s @ %s (%d B) */\n" % (f.getName(), f.getEntryPoint(), ln)); continue
    res = dec.decompileFunction(f, 60, mon)
    if res and res.decompileCompleted():
        out.write("\n/* ===== %s @ %s (%d B) ===== */\n" % (f.getName(), f.getEntryPoint(), ln))
        out.write(res.getDecompiledFunction().getC())
        done += 1
out.close(); print("-> fc_spl_callers_dump.txt (%d decompiled)" % done)
