// Ghidra headless PRE-script for the m0900 (STM32F103) image, issues awto-au/awto-dji#36, #83.
// Run via scripts/re/m0900_ghidra_names.py (raw load at 0x08008000). No args.
// Adds uninitialized SRAM / peripheral / SCS blocks so that literal-pool pointers into them
// get references and the decompiler shows named globals. Flash block is renamed "app_flash".
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;

public class M0900Setup extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {
            if (b.getStart().getOffset() == 0x08008000L) { b.setName("app_flash"); b.setWrite(false); b.setExecute(true); }
        }
        // SRAM top = initial SP 0x20004cb8 (vector[0]); 20 KB part (STM32F103xB size).
        add(mem, "SRAM", 0x20000000L, 0x5000L, true);
        add(mem, "PERIPH", 0x40000000L, 0x23400L, true);
        add(mem, "UID", 0x1FFFF7E0L, 0x20L, false);
        add(mem, "SCS", 0xE000E000L, 0x1000L, true);
        println("M0900Setup: blocks=" + mem.getBlocks().length);
    }

    void add(Memory mem, String name, long addr, long len, boolean write) throws Exception {
        if (mem.getBlock(toAddr(addr)) != null) return;
        MemoryBlock b = mem.createUninitializedBlock(name, toAddr(addr), len, false);
        b.setRead(true); b.setWrite(write); b.setExecute(false); b.setVolatile(true);
    }
}
