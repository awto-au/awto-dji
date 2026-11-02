// Ghidra headless POST-script for the m0900 (STM32F103, Cortex-M3 Thumb-2) image, issues #36, #83.
// Run via scripts/re/m0900_ghidra_names.py, not directly.
// Args: <out.txt> <symbols.tsv> <structs.h>
//  1. seeds functions at vector-table handlers and every BL/B.W target;
//  2. applies docs/symbols/m0900_V01.11.0020.tsv (addr kind name note source; kinds func|ram|table|code|region|label)
//     with a plate comment; ram rows may carry `type=<spec>` in the note (struct name, u8/u16/u32/ptr, spec[N]);
//  3. parses the C block between `@ghidra-begin` / `@ghidra-end` markers of the structs header into the program DTM;
//  4. dumps functions (call counts), call sites, disassembly, strings, decompilation to <out.txt>.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.util.cparser.C.CParser;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.PrintWriter;
import java.nio.file.*;
import java.util.*;
import java.util.regex.*;

public class M0900Dump extends GhidraScript {
    DataTypeManager dtm;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        long flashBase = 0x08008000L;
        long flashEnd = flashBase + currentProgram.getMemory().getBlock(toAddr(flashBase)).getSize() - 1;
        dtm = currentProgram.getDataTypeManager();

        // Vector table: word 0 = initial SP, words 1..n = handlers (bit 0 = Thumb).
        for (int i = 1; i < 0x40; i++) {
            long v = currentProgram.getMemory().getInt(toAddr(flashBase + 4L * i)) & 0xFFFFFFFFL;
            long t = v & ~1L;
            if (t >= flashBase && t <= flashEnd) {
                Address a = toAddr(t);
                disassemble(a);
                try { createFunction(a, i == 1 ? "Reset_Handler" : "vec_" + i); } catch (Exception e) { }
            }
        }
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

        if (args.length > 2) loadStructs(args[2]);
        if (args.length > 1) applySymbols(args[1]);

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
        w.println("=== STRINGS (with referencing functions) ===");
        DataIterator di0 = listing.getDefinedData(true);
        while (di0.hasNext()) {
            Data d = di0.next();
            if (!(d.getValue() instanceof String)) continue;
            StringBuilder sb = new StringBuilder();
            for (Reference r : getReferencesTo(d.getAddress())) {
                Function f = fm.getFunctionContaining(r.getFromAddress());
                sb.append(' ').append(r.getFromAddress()).append(f == null ? "" : "<" + f.getName());
            }
            w.println(d.getAddress() + "\t" + d.getValue().toString().replace("\n", "\\n") + "\t" + sb);
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

    void loadStructs(String path) throws Exception {
        String text = new String(Files.readAllBytes(Paths.get(path)), "UTF-8");
        int a = text.indexOf("@ghidra-begin"), b = text.indexOf("@ghidra-end");
        if (a < 0 || b < 0) { println("M0900Dump: no @ghidra block in " + path); return; }
        String c = text.substring(text.indexOf('\n', a) + 1, b);
        c = c.substring(0, c.lastIndexOf("\n") + 1);
        CParser parser = new CParser(dtm);
        parser.parse(c);
        for (DataType t : parser.getComposites().values()) dtm.resolve(t, DataTypeConflictHandler.REPLACE_HANDLER);
        int n = 0;
        Iterator<Structure> it = dtm.getAllStructures();
        while (it.hasNext()) { it.next(); n++; }
        println("M0900Dump: structs in DTM=" + n + " parsed=" + parser.getComposites().size());
    }

    DataType typeFor(String spec) {
        Matcher m = Pattern.compile("^(.*)\\[(\\d+)\\]$").matcher(spec);
        if (m.matches()) {
            DataType e = typeFor(m.group(1));
            if (e == null) return null;
            int n = Integer.parseInt(m.group(2));
            return new ArrayDataType(e, n, e.getLength());
        }
        switch (spec) {
            case "u8": return ByteDataType.dataType;
            case "u16": return UnsignedShortDataType.dataType;
            case "u32": return UnsignedIntegerDataType.dataType;
            case "f32": return FloatDataType.dataType;
            case "ptr": return PointerDataType.dataType;
        }
        Iterator<Structure> it = dtm.getAllStructures();
        while (it.hasNext()) { Structure s = it.next(); if (s.getName().equals(spec)) return s; }
        return null;
    }

    void applySymbols(String path) throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        List<String> lines = Files.readAllLines(Paths.get(path));
        int funcs = 0, labels = 0, typed = 0, bad = 0;
        Set<String> seenAddr = new HashSet<>();
        Pattern typeRe = Pattern.compile("\\btype=([A-Za-z0-9_\\[\\]]+)");
        for (int i = 1; i < lines.size(); i++) {
            String[] f = lines.get(i).split("\t", -1);
            if (f.length < 3 || f[0].startsWith("#") || f[0].isEmpty()) continue;
            try {
                Address a = toAddr(Long.decode(f[0]));
                String kind = f[1], name = f[2], note = f.length > 3 ? f[3] : "";
                if (!seenAddr.add(f[0] + kind)) println("DUP addr+kind " + f[0] + " " + kind + " " + name);
                if (kind.equals("func")) {
                    Function fn = fm.getFunctionAt(a);
                    if (fn == null) { disassemble(a); fn = createFunction(a, name); }
                    if (fn == null) { bad++; println("NO FUNC @ " + a); continue; }
                    fn.setName(name, SourceType.USER_DEFINED);
                    funcs++;
                } else {
                    createLabel(a, name, true, SourceType.USER_DEFINED);
                    labels++;
                    Matcher m = typeRe.matcher(note);
                    if (kind.equals("ram") && m.find()) {
                        DataType dt = typeFor(m.group(1));
                        if (dt == null) { println("UNKNOWN TYPE " + m.group(1) + " for " + name); bad++; }
                        else {
                            clearListing(a, a.add(dt.getLength() - 1));
                            createData(a, dt);
                            typed++;
                        }
                    }
                }
                if (!note.isEmpty()) setPlateComment(a, note);
            } catch (Exception e) { bad++; println("BAD LINE " + (i + 1) + ": " + e); }
        }
        println("M0900Dump: applied funcs=" + funcs + " labels=" + labels + " typed=" + typed + " bad=" + bad);
    }
}
