// Ghidra headless POST-script for the m1400 (LPC1765, Cortex-M3) image, issue #84. Run via scripts/re/m1400_ghidra_names.py.
// Arg: <symbols.tsv> (docs/symbols/c1_m1400.tsv: addr kind name note source). Must run BEFORE DumpLPC17xx.java.
// func rows: create function if absent, rename; other rows: label + plate comment. Rows outside the image are counted as bad.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.nio.file.*;
import java.util.*;

public class M1400Names extends GhidraScript {
    @Override
    public void run() throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        List<String> lines = Files.readAllLines(Paths.get(getScriptArgs()[0]));
        int funcs = 0, labels = 0, bad = 0;
        for (int i = 1; i < lines.size(); i++) {
            String[] f = lines.get(i).split("\t", -1);
            if (f.length < 3 || f[0].startsWith("#") || f[0].isEmpty()) continue;
            try {
                long v = Long.decode(f[0]);
                if (!currentProgram.getMemory().contains(toAddr(v))) { bad++; continue; }
                Address a = toAddr(v);
                String kind = f[1], name = f[2], note = f.length > 3 ? f[3] : "";
                if (kind.equals("func")) {
                    Function fn = fm.getFunctionAt(a);
                    if (fn == null) { disassemble(a); fn = createFunction(a, name); }
                    if (fn == null) { bad++; println("NO FUNC @ " + a); continue; }
                    fn.setName(name, SourceType.USER_DEFINED);
                    funcs++;
                } else if (kind.equals("ram") || kind.equals("table") || kind.equals("label") || kind.equals("code")) {
                    createLabel(a, name, true, SourceType.USER_DEFINED);
                    labels++;
                } else continue;
                if (!note.isEmpty()) setPlateComment(a, note);
            } catch (Exception e) { bad++; println("BAD LINE " + (i + 1) + ": " + e); }
        }
        println("M1400Names: applied funcs=" + funcs + " labels=" + labels + " bad=" + bad);
    }
}
