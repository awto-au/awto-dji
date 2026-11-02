// Ghidra headless POST-script, Intel i6050 WiMAX firmware (awto-dji#61). Decompile pass.
// Args: <addr1,addr2,...> <out_dir>. Decompiles each listed function (DecompInterface) and
// appends to <out_dir>/decompile.txt. Per-function timeout 30s: these are small (<=1200 byte)
// Thumb/ARM functions; Ghidra's own decompiler typically resolves them in well under 1s, 30s is
// a 30x+ backstop against a pathological case, not a measured bound.
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionManager;
import java.io.PrintWriter;
import java.nio.file.*;

public class IntelWimaxDecompile extends GhidraScript {
    static final int TIMEOUT_S = 30;

    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String[] addrs = args[0].split(",");
        Path outDir = Paths.get(args[1]);
        Files.createDirectories(outDir);
        FunctionManager fm = currentProgram.getFunctionManager();
        DecompInterface decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        int ok = 0, fail = 0;
        try (PrintWriter w = new PrintWriter(outDir.resolve("decompile.txt").toString(), "UTF-8")) {
            for (String hex : addrs) {
                Address a = toAddr(Long.decode(hex.trim()));
                Function f = fm.getFunctionContaining(a);
                if (f == null) { w.println("=== NO FUNCTION @ " + hex + " ==="); fail++; continue; }
                DecompileResults r = decomp.decompileFunction(f, TIMEOUT_S, monitor);
                w.println("=== " + f.getEntryPoint() + " " + f.getName() + " ===");
                if (r.decompileCompleted()) {
                    w.println(r.getDecompiledFunction().getC());
                    ok++;
                } else {
                    w.println("DECOMPILE FAILED: " + r.getErrorMessage());
                    fail++;
                }
                w.println();
            }
        }
        decomp.dispose();
        println("IntelWimaxDecompile: ok=" + ok + " fail=" + fail + " -> " + outDir.resolve("decompile.txt"));
    }
}
