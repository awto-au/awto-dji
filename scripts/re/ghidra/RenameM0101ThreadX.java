// Ghidra headless post-script: apply the follow-up pass's ThreadX primitive/wrapper
// findings (docs/m0101-threadx-reversing.md section 8.1) as real function names +
// comments in the existing m0101 project, so the Ghidra project itself (not just the
// doc) carries the result. Run via scripts/re/m0101_rename_threadx.py, not directly.
// No base address assumption - addresses below are file offsets, same framing as the
// first pass's import (loaded at 0x0).
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;
import java.util.*;

public class RenameM0101ThreadX extends GhidraScript {
    @Override
    public void run() throws Exception {
        Map<Long, String> renames = new LinkedHashMap<>();
        renames.put(0xc1e0L, "_tx_thread_create_candidate");
        renames.put(0xccecL, "_tx_semaphore_create_candidate");
        renames.put(0xd638L, "_tx_mutex_create_candidate");
        renames.put(0xe060L, "_tx_event_flags_create_candidate");
        renames.put(0xa30cL, "AmbaKAL_TaskCreate_candidate");
        renames.put(0xa8c4L, "AmbaKAL_SemaphoreCreate_candidate");
        renames.put(0xacd0L, "AmbaKAL_MutexCreate_candidate");
        renames.put(0xaf38L, "AmbaKAL_EventFlagCreate_candidate");
        renames.put(0x9cd4L, "GenericTaskSpawnHelper_candidate");

        String comment = "Issue #37 follow-up pass, docs/m0101-threadx-reversing.md 8.1: "
            + "identified via ThreadX magic control-block ID write (eclipse-threadx/threadx "
            + "common/inc/tx_*.h TX_*_ID constants) - a write (not read+compare) of the ID "
            + "right after the object pointer arg. Not a confirmed symbol name, a strong "
            + "byte-pattern match.";

        for (Map.Entry<Long, String> e : renames.entrySet()) {
            Address addr = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(e.getKey());
            Function f = currentProgram.getFunctionManager().getFunctionAt(addr);
            if (f == null) {
                println("WARN: no function at " + addr + " for " + e.getValue());
                continue;
            }
            f.setName(e.getValue(), SourceType.USER_DEFINED);
            f.setComment(comment);
            println("renamed " + addr + " -> " + e.getValue());
        }
    }
}
