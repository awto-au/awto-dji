// Ghidra headless POST-script for the Intel i6050 SBCF firmware, issue awto-au/awto-dji#61.
// Args: <symbols.tsv> <out_dir>. Applies docs/symbols/intel_i6050_fw1.5.tsv (addr kind name note source;
// kinds func|data|label|region) with a plate comment, then dumps functions (with call counts), call sites,
// defined strings and string xrefs to <out_dir>/dump.txt. Output stays in ./tmp (contains vendor code).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.PrintWriter;
import java.nio.file.*;
import java.util.*;

public class IntelWimaxNames extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        Listing listing = currentProgram.getListing();
        FunctionManager fm = currentProgram.getFunctionManager();
        SymbolTable st = currentProgram.getSymbolTable();
        int applied = 0, bad = 0;
        List<String> lines = Files.readAllLines(Paths.get(args[0]));
        for (int i = 1; i < lines.size(); i++) {
            String[] f = lines.get(i).split("\t", -1);
            if (f.length < 3 || f[0].startsWith("#")) continue;
            try {
                Address a = toAddr(Long.decode(f[0]));
                String kind = f[1], name = f[2];
                String note = f.length > 3 ? f[3] : "";
                if (kind.equals("func")) {
                    Function fn = fm.getFunctionAt(a);
                    if (fn == null) fn = createFunction(a, name);
                    if (fn == null) { bad++; println("NO FUNC @ " + a); continue; }
                    fn.setName(name, SourceType.USER_DEFINED);
                } else {
                    createLabel(a, name, true, SourceType.USER_DEFINED);
                }
                if (!note.isEmpty()) setPlateComment(a, note);
                applied++;
            } catch (Exception e) { bad++; println("BAD LINE " + i + ": " + e); }
        }
        println("IntelWimaxNames: applied=" + applied + " bad=" + bad);

        Map<Long, List<String>> callers = new TreeMap<>();
        InstructionIterator ii = listing.getInstructions(true);
        while (ii.hasNext()) {
            Instruction ins = ii.next();
            if (!ins.getFlowType().isCall()) continue;
            Function caller = fm.getFunctionContaining(ins.getAddress());
            for (Reference r : ins.getReferencesFrom()) {
                if (!r.getReferenceType().isCall()) continue;
                callers.computeIfAbsent(r.getToAddress().getOffset(), k -> new ArrayList<>())
                    .add(ins.getAddress() + "<" + (caller == null ? "?" : caller.getName()));
            }
        }
        Path out = Paths.get(args[1]);
        Files.createDirectories(out);
        try (PrintWriter w = new PrintWriter(out.resolve("dump.txt").toString(), "UTF-8")) {
            w.println("=== FUNCTIONS ===");
            int n = 0;
            for (Function f : fm.getFunctions(true)) {
                n++;
                List<String> cs = callers.getOrDefault(f.getEntryPoint().getOffset(), Collections.emptyList());
                w.println("FUNCTION\t" + f.getEntryPoint() + "\t" + f.getName() + "\tsize=" + f.getBody().getNumAddresses()
                    + "\tcallsites=" + cs.size());
            }
            w.println("=== CALLSITES ===");
            for (Map.Entry<Long, List<String>> e : callers.entrySet())
                w.println(Long.toHexString(e.getKey()) + " <- " + String.join(" ", e.getValue()));
            w.println("=== STRINGS (with referencing functions) ===");
            DataIterator di = listing.getDefinedData(true);
            while (di.hasNext()) {
                Data d = di.next();
                if (!(d.getValue() instanceof String)) continue;
                StringBuilder sb = new StringBuilder();
                for (Reference r : getReferencesTo(d.getAddress())) {
                    Function f = fm.getFunctionContaining(r.getFromAddress());
                    sb.append(' ').append(r.getFromAddress()).append(f == null ? "" : "<" + f.getName());
                }
                w.println(d.getAddress() + "\t" + d.getValue().toString().replace("\n", "\\n") + "\t" + sb);
            }
            println("IntelWimaxNames: functions=" + n + " dump=" + out.resolve("dump.txt"));
        }
    }
}
