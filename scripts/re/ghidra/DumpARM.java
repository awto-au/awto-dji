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
        // Optional arg 1: TSV of "0xADDR<TAB>NAME" peripheral bases, replacing the F1 default.
        if (args.length > 1) {
            NAMED.clear();
            for (String line : java.nio.file.Files.readAllLines(java.nio.file.Paths.get(args[1]))) {
                String[] f = line.trim().split("\\s+");
                if (f.length == 2 && f[0].startsWith("0x")) NAMED.put(Long.parseLong(f[0].substring(2), 16), f[1]);
            }
        }
        FunctionManager fm = currentProgram.getFunctionManager();
        // Optional arg 2 "vectors": make a function at every Thumb handler in the vector
        // table. Raw-binary import has no entry points, so ISRs never reached by a call
        // (e.g. USART1 handler at 0x08011725) otherwise have no function and no body.
        if (args.length > 2 && args[2].equals("vectors")) {
            Address imgBase = currentProgram.getMinAddress();
            int made = 0;
            for (int i = 1; i < 98; i++) {
                long v = Integer.toUnsignedLong(getInt(imgBase.add(4L * i)));
                if ((v & 1) == 0) continue;
                Address h = toAddr(v & ~1L);
                if (currentProgram.getMemory().contains(h) && fm.getFunctionAt(h) == null) {
                    disassemble(h);
                    if (createFunction(h, "vec_" + i) != null) made++;
                }
            }
            println("vector-table functions created: " + made);
        }
        // Optional arg 3 "0xBASE:N": N {handler, id} pairs (8-byte stride), e.g. the DUML
        // command table. Stops at the first entry that is not a Thumb address in the image.
        if (args.length > 3) {
            String[] p = args[3].split(":");
            Address tb = toAddr(Long.parseLong(p[0].substring(2), 16));
            int n = Integer.parseInt(p[1]);
            for (int i = 0; i < n; i++) {
                Address e = tb.add(8L * i);
                long h = Integer.toUnsignedLong(getInt(e));
                long id = Integer.toUnsignedLong(getInt(e.add(4)));
                if ((h & 1) == 0 || !currentProgram.getMemory().contains(toAddr(h & ~1L))) {
                    println("table stop at entry " + i + " (" + e + ")");
                    break;
                }
                Address ha = toAddr(h & ~1L);
                if (fm.getFunctionAt(ha) == null) {
                    disassemble(ha);
                    createFunction(ha, "cmd_" + Long.toHexString(id));
                }
                println("table entry " + i + ": id=0x" + Long.toHexString(id) + " handler=" + ha);
            }
        }

        PrintWriter w = new PrintWriter(outPath);

        Listing listing = currentProgram.getListing();

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
