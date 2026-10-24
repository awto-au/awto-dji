// Ghidra headless post-script: full RE pass on m0400 (gimbal MCU, STM32F4, RM0090), redo of
// the shallow awto-dji#41 pass. Combines DumpLPC17xx.java's SVD register labelling + full
// decompile with DumpARM.java's vector-table/cmd-table function creation, plus named-base
// xrefs widened to every peripheral base the task calls out (GPIOA/B/C, USART1/2/3, SPI1/2,
// CAN1, ADC1, TIM1/3/4, DMA1/2, I2C1).
//
// Args: <out.txt> <svd_labels.tsv> <cmd_table_base>:<n>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.SourceType;
import ghidra.program.model.scalar.Scalar;
import java.io.BufferedReader;
import java.io.FileReader;
import java.io.PrintWriter;
import java.util.*;

public class DumpM0400Full extends GhidraScript {

    static final Map<Long, String> BASES = new LinkedHashMap<>();
    static {
        BASES.put(0x40023800L, "RCC");
        BASES.put(0x40023C00L, "FLASH_IF");
        BASES.put(0x40020000L, "GPIOA");
        BASES.put(0x40020400L, "GPIOB");
        BASES.put(0x40020800L, "GPIOC");
        BASES.put(0x40011000L, "USART1");
        BASES.put(0x40004400L, "USART2");
        BASES.put(0x40004800L, "USART3");
        BASES.put(0x40013000L, "SPI1");
        BASES.put(0x40003800L, "SPI2");
        BASES.put(0x40026000L, "DMA1");
        BASES.put(0x40026400L, "DMA2");
        BASES.put(0x40012000L, "ADC1");
        BASES.put(0x40006400L, "CAN1");
        BASES.put(0x40005400L, "I2C1");
        BASES.put(0x40000000L, "TIM2");
        BASES.put(0x40000400L, "TIM3");
        BASES.put(0x40000800L, "TIM4");
        BASES.put(0x40010000L, "TIM1");
        BASES.put(0x40012C00L, "SDIO");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        String svdLabelsPath = args[1];

        int labelled = 0, skipped = 0;
        try (BufferedReader br = new BufferedReader(new FileReader(svdLabelsPath))) {
            String line = br.readLine(); // header
            while ((line = br.readLine()) != null) {
                String[] parts = line.split("\t");
                if (parts.length != 2) continue;
                long addr = Long.parseLong(parts[0].substring(2), 16);
                try {
                    Address a = toAddr(addr);
                    createLabel(a, parts[1], true, SourceType.IMPORTED);
                    labelled++;
                } catch (Exception e) {
                    skipped++;
                }
            }
        }
        println("SVD labels: " + labelled + " applied, " + skipped + " skipped");

        FunctionManager fm = currentProgram.getFunctionManager();

        // Vector-table functions (reset/IRQ handlers not reached by any call).
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

        // DUML cmd-table functions, named cmd_<set>_<id> for readability in the handler list.
        if (args.length > 2) {
            String[] p = args[2].split(":");
            Address tb = toAddr(Long.parseLong(p[0].substring(2), 16));
            int n = Integer.parseInt(p[1]);
            for (int i = 0; i < n; i++) {
                Address e = tb.add(8L * i);
                long h = Integer.toUnsignedLong(getInt(e));
                int id = getByte(e.add(4)) & 0xff;
                int set = getByte(e.add(5)) & 0xff;
                if ((h & 1) == 0 || !currentProgram.getMemory().contains(toAddr(h & ~1L))) {
                    println("cmd table stop at entry " + i + " (" + e + ")");
                    break;
                }
                Address ha = toAddr(h & ~1L);
                String nm = String.format("cmd_%02x_%02x", set, id);
                if (fm.getFunctionAt(ha) == null) {
                    disassemble(ha);
                    createFunction(ha, nm);
                } else {
                    fm.getFunctionAt(ha).setName(nm, SourceType.USER_DEFINED);
                }
                println("cmd table entry " + i + ": set=0x" + Integer.toHexString(set)
                        + " id=0x" + Integer.toHexString(id) + " handler=" + ha);
            }
        }

        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);

        PrintWriter w = new PrintWriter(outPath, "UTF-8");
        w.println("=== SVD LABELS: " + labelled + " applied, " + skipped + " skipped ===");
        w.println("\n=== FUNCTIONS (" + funcs.size() + ") ===");
        for (Function f : funcs) {
            w.println(f.getEntryPoint() + "  " + f.getName() + "  body=" + f.getBody().getNumAddresses() + " bytes");
        }

        Listing listing = currentProgram.getListing();
        InstructionIterator allInsns = listing.getInstructions(true);
        List<Instruction> insnList = new ArrayList<>();
        while (allInsns.hasNext()) insnList.add(allInsns.next());

        w.println("\n=== NAMED PERIPHERAL BASE XREFS ===");
        for (Map.Entry<Long, String> e : BASES.entrySet()) {
            long val = e.getKey();
            String name = e.getValue();
            List<String> hits = new ArrayList<>();
            for (Instruction instr : insnList) {
                boolean match = false;
                for (int i = 0; i < instr.getNumOperands(); i++) {
                    for (Object obj : instr.getOpObjects(i)) {
                        if (obj instanceof Scalar && ((Scalar) obj).getUnsignedValue() == val) match = true;
                    }
                }
                for (Reference r : instr.getReferencesFrom()) {
                    Data d = listing.getDataAt(r.getToAddress());
                    if (d != null && d.getLength() == 4) {
                        try {
                            if (d.getScalar(0).getUnsignedValue() == val) match = true;
                        } catch (Exception ex) { /* not scalar */ }
                    }
                }
                if (match) {
                    Function f = fm.getFunctionContaining(instr.getAddress());
                    hits.add(instr.getAddress() + " " + instr + (f != null ? "  [fn " + f.getEntryPoint() + " " + f.getName() + "]" : "  [no fn]"));
                }
            }
            w.println(name + " (0x" + Long.toHexString(val) + "): " + hits.size() + " hit(s)");
            for (String h : hits) w.println("    " + h);
        }

        w.println("\n=== FULL DISASSEMBLY ===");
        long count = 0;
        for (Instruction instr : insnList) {
            w.println("CODE:" + instr.getAddress() + ": " + instr);
            count++;
        }
        w.println("TOTAL INSTRUCTIONS: " + count);

        w.println("\n=== DECOMPILATION ===");
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
