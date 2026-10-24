// Ghidra headless post-script: full disassembly + decompilation + call-count dump of
// the m0900 (STM32F103, Cortex-M3 Thumb-2) image. Issue awto-au/awto-dji#36.
// Run via scripts/re/m0900_can_ghidra.py, not directly. Args: <out.txt>.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import java.io.PrintWriter;
import java.util.*;

public class M0900Dump extends GhidraScript {
    @Override
    public void run() throws Exception {
        String outPath = getScriptArgs()[0];
        long flashBase = 0x08000000L;
        long flashEnd = currentProgram.getMemory().getMaxAddress().getOffset();

        // Vector table: word 0 is the initial SP, words 1..n are handler addresses (bit 0 = Thumb).
        for (int i = 1; i < 0x40; i++) {
            long v = currentProgram.getMemory().getInt(toAddr(flashBase + 4L * i)) & 0xFFFFFFFFL;
            long t = v & ~1L;
            if (t >= flashBase && t <= flashEnd) {
                Address a = toAddr(t);
                disassemble(a);
                try { createFunction(a, "vec_" + i); } catch (Exception e) { /* already a function */ }
            }
        }
        // Reset handler is vector 1; name it explicitly.
        long reset = currentProgram.getMemory().getInt(toAddr(flashBase + 4)) & ~1L & 0xFFFFFFFFL;
        try { createFunction(toAddr(reset), "Reset_Handler"); } catch (Exception e) { }

        // Ghidra's auto-analysis already followed flow; create functions at every BL/B.W call target.
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        InstructionIterator ii0 = listing.getInstructions(true);
        while (ii0.hasNext()) {
            Instruction ins = ii0.next();
            if (!ins.getFlowType().isCall()) continue;
            for (Reference r : ins.getReferencesFrom()) {
                if (r.getReferenceType().isCall()) {
                    try { createFunction(r.getToAddress(), null); } catch (Exception e) { }
                }
            }
        }

        // Call counts: distinct call sites per function entry.
        Map<Long, List<String>> callers = new TreeMap<>();
        InstructionIterator ii1 = listing.getInstructions(true);
        while (ii1.hasNext()) {
            Instruction ins = ii1.next();
            if (!ins.getFlowType().isCall()) continue;
            Function caller = fm.getFunctionContaining(ins.getAddress());
            for (Reference r : ins.getReferencesFrom()) {
                if (!r.getReferenceType().isCall()) continue;
                long tgt = r.getToAddress().getOffset();
                String cn = caller == null ? "?" : caller.getName() + "@" + caller.getEntryPoint();
                callers.computeIfAbsent(tgt, k -> new ArrayList<>()).add(ins.getAddress() + "<" + cn);
            }
        }

        PrintWriter w = new PrintWriter(outPath, "UTF-8");
        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);

        w.println("=== FUNCTIONS (" + funcs.size() + ") ===");
        for (Function f : funcs) {
            List<String> cs = callers.getOrDefault(f.getEntryPoint().getOffset(), Collections.emptyList());
            w.println("FUNCTION " + f.getName() + " @ " + f.getEntryPoint() + " size="
                    + f.getBody().getNumAddresses() + " callsites=" + cs.size());
        }

        w.println();
        w.println("=== CALLSITES ===");
        for (Map.Entry<Long, List<String>> e : callers.entrySet()) {
            w.println(Long.toHexString(e.getKey()) + " <- " + String.join(" ", e.getValue()));
        }

        w.println();
        w.println("=== FULL DISASSEMBLY ===");
        InstructionIterator ii2 = listing.getInstructions(true);
        while (ii2.hasNext()) {
            Instruction ins = ii2.next();
            Function f = fm.getFunctionContaining(ins.getAddress());
            StringBuilder refs = new StringBuilder();
            for (Reference r : ins.getReferencesFrom()) {
                refs.append(" ; ref->").append(r.getToAddress()).append("(").append(r.getReferenceType()).append(")");
            }
            w.println(ins.getAddress() + " [" + (f == null ? "-" : f.getName()) + "]: " + ins.toString() + refs);
        }

        w.println();
        w.println("=== DECOMPILATION ===");
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        int done = 0;
        for (Function f : funcs) {
            println("DECOMPILE " + (++done) + "/" + funcs.size() + " " + f.getName());
            DecompileResults res = di.decompileFunction(f, 30, monitor);
            w.println("---- " + f.getName() + " @ " + f.getEntryPoint() + " ----");
            if (res.decompileCompleted()) {
                w.println(res.getDecompiledFunction().getC());
            } else {
                w.println("DECOMPILE FAILED: " + res.getErrorMessage());
            }
        }
        w.close();
        println("WROTE " + outPath + " functions=" + funcs.size());
    }
}
