// Ghidra headless PRE-script for the Intel i6050 (Evans Peak) SBCF firmware, issue awto-au/awto-dji#61.
// Run via scripts/re/intel_wimax_ghidra.py. Args: <regions_dir>.
// 1. Adds the other final-memory regions (regions.tsv from intel_wimax_sbcf.py --out) to the program
//    that headless imported (reg_e80000.bin @ 0xe80000, ARM:LE:32:v5t).
// 2. Maps the 0x740000 vector/low-code region also at 0x0 (I: 0x740000 is the host load window of address 0).
// 3. Seeds functions: literal-pool words that point at a prologue (ARM stmfd..lr / Thumb push {..lr}).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.*;
import ghidra.program.model.lang.Register;
import ghidra.program.model.mem.*;
import java.io.*;
import java.math.BigInteger;
import java.nio.file.*;
import java.util.*;

public class IntelWimaxSetup extends GhidraScript {
    static final long[][] CODE = { {0xDC0000L, 0x8D210L}, {0xE80000L, 0x7BA44L}, {0x0L, 0x7720L} };

    @Override
    public void run() throws Exception {
        Path dir = Paths.get(getScriptArgs()[0]);
        Memory mem = currentProgram.getMemory();
        List<String> lines = Files.readAllLines(dir.resolve("regions.tsv"));
        for (int i = 1; i < lines.size(); i++) {
            String[] f = lines.get(i).split("\t");
            long addr = Long.decode(f[1]);
            if (addr == 0xE80000L) continue; // already imported
            addRegion(mem, dir.resolve(f[0]), addr, "reg_" + String.format("%06x", addr));
            if (addr == 0x740000L) addRegion(mem, dir.resolve(f[0]), 0L, "low0_vectors");
        }
        // Mark code blocks executable, the rest data.
        for (MemoryBlock b : mem.getBlocks()) {
            long s = b.getStart().getOffset();
            boolean code = false;
            for (long[] c : CODE) if (s == c[0]) code = true;
            b.setExecute(code); b.setWrite(true); b.setRead(true);
        }
        Register tmode = currentProgram.getLanguage().getRegister("TMode");
        int armSeed = 0, thumbSeed = 0, conflicts = 0;
        Set<Long> seen = new HashSet<>();
        for (long[] c : CODE) {
            for (long off = 0; off + 4 <= c[1]; off += 4) {
                long a = c[0] + off;
                long v = mem.getInt(toAddr(a)) & 0xFFFFFFFFL;
                boolean thumb = (v & 1) != 0;
                long t = v & ~1L;
                if (!inCode(t)) continue;
                if (!seen.add(v)) continue;
                Address ta = toAddr(t);
                if (thumb) {
                    int h = mem.getShort(ta) & 0xFFFF;
                    if ((h & 0xFF00) != 0xB500) continue;
                    try {
                        currentProgram.getProgramContext().setValue(tmode, ta, ta, BigInteger.ONE);
                    } catch (Exception e) { conflicts++; continue; }
                    disassemble(ta);
                    createFunction(ta, null);
                    thumbSeed++;
                } else if ((t & 3) == 0) {
                    int w = mem.getInt(ta);
                    if ((w & 0xFFFF0000) != 0xE92D0000 || (w & 0x4000) == 0) continue;
                    disassemble(ta);
                    createFunction(ta, null);
                    armSeed++;
                }
            }
        }
        // ARM entry stub, reset/IRQ code at address 0 and vector table.
        for (long e : new long[] {0xE80000L, 0x0L, 0x40L, 0x70L, 0xF4L, 0xF8L, 0x108L, 0x118L}) {
            disassemble(toAddr(e));
            createFunction(toAddr(e), null);
        }
        println("IntelWimaxSetup: seeded ARM=" + armSeed + " Thumb=" + thumbSeed + " conflicts=" + conflicts);
    }

    static boolean inCode(long t) {
        for (long[] c : CODE) if (t >= c[0] && t < c[0] + c[1]) return true;
        return false;
    }

    void addRegion(Memory mem, Path file, long addr, String name) throws Exception {
        byte[] data = Files.readAllBytes(file);
        try (InputStream in = new ByteArrayInputStream(data)) {
            mem.createInitializedBlock(name, toAddr(addr), in, data.length, monitor, false);
        }
    }
}
