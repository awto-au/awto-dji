// Ghidra headless post-script: function list + full disassembly + string-xref
// report for a stripped ARM Linux userland ELF (cam_server et al, m0100 Ambarella
// A9 Linux). Written for issue awto-au/awto-dji#37 (m0100 Linux functional RE).
// Run via scripts/re/cam_server_ghidra_disasm.py, not directly.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.data.DataType;
import java.io.PrintWriter;
import java.util.*;

public class DumpELF extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args.length > 0 ? args[0] : "/tmp/cam_server_ghidra_dump.txt";
        // Optional comma-separated substrings to filter the string-xref section.
        String filter = args.length > 1 ? args[1] : "";
        PrintWriter w = new PrintWriter(outPath);

        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();

        w.println("=== FUNCTIONS (" + fm.getFunctionCount() + ") ===");
        for (Function f : fm.getFunctions(true)) {
            w.println(String.format("%s  %s  body=%d bytes  thunk=%b", f.getEntryPoint(),
                    f.getName(), f.getBody().getNumAddresses(), f.isThunk()));
        }

        w.println("\n=== STRING XREFS (filtered: " + filter + ") ===");
        String[] needles = filter.isEmpty() ? new String[0] : filter.split(",");
        DataIterator dit = listing.getDefinedData(true);
        while (dit.hasNext()) {
            Data d = dit.next();
            DataType dt = d.getDataType();
            if (dt == null || !dt.getName().toLowerCase().contains("string")) continue;
            String val;
            try { val = d.getDefaultValueRepresentation(); } catch (Exception ex) { continue; }
            boolean hit = needles.length == 0;
            for (String n : needles) {
                if (!n.isEmpty() && val.toLowerCase().contains(n.toLowerCase())) { hit = true; break; }
            }
            if (!hit) continue;
            w.println("STR " + d.getAddress() + ": " + val);
            for (Reference r : getReferencesTo(d.getAddress())) {
                Address from = r.getFromAddress();
                Function f = fm.getFunctionContaining(from);
                w.println("    xref " + from + (f != null ? "  [fn " + f.getEntryPoint() + " " + f.getName() + "]" : "  [no fn]"));
            }
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

        w.close();
    }
}
