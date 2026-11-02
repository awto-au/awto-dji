// Ghidra headless PRE-script for the m1400 (LPC1765, Cortex-M3) image, issues #84, #83. Run via scripts/re/m1400_ghidra_names.py.
// Adds uninitialized SRAM / AHB SRAM / peripheral / SCS blocks so RAM rows of docs/symbols/c1_m1400.tsv apply and
// literal-pool pointers into them get references. Flash block (base 0xA000) renamed "app_flash".
// Sizes (LPC176x user manual): local SRAM 32 KB @0x10000000 (initial SP 0x10007f60), AHB SRAM 2x16 KB @0x2007C000.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;

public class M1400Setup extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {
            if (b.getStart().getOffset() == 0xA000L) { b.setName("app_flash"); b.setWrite(false); b.setExecute(true); }
        }
        add(mem, "SRAM", 0x10000000L, 0x8000L, true);
        add(mem, "AHBSRAM", 0x2007C000L, 0x8000L, true);
        add(mem, "PERIPH_APB", 0x40000000L, 0x100000L, true);
        add(mem, "PERIPH_AHB", 0x50000000L, 0x200000L, true);
        add(mem, "SCS", 0xE000E000L, 0x1000L, true);
        println("M1400Setup: blocks=" + mem.getBlocks().length);
    }

    void add(Memory mem, String name, long addr, long len, boolean write) throws Exception {
        if (mem.getBlock(toAddr(addr)) != null) return;
        MemoryBlock b = mem.createUninitializedBlock(name, toAddr(addr), len, false);
        b.setRead(true); b.setWrite(write); b.setExecute(false); b.setVolatile(true);
    }
}
