// Ghidra headless post-script: full disassembly + decompilation dump of an
// imported 8051 program. Written for m1500 (FX2LP), issue awto-au/awto-dji#31.
// Run via scripts/re/m1500_fx2_disasm.py, not directly.
import ghidra.app.script.GhidraScript;
import ghidra.app.cmd.disassemble.DisassembleCommand;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSet;
import ghidra.program.model.listing.*;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.List;

public class Dump8051 extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args.length > 0 ? args[0] : "/tmp/m1500_dump.txt";

        // Reset vector + FX2's 4 extended-interrupt vector stub addresses (survey doc:
        // tiny 3-byte LJMP stubs found by the .iic record parser at these offsets).
        long[] seeds = {0x0000, 0x000b, 0x0033, 0x0043, 0x0053};
        AddressSet disassembled = new AddressSet();
        for (long s : seeds) {
            Address a = toAddr(s);
            DisassembleCommand cmd = new DisassembleCommand(a, null, true);
            cmd.applyTo(currentProgram, monitor);
            disassembled.add(cmd.getDisassembledAddressSet());
        }
        // Second pass: follow any CALL/JMP targets not yet reached (covers code only
        // reachable via a computed/indirect table that the first pass's flow-follow missed).
        for (Instruction instr : currentProgram.getListing().getInstructions(true)) {
            for (Reference r : instr.getReferencesFrom()) {
                Address to = r.getToAddress();
                if (to.getAddressSpace().getName().equals("CODE") && !disassembled.contains(to)
                        && currentProgram.getListing().getInstructionAt(to) == null) {
                    DisassembleCommand cmd2 = new DisassembleCommand(to, null, true);
                    cmd2.applyTo(currentProgram, monitor);
                    disassembled.add(cmd2.getDisassembledAddressSet());
                }
            }
        }
        // createFunction at the seeds and at any CALL target, so the function list below
        // is non-empty and roughly matches real subroutine boundaries.
        createFunction(toAddr(0), "entry");
        for (long s : seeds) createFunction(toAddr(s), "vec_" + Long.toHexString(s));
        for (Instruction instr : currentProgram.getListing().getInstructions(true)) {
            String m = instr.getMnemonicString();
            if (m.startsWith("LCALL") || m.startsWith("ACALL")) {
                for (Reference r : instr.getReferencesFrom()) {
                    createFunction(r.getToAddress(), null);
                }
            }
        }

        PrintWriter w = new PrintWriter(outPath);
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        List<Function> funcs = new ArrayList<>();
        for (Function f : fm.getFunctions(true)) funcs.add(f);

        w.println("=== FUNCTIONS (" + funcs.size() + ") ===");
        for (Function f : funcs) {
            w.println("FUNCTION " + f.getName() + " @ " + f.getEntryPoint() + " size=" + f.getBody().getNumAddresses());
        }

        w.println();
        w.println("=== FULL DISASSEMBLY ===");
        InstructionIterator ii = listing.getInstructions(true);
        while (ii.hasNext()) {
            Instruction instr = ii.next();
            StringBuilder refstr = new StringBuilder();
            for (Reference r : instr.getReferencesFrom()) {
                refstr.append(" ; ref->").append(r.getToAddress()).append("(").append(r.getReferenceType()).append(")");
            }
            w.println(instr.getAddress() + ": " + instr.toString() + refstr);
        }

        w.println();
        w.println("=== DECOMPILATION ===");
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        for (Function f : funcs) {
            DecompileResults res = di.decompileFunction(f, 60, monitor);
            w.println("---- " + f.getName() + " @ " + f.getEntryPoint() + " ----");
            if (res.decompileCompleted()) {
                w.println(res.getDecompiledFunction().getC());
            } else {
                w.println("DECOMPILE FAILED: " + res.getErrorMessage());
            }
        }

        w.println();
        w.println("=== MEMORY BLOCKS ===");
        for (MemoryBlock b : currentProgram.getMemory().getBlocks()) {
            w.println(b.getName() + ": " + b.getStart() + " - " + b.getEnd() + " init=" + b.isInitialized());
        }

        w.close();
        println("WROTE " + outPath);
    }
}
