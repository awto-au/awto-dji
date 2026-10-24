// Ghidra headless post-script: full disassembly dump of an imported ARM Cortex-M
// program, plus a targeted SPI1/SPI2/GPIO literal-xref report. Written for m0900
// (STM32F103, air radio MCU), issue awto-au/awto-dji#18.
// Run via scripts/re/m0900_ghidra_disasm.py, not directly.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.scalar.Scalar;
import java.io.PrintWriter;
import java.util.*;

public class DumpARM extends GhidraScript {
    // Named peripheral base constants worth flagging (RM0008 STM32F103 memory map).
    static final Map<Long, String> NAMED = new LinkedHashMap<>();
    static {
        NAMED.put(0x40013000L, "SPI1");
        NAMED.put(0x40003800L, "SPI2");
        NAMED.put(0x40010800L, "GPIOA");
        NAMED.put(0x40010c00L, "GPIOB");
        NAMED.put(0x40011000L, "GPIOC");
        NAMED.put(0x40021000L, "RCC");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args.length > 0 ? args[0] : "/tmp/m0900_ghidra_dump.txt";
        PrintWriter w = new PrintWriter(outPath);

        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();

        w.println("=== FUNCTIONS (" + fm.getFunctionCount() + ") ===");
        for (Function f : fm.getFunctions(true)) {
            w.println(String.format("%s  %s  body=%d bytes", f.getEntryPoint(), f.getName(),
                    f.getBody().getNumAddresses()));
        }

        w.println("\n=== FULL DISASSEMBLY ===");
        InstructionIterator it = listing.getInstructions(true);
        long count = 0;
        while (it.hasNext()) {
            Instruction instr = it.next();
            w.println("CODE:" + instr.getAddress() + ": " + instr);
            count++;
        }
        w.println("TOTAL INSTRUCTIONS: " + count);

        // Targeted report: every instruction whose operand resolves to one of the
        // NAMED peripheral base constants (immediate operand or a reference to a
        // defined data location holding that value), with the enclosing function.
        w.println("\n=== NAMED PERIPHERAL LITERAL XREFS ===");
        for (Map.Entry<Long, String> e : NAMED.entrySet()) {
            long val = e.getKey();
            String name = e.getValue();
            List<String> hits = new ArrayList<>();
            InstructionIterator it2 = listing.getInstructions(true);
            while (it2.hasNext()) {
                Instruction instr = it2.next();
                boolean match = false;
                for (int i = 0; i < instr.getNumOperands(); i++) {
                    for (Object obj : instr.getOpObjects(i)) {
                        if (obj instanceof Scalar) {
                            Scalar s = (Scalar) obj;
                            if (s.getUnsignedValue() == val) match = true;
                        }
                    }
                }
                // Also follow data refs: ldr from a literal pool holding this value.
                for (Reference r : instr.getReferencesFrom()) {
                    Address to = r.getToAddress();
                    Data d = listing.getDataAt(to);
                    if (d != null && d.getLength() == 4) {
                        try {
                            long v = d.getScalar(0).getUnsignedValue();
                            if (v == val) match = true;
                        } catch (Exception ex) { /* not scalar */ }
                    }
                }
                if (match) {
                    Function f = fm.getFunctionContaining(instr.getAddress());
                    hits.add(instr.getAddress() + " " + instr
                            + (f != null ? "  [fn " + f.getEntryPoint() + "]" : "  [no fn]"));
                }
            }
            w.println(name + " (" + String.format("0x%08x", val) + "): " + hits.size() + " hit(s)");
            for (String h : hits) w.println("    " + h);
        }

        w.close();
    }
}
