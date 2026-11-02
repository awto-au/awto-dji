// Ghidra headless PRE-script for the m0306 (STM32F427, Cortex-M4) image, issues awto-au/awto-dji#40, #83.
// Run via scripts/re/m0306_ghidra_names.py (raw load at 0x08020000). No args.
// Adds uninitialized SRAM / CCM / peripheral / SCS blocks so literal-pool pointers into them get references
// and RAM label rows apply. Flash block renamed "app_flash". SRAM top = initial SP 0x2002ff00 (192 KB SRAM1-3 end 0x20030000).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;

public class M0306Setup extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {
            if (b.getStart().getOffset() == 0x08020000L) { b.setName("app_flash"); b.setWrite(false); b.setExecute(true); }
        }
        add(mem, "SRAM", 0x20000000L, 0x30000L, true);   // SRAM1+SRAM2+SRAM3 = 112+16+64 KB (RM0090 table 1)
        add(mem, "CCM", 0x10000000L, 0x10000L, true);    // 64 KB core-coupled
        add(mem, "PERIPH_APB_AHB1", 0x40000000L, 0x40000L, true);  // APB1, APB2, AHB1 (to 0x4003FFFF)
        add(mem, "PERIPH_AHB2", 0x50000000L, 0x61000L, true);      // OTG_FS .. RNG (to 0x50060FFF)
        add(mem, "UID", 0x1FFF7A00L, 0x20L, false);
        add(mem, "SCS", 0xE000E000L, 0x1000L, true);
        println("M0306Setup: blocks=" + mem.getBlocks().length);
    }

    void add(Memory mem, String name, long addr, long len, boolean write) throws Exception {
        if (mem.getBlock(toAddr(addr)) != null) return;
        MemoryBlock b = mem.createUninitializedBlock(name, toAddr(addr), len, false);
        b.setRead(true); b.setWrite(write); b.setExecute(false); b.setVolatile(true);
    }
}
