/*
 * hook.h — Cortex-M4 FPB + DebugMonitor runtime function hook tracer
 * (Command B)
 *
 * BENCH DIAGNOSTIC ONLY. See docs/fc-instrument-design.md section 3 and the
 * safety banner in fc/instrument/README.md.
 *
 * install_hook(addr) programs an FPB instruction-address comparator so that
 * when the core reaches `addr`, a DebugMonitor exception fires (NOT a
 * halting breakpoint — the RTOS and everything else keeps running). The
 * handler captures the AAPCS argument registers + LR + a timestamp, pushes
 * a record to trace_pipe's ring buffer, then performs a single-step +
 * re-arm so the comparator doesn't immediately refire on the same PC.
 *
 * release_hook(addr) disables the comparator; execution timing at that
 * address returns to normal (no hook overhead once released).
 *
 * NEVER install a hook on a control-loop / motor-mixer / ESC-output
 * function. This header intentionally does not take a "function name"
 * argument with any built-in safety list beyond what's documented in the
 * README's banned-address table — the caller is responsible for only ever
 * passing comms-layer addresses (duml_send, DUML dispatch, etc. — see the
 * design doc section 3.5 for the specific list).
 */
#ifndef FC_INSTRUMENT_HOOK_H
#define FC_INSTRUMENT_HOOK_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* How many bytes of the arg0-pointed buffer (if any) to also capture per
 * hit, for hooks where the first argument is a buffer pointer (e.g.
 * duml_send(buf, len) — capturing *buf tells you what was actually sent).
 * 0 disables buffer capture for that hook (captures registers only). */
#define HOOK_MAX_DEREF_LEN   64

typedef enum {
    HOOK_OK                 = 0,
    HOOK_ERR_NO_FREE_SLOT    = 1,  /* all FPB code comparators in use */
    HOOK_ERR_ALREADY_HOOKED  = 2,
    HOOK_ERR_NOT_HOOKED      = 3,  /* release_hook on an address with no hook */
    HOOK_ERR_FPB_UNAVAILABLE = 4,  /* FP_CTRL reports 0 comparators, or SWD
                                     * halting-debug currently owns the unit */
} hook_status_t;

/* One captured call record, pushed to the ring buffer by DebugMon_Handler.
 * Kept small and fixed-size so the ring buffer can be a plain array
 * (no dynamic allocation in exception context). */
typedef struct __attribute__((packed)) {
    uint32_t timestamp;     /* TIM2 free-running microsecond counter —
                              * fc-io-inventory.md identifies TIM2 as the
                              * dominant time-base already in use by the
                              * stock firmware; reuse it rather than stand
                              * up a second timer */
    uint32_t func_addr;     /* which hook fired (== stacked PC at match) */
    uint32_t r0, r1, r2, r3; /* AAPCS first four args */
    uint32_t lr;             /* caller's return address */
    uint8_t  deref_len;      /* 0..HOOK_MAX_DEREF_LEN, bytes valid in buf[] */
    uint8_t  deref_status;   /* readmem_status_t cast to uint8_t, in case the
                               * dereference faulted (hooked fn called with a
                               * bad pointer) */
    uint8_t  buf[HOOK_MAX_DEREF_LEN];
} hook_record_t;

/* Install a hook at `func_addr`. `deref_len` > 0 additionally captures
 * that many bytes pointed to by R0 at each hit (0 = registers only).
 * Returns HOOK_OK or an error; on error no comparator is consumed. */
hook_status_t install_hook(uint32_t func_addr, uint8_t deref_len);

/* Disable the comparator watching func_addr. Idempotent-safe to call on an
 * address that isn't currently hooked (returns HOOK_ERR_NOT_HOOKED, no
 * side effect). */
hook_status_t release_hook(uint32_t func_addr);

/* Release every currently-installed hook. Call this before any
 * control-relevant test, or on shutdown/panic, as a blanket "make sure
 * nothing is hooked" safety net. */
void release_all_hooks(void);

/* One-time init: reads FP_CTRL to discover the real comparator count,
 * verifies halting-debug (C_DEBUGEN) is not already claiming the FPB,
 * configures DEMCR.MON_EN and the DebugMonitor exception priority.
 * Must run before any install_hook call. Returns false if the FPB is
 * unavailable (see HOOK_ERR_FPB_UNAVAILABLE). */
bool hook_subsystem_init(void);

/* How many code comparators this part implements (read from FP_CTRL at
 * hook_subsystem_init time), and how many are currently free. Exposed so
 * trace_pipe/the command dispatcher can report capacity to the host. */
uint32_t hook_comparator_count(void);
uint32_t hook_comparator_free(void);

/*
 * DebugMon_Handler — the actual exception handler. Declared here (not
 * static) because it must be the symbol the vector table names (either
 * directly, in the clean-room build, or via a redirected vector/weak-
 * symbol override in the appended-patch-payload build — see README).
 * Not intended to be called directly by application code.
 */
void DebugMon_Handler(void);

#ifdef __cplusplus
}
#endif

#endif /* FC_INSTRUMENT_HOOK_H */
