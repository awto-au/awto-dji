// Ghidra headless PRE-script for the m0400 gimbal (STM32F4, Cortex-M4) image, issue awto-au/awto-dji#41.
// Run via scripts/re/m0400_ghidra_names.py (raw load at 0x08008000). No args.
// Adds SRAM / CCM / peripheral / SCS blocks so literal-pool pointers into them get references and the
// decompiler shows named globals. Flash block is renamed "app_flash".
import ghidra.app.script.GhidraScript;
import ghidra.program.model.mem.*;

public class M0400Setup extends GhidraScript {
    @Override
    public void run() throws Exception {
        Memory mem = currentProgram.getMemory();
        for (MemoryBlock b : mem.getBlocks()) {
            if (b.getStart().getOffset() == 0x08008000L) { b.setName("app_flash"); b.setWrite(false); b.setExecute(true); }
        }
        // SP = vector[0] 0x2000fc40; F405/407: 112 KB SRAM1 + 16 KB SRAM2 contiguous from 0x20000000.
        add(mem, "SRAM", 0x20000000L, 0x20000L, true);
        add(mem, "CCM", 0x10000000L, 0x10000L, true);
        add(mem, "PERIPH", 0x40000000L, 0x80000L, true);   // APB1/APB2/AHB1 incl. ETH, OTG_HS
        add(mem, "AHB2", 0x50000000L, 0x61000L, true);     // DCMI, CRYP, HASH, RNG, OTG_FS
        add(mem, "OTP_UID", 0x1FFF7800L, 0x400L, false);
        add(mem, "SCS", 0xE000E000L, 0x1000L, true);
        println("M0400Setup: blocks=" + mem.getBlocks().length);
    }

    void add(Memory mem, String name, long addr, long len, boolean write) throws Exception {
        if (mem.getBlock(toAddr(addr)) != null) return;
        MemoryBlock b = mem.createUninitializedBlock(name, toAddr(addr), len, false);
        b.setRead(true); b.setWrite(write); b.setExecute(false); b.setVolatile(true);
    }
}
