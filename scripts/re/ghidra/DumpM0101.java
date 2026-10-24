// Ghidra headless post-script: function list + targeted string-xref report for the
// m0101 ThreadX camera-loader module, issue awto-au/awto-dji#37. ARMv7-A (Cortex-A9,
// per the "ThreadX Cortex-A9/IAR" copyright string), no symbols, base address unknown
// so loaded at file offset 0 - absolute addresses below are FILE OFFSETS, not a real
// runtime base. Run via scripts/re/m0101_ghidra_disasm.py, not directly.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.PrintWriter;
import java.util.*;

public class DumpM0101 extends GhidraScript {
    // Strings worth finding the call sites of - picks out the firmware-update /
    // NAND-partition / UEG-handshake entry points from the `strings` triage.
    static final String[] TARGETS = {
        "AmbaFwUpdaterTask", "DjiFwUpdaterReboot", "DjiFwUpdaterLedTask",
        "DjiUegFwStageSet", "DjiUegFwStageGet", "DjiUecFirmwareDetect",
        "DjiUecSucceedHandle", "DjiUecFailHandle",
        "C:/P3X_FW_V??.??.????.bin", "C:/FC300XFw.bin", "FC300X",
        "AmbaNAND_SetPtb", "AmbaNAND_SetMeta", "AmbaNFTL_Init",
        "RootTask", "AmbaPrintTask", "Bootstrap", "DSP uCode",
    };

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args.length > 0 ? args[0] : "/tmp/m0101_ghidra_dump.txt";
        PrintWriter w = new PrintWriter(outPath);

        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();

        w.println("=== FUNCTIONS (" + fm.getFunctionCount() + ") ===");
        for (Function f : fm.getFunctions(true)) {
            w.println(String.format("%s  %s  body=%d bytes", f.getEntryPoint(), f.getName(),
                    f.getBody().getNumAddresses()));
        }

        long insnCount = 0;
        InstructionIterator ii = listing.getInstructions(true);
        while (ii.hasNext()) { ii.next(); insnCount++; }
        w.println("\nTOTAL INSTRUCTIONS: " + insnCount);

        w.println("\n=== TARGET STRING XREFS ===");
        for (String target : TARGETS) {
            w.println("\n-- \"" + target + "\" --");
            DataIterator di = listing.getDefinedData(true);
            boolean found = false;
            while (di.hasNext()) {
                Data d = di.next();
                Object val = d.getValue();
                if (val instanceof String && ((String) val).startsWith(target)) {
                    found = true;
                    Address strAddr = d.getAddress();
                    w.println("  string @ " + strAddr + " = " + val);
                    ReferenceIterator refs = currentProgram.getReferenceManager().getReferencesTo(strAddr);
                    while (refs.hasNext()) {
                        Reference r = refs.next();
                        Address from = r.getFromAddress();
                        Function fn = fm.getFunctionContaining(from);
                        String fname = fn != null ? fn.getName() + "@" + fn.getEntryPoint() : "?";
                        w.println("    xref from " + from + "  in " + fname);
                    }
                }
            }
            if (!found) w.println("  (string not found as defined data - may need manual string search)");
        }
        w.close();
    }
}
