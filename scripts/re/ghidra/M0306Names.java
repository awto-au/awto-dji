// Ghidra headless POST-script for the m0306 (STM32F427, Cortex-M4 Thumb-2) image, issues #40, #83.
// Run via scripts/re/m0306_ghidra_names.py, not directly.
// Args: <out.txt> <structs.h> <symbols.tsv>... (TSV flavour detected from the header line:
//   `addr kind name note source` new; `addr name note source` legacy m0306.tsv; `addr name note` data; `addr name type_id size` params)
//  1. seeds functions at vector-table handlers and every BL/B.W target;
//  2. applies docs/symbols/m0306_V01.11.0020.tsv (addr kind name note source; kinds func|ram|table|code|region|label)
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

public class M0306Names extends GhidraScript {
    DataTypeManager dtm;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outPath = args[0];
        long flashBase = 0x08020000L;
        long flashEnd = flashBase + currentProgram.getMemory().getBlock(toAddr(flashBase)).getSize() - 1;
        dtm = currentProgram.getDataTypeManager();

        // Vector table: word 0 = initial SP, words 1..n = handlers (bit 0 = Thumb).
        for (int i = 1; i < 0x70; i++) {
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

        // DUML dispatch table: 65 x 8 B {thumb funcptr u32, key u16, pad u16} at 0x080ab440 (docs/fc-message-path.md).
        for (long t = 0x080ab440L; t < 0x080ab644L; t += 8) {
            long v = currentProgram.getMemory().getInt(toAddr(t)) & 0xFFFFFFFFL;
            long tt = v & ~1L;
            if ((v & 1) != 0 && tt >= flashBase && tt <= flashEnd) {
                try { disassemble(toAddr(tt)); createFunction(toAddr(tt), null); } catch (Exception e) { }
            }
        }
        if (args.length > 1) loadStructs(args[1]);
        for (int i = 2; i < args.length; i++) applySymbols(args[i]);

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
        if (a < 0 || b < 0) { println("M0306Names: no @ghidra block in " + path); return; }
        String c = text.substring(text.indexOf('\n', a) + 1, b);
        c = c.substring(0, c.lastIndexOf("\n") + 1);
        CParser parser = new CParser(dtm);
        parser.parse(c);
        for (DataType t : parser.getComposites().values()) dtm.resolve(t, DataTypeConflictHandler.REPLACE_HANDLER);
        int n = 0;
        Iterator<Structure> it = dtm.getAllStructures();
        while (it.hasNext()) { it.next(); n++; }
        println("M0306Names: structs in DTM=" + n + " parsed=" + parser.getComposites().size());
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

    static String clean(String n) { return n.replaceAll("[^A-Za-z0-9_.]", "_"); }

    void applySymbols(String path) throws Exception {
        FunctionManager fm = currentProgram.getFunctionManager();
        List<String> lines = Files.readAllLines(Paths.get(path));
        String[] hdr = lines.get(0).split("\t", -1);
        String flavour = hdr.length >= 3 && hdr[1].equals("kind") ? "new"
                : hdr.length >= 4 && hdr[2].equals("type_id") ? "params"
                : hdr.length >= 4 && hdr[2].equals("note") && hdr[3].equals("source") ? "legacy" : "data";
        int funcs = 0, labels = 0, typed = 0, bad = 0, renamedDup = 0;
        Pattern typeRe = Pattern.compile("\\btype=([A-Za-z0-9_\\[\\]]+)");
        for (int i = 1; i < lines.size(); i++) {
            String[] f = lines.get(i).split("\t", -1);
            if (f.length < 3 || f[0].startsWith("#") || f[0].isEmpty()) continue;
            try {
                Address a = toAddr(Long.decode(f[0]));
                if (!currentProgram.getMemory().contains(a)) { bad++; println("OUTSIDE " + f[0] + " " + f[1]); continue; }
                String kind, name, note, typeSpec = null;
                if (flavour.equals("new")) { kind = f[1]; name = clean(f[2]); note = f.length > 3 ? f[3] : ""; }
                else if (flavour.equals("params")) {
                    kind = "ram"; name = clean(f[1]); note = "param table, type_id " + f[2] + " size " + f[3];
                    if (f[3].equals("1")) typeSpec = "u8"; else if (f[3].equals("2")) typeSpec = "u16"; else if (f[3].equals("4")) typeSpec = "u32";
                } else if (flavour.equals("legacy")) {
                    name = clean(f[1]); note = f.length > 2 ? f[2] : "";
                    kind = (name.endsWith("_tbl") || name.endsWith("_table")) ? "table" : "func";
                } else {
                    name = clean(f[1]); note = f.length > 2 ? f[2] : "";
                    kind = a.getOffset() >= 0x20000000L ? "ram" : "table";
                }
                if (kind.equals("func")) {
                    Function fn = fm.getFunctionAt(a);
                    if (fn == null) { disassemble(a); fn = createFunction(a, name); }
                    if (fn == null) { bad++; println("NO FUNC @ " + a + " " + name); continue; }
                    try { fn.setName(name, SourceType.USER_DEFINED); }
                    catch (Exception e) { fn.setName(name + "_" + a, SourceType.USER_DEFINED); renamedDup++; }
                    funcs++;
                } else {
                    createLabel(a, name, true, SourceType.USER_DEFINED);
                    labels++;
                    Matcher m = typeRe.matcher(note);
                    String spec = typeSpec != null ? typeSpec : (m.find() ? m.group(1) : null);
                    if (spec != null && (kind.equals("ram") || kind.equals("table"))) {
                        DataType dt = typeFor(spec);
                        if (dt == null) { println("UNKNOWN TYPE " + spec + " for " + name); bad++; }
                        else {
                            clearListing(a, a.add(dt.getLength() - 1));
                            createData(a, dt);
                            typed++;
                        }
                    }
                }
                if (!note.isEmpty()) setPlateComment(a, note);
            } catch (Exception e) { bad++; println("BAD LINE " + (i + 1) + " " + path + ": " + e); }
        }
        println("M0306Names: " + flavour + " " + Paths.get(path).getFileName() + " applied funcs=" + funcs + " labels=" + labels
                + " typed=" + typed + " dupnames=" + renamedDup + " bad=" + bad);
    }
}
