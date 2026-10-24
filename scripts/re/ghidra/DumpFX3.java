// Ghidra headless post-script: full ARM disassembly dump of a Cypress FX3 "CY"
// boot image (m1601, ground USB bridge, issue awto-au/awto-dji#42). First FX3/ARM9
// target in this project - no native FX3 loader in Ghidra, so the image is NOT
// handed to -import directly. Instead:
//   1. The driver script (m1601_fx3_disasm.py) -import's a tiny dummy blob (any
//      non-empty file) at a scratch address, just so Ghidra has a Program to work
//      with and a language/compiler spec is selected.
//   2. This script removes that dummy block, then rebuilds the REAL memory map by
//      reading byte ranges straight off the original .bin (via the section table
//      the driver passes in <manifest>: VA<TAB>fileOffset<TAB>length per line,
//      reusing the same "CY" section-record parsing scripts/re/fx3_trace.py
//      already validated for this image).
//   3. Disassembles from <entryHex> plus a handful of addresses already identified
//      by the prior capstone-based static-analysis pass (docs/fx3-usb-modes.md),
//      then runs full auto-analysis (equivalent to -analyze) so Ghidra's own
//      function-start/constant-propagation passes sweep the whole image, not just
//      a hand-rolled flood fill.
//
// Args: <out.txt> <orig_bin_path> <manifest.tsv> <entryHex>
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import java.io.ByteArrayInputStream;
import java.io.PrintWriter;
import java.io.RandomAccessFile;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;

public class DumpFX3 extends GhidraScript {

    // Addresses already identified by the capstone-based pass in
    // docs/fx3-usb-modes.md, seeded here as named functions so the Ghidra artifact
    // cross-validates (or contradicts) that prior analysis, not just re-derives it.
    static final Map<Long, String> KNOWN = new LinkedHashMap<>();
    static {
        KNOWN.put(0x400068b8L, "RegisterUsbDescriptors");
        KNOWN.put(0x40007c70L, "DumlDispatch");
        KNOWN.put(0x4000e2dcL, "LoadPersistentConfig");
        KNOWN.put(0x4000e1c4L, "SetConfigField");
        KNOWN.put(0x4000e160L, "GetConfigField");
        KNOWN.put(0x40008cb8L, "ReadGpio41_P");
        KNOWN.put(0x40008cdcL, "ReadGpio42");
        KNOWN.put(0x40008de8L, "GetP");
        KNOWN.put(0x40008e08L, "GetM");
        KNOWN.put(0x4000e398L, "LoadK");
        KNOWN.put(0x4000e410L, "GetK");
        KNOWN.put(0x40007618L, "CmdSetConfig_08_01");
        KNOWN.put(0x400078e0L, "CmdGetConfig_08_02");
        KNOWN.put(0x40007588L, "CmdWriteField0_06_3a");
        KNOWN.put(0x40007858L, "CmdVersion_00_01");
        KNOWN.put(0x4000780cL, "CmdPing_00_0c");
        KNOWN.put(0x4000755cL, "CmdBuildInfo_00_ff");
        KNOWN.put(0x400076c4L, "CmdScheduleReset_00_0b");
        KNOWN.put(0x4000772cL, "DelayedResetAction");
    }

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        String origBinPath = args[1];
        String manifestPath = args[2];
        long entry = Long.parseLong(args[3].substring(2), 16);

        // 1. Note the dummy bootstrap block(s) the driver imported just to get a
        // Program (name varies with Ghidra version/loader - capture by identity,
        // not by guessing the name, then remove after the real blocks exist).
        List<MemoryBlock> dummyBlocks = new ArrayList<>(Arrays.asList(currentProgram.getMemory().getBlocks()));

        // 2. Rebuild the real "CY" section map straight from the original file.
        int nSections = 0;
        long totalBytes = 0;
        try (RandomAccessFile raf = new RandomAccessFile(origBinPath, "r")) {
            for (String line : Files.readAllLines(Paths.get(manifestPath))) {
                line = line.trim();
                if (line.isEmpty()) continue;
                String[] f = line.split("\t");
                long va = Long.parseLong(f[0].substring(2), 16);
                long fileOff = Long.parseLong(f[1].substring(2), 16);
                int len = Integer.parseInt(f[2]);
                byte[] buf = new byte[len];
                raf.seek(fileOff);
                raf.readFully(buf);
                Address at = toAddr(va);
                MemoryBlock blk = currentProgram.getMemory().createInitializedBlock(
                        "sec_" + String.format("%08x", va), at,
                        new ByteArrayInputStream(buf), len, monitor, false);
                blk.setRead(true);
                blk.setWrite(true);
                blk.setExecute(true);
                nSections++;
                totalBytes += len;
            }
        }
        println("rebuilt " + nSections + " section(s), " + totalBytes + " total bytes");

        // 2b. Now remove the dummy block(s) - safe once real content exists.
        for (MemoryBlock b : dummyBlocks) {
            currentProgram.getMemory().removeBlock(b, monitor);
        }

        // 3. Seed disassembly at the real entry point plus every known-good address
        // from the prior static-analysis pass, then let full auto-analysis run.
        disassemble(toAddr(entry));
        createFunction(toAddr(entry), "entry_" + Long.toHexString(entry));
        for (Map.Entry<Long, String> e : KNOWN.entrySet()) {
            Address a = toAddr(e.getKey());
            if (!currentProgram.getMemory().contains(a)) continue;
            disassemble(a);
            createFunction(a, e.getValue());
        }
        analyzeAll(currentProgram);

        // 4. Dump function list + full disassembly (no per-function decompile: FX3
        // images run to hundreds of functions, matching DumpARM.java's lighter touch
        // for larger images rather than m1500/m0400's full-decompile pass).
        PrintWriter w = new PrintWriter(outPath);
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);

        w.println("=== FUNCTIONS (" + funcs.size() + ") ===");
        for (Function f : funcs) {
            w.println(f.getEntryPoint() + "  " + f.getName() + "  size=" + f.getBody().getNumAddresses());
        }

        w.println("\n=== MEMORY BLOCKS ===");
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            w.println(b.getName() + ": " + b.getStart() + " - " + b.getEnd()
                    + " init=" + b.isInitialized() + " x=" + b.isExecute());
        }

        w.println("\n=== FULL DISASSEMBLY ===");
        InstructionIterator it = listing.getInstructions(true);
        long count = 0;
        while (it.hasNext()) {
            Instruction instr = it.next();
            StringBuilder refstr = new StringBuilder();
            for (Reference r : instr.getReferencesFrom()) {
                refstr.append(" ; ref->").append(r.getToAddress()).append("(").append(r.getReferenceType()).append(")");
            }
            w.println("CODE:" + instr.getAddress() + ": " + instr + refstr);
            count++;
        }
        w.println("TOTAL INSTRUCTIONS: " + count);

        // Coverage: fraction of each executable block Ghidra resolved as valid
        // instructions vs left as undefined bytes (data/pool/unreached code).
        w.println("\n=== PER-BLOCK INSTRUCTION COVERAGE ===");
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            if (!b.isExecute()) continue;
            long total = b.getSize();
            long instrBytes = 0;
            ghidra.program.model.address.AddressSet range =
                    new ghidra.program.model.address.AddressSet(b.getStart(), b.getEnd());
            InstructionIterator bi = listing.getInstructions(range, true);
            while (bi.hasNext()) instrBytes += bi.next().getLength();
            w.println(b.getName() + ": size=" + total + " instruction_bytes=" + instrBytes
                    + " (" + (100.0 * instrBytes / total) + "%)");
        }

        w.close();
        println("WROTE " + outPath);
    }
}
