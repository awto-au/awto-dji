// Ghidra headless post-script: SVD-based peripheral register labelling + full disassembly +
// decompilation + named-literal-xref dump for an LPC17xx image. Written for m1400 (LPC1765,
// C1 ground/RC radio MCU), awto-dji#39. Same role as DumpARM.java (m0900/STM32), different
// peripheral map - shared ARM:LE:32:Cortex processor, so no new Ghidra setup needed.
//
// Args: <out.txt> <svd_labels.tsv>
// svd_labels.tsv: "address\tlabel" rows from scripts/re/svd_to_labels.py (flattened CMSIS-SVD,
// derivedFrom already resolved). Run via scripts/re/m1400_ghidra_disasm.py, not directly.
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

public class DumpLPC17xx extends GhidraScript {

    // Peripheral *bases* worth a named-literal-xref report (coarser than every register -
    // this answers "is this block touched at all", the register labels below answer "which
    // register"). Values from the same SVD as the label TSV; kept here too so the xref report
    // doesn't depend on the TSV being in a specific order.
    static final Map<Long, String> BASES = new LinkedHashMap<>();
    static {
        BASES.put(0x40000000L, "WDT");
        BASES.put(0x40004000L, "TIMER0");
        BASES.put(0x40008000L, "TIMER1");
        BASES.put(0x4000C000L, "UART0");
        BASES.put(0x40010000L, "UART1");
        BASES.put(0x40018000L, "PWM1");
        BASES.put(0x4001C000L, "I2C0");
        BASES.put(0x40020000L, "SPI");
        BASES.put(0x40024000L, "RTC");
        BASES.put(0x40028080L, "GPIOINT");
        BASES.put(0x4002C000L, "PINCONNECT");
        BASES.put(0x40030000L, "SSP1");
        BASES.put(0x40034000L, "ADC");
        BASES.put(0x40044000L, "CAN1");
        BASES.put(0x40048000L, "CAN2");
        BASES.put(0x4005C000L, "I2C1");
        BASES.put(0x40088000L, "SSP0");
        BASES.put(0x4008C000L, "DAC");
        BASES.put(0x40090000L, "TIMER2");
        BASES.put(0x40094000L, "TIMER3");
        BASES.put(0x40098000L, "UART2");
        BASES.put(0x4009C000L, "UART3");
        BASES.put(0x400FC000L, "SYSCON");
        BASES.put(0x50000000L, "EMAC");
        BASES.put(0x50004000L, "GPDMA");
        BASES.put(0x50008000L, "USB");
        BASES.put(0x2009C000L, "GPIO");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        String svdLabelsPath = args[1];

        // 1. SVD register labelling [spec]. Only labels addresses inside this program's
        // defined memory (peripherals are all MMIO, not in the flash image, so most of these
        // land outside - Ghidra needs the address *space* to exist, which the BinaryLoader
        // doesn't create for MMIO. createLabel still works on addresses outside defined memory
        // blocks in Ghidra's flat API as long as the address space itself (RAM/the default
        // space) covers it; LPC17xx peripherals are all < 4 GB in the same 32-bit space as
        // flash/SRAM, so this succeeds without a separate memory block.
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

        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);

        PrintWriter w = new PrintWriter(outPath, "UTF-8");
        w.println("=== SVD LABELS: " + labelled + " applied, " + skipped + " skipped (outside defined memory) ===");

        w.println("\n=== FUNCTIONS (" + funcs.size() + ") ===");
        for (Function f : funcs) {
            w.println(f.getEntryPoint() + "  " + f.getName() + "  body=" + f.getBody().getNumAddresses() + " bytes");
        }

        // 2. Named peripheral-base literal/data-ref xrefs, same method as DumpARM.java.
        w.println("\n=== NAMED PERIPHERAL BASE XREFS ===");
        InstructionIterator allInsns = listing.getInstructions(true);
        List<Instruction> insnList = new ArrayList<>();
        while (allInsns.hasNext()) insnList.add(allInsns.next());

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
                    hits.add(instr.getAddress() + " " + instr + (f != null ? "  [fn " + f.getEntryPoint() + "]" : "  [no fn]"));
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
