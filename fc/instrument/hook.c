/*
 * hook.c — Cortex-M4 FPB + DebugMonitor runtime function hook tracer
 * (Command B). See docs/fc-instrument-design.md section 3.
 *
 * BENCH DIAGNOSTIC ONLY. Never install a hook on a motor/control-loop
 * function; never run with props on. See fc/instrument/README.md.
 */

#include "hook.h"
#include "readmem.h"   /* reuse the fault-guarded copy for arg-pointer deref */
#include "trace_pipe.h"
#include <string.h>

/* ------------------------------------------------------------------------
 * Register definitions.
 *
 * FPB (Flash Patch and Breakpoint unit), ARMv7-M Architecture Reference
 * Manual C1.11 / Cortex-M4 TRM. Base 0xE0002000.
 *   FP_CTRL   @ 0xE0002000
 *     bit0        ENABLE       - 1 = FPB enabled
 *     bit1        KEY          - must write 1 to enable writes to ENABLE
 *                                 (write-only "key" bit, per ARM TRM)
 *     bits[3:0]   NUM_CODE[3:0] (low nibble of code comparator count)
 *     bits[7:4]   NUM_LIT[3:0]  (literal comparator count, unused here)
 *     bits[14:12] NUM_CODE[6:4] (high bits of code comparator count, FPBv2;
 *                                 FPBv1 parts report 0 here and only use
 *                                 bits[3:0] — TODO(bringup): confirm which
 *                                 FPB version this F427 silicon revision
 *                                 implements; code below handles both by
 *                                 combining the fields, which is a no-op
 *                                 on FPBv1 parts where the high bits are 0)
 *   FP_COMP[n] @ 0xE0002008 + 4*n   (n = 0 .. NUM_CODE-1)
 *     FPBv1 (most Cortex-M4 parts, including STM32F4): bits[28:2] = address,
 *       bit[1] = half-word select when the comparator also needs to
 *       distinguish the upper/lower half of the matched word (REPLACE
 *       field bits[31:30] = 0b00 for a plain breakpoint-on-match use, i.e.
 *       not doing flash-patch remapping), bit0 = ENABLE.
 *
 * TODO(bringup): verify FPB version (v1 vs v2) for the exact F427 revision
 * on this board via FP_CTRL read at boot; v2 parts take a plain 32-bit
 * address in FP_COMP with no half-word quirk. The address mask/shift below
 * assumes FPBv1, matching the Cortex-M4's documented FPB (Cortex-M4 TRM
 * does not define FPBv2 — v2 is M7/M33+ — so FPBv1 is the correct
 * assumption for this part; left as TODO only to be re-checked against the
 * actual chip's debug ROM table, not because v2 is expected).
 * ------------------------------------------------------------------------ */
#define FPB_BASE            (0xE0002000UL)
#define FP_CTRL             (*(volatile uint32_t *)(FPB_BASE + 0x00))
#define FP_COMP(n)          (*(volatile uint32_t *)(FPB_BASE + 0x08 + 4 * (n)))

#define FP_CTRL_ENABLE      (1UL << 0)
#define FP_CTRL_KEY         (1UL << 1)
#define FP_CTRL_NUM_CODE_LO_MASK  0x0FUL        /* bits[3:0] */
#define FP_CTRL_NUM_CODE_LO_SHIFT 0
#define FP_CTRL_NUM_CODE_HI_MASK  0x7000UL      /* bits[14:12] */
#define FP_CTRL_NUM_CODE_HI_SHIFT 12

#define FP_COMP_ENABLE      (1UL << 0)
#define FP_COMP_ADDR_MASK   (0x1FFFFFFCUL)      /* bits[28:2], word-aligned */

#define MAX_COMPARATORS     8  /* upper bound on array sizing; actual count
                                 * read from FP_CTRL at init, see
                                 * hook_subsystem_init() */

/* ------------------------------------------------------------------------
 * DEMCR (Debug Exception and Monitor Control Register), SCB peripheral,
 * ARMv7-M. Fixed address, does not vary by vendor.
 * ------------------------------------------------------------------------ */
#define DEMCR               (*(volatile uint32_t *)(0xE000EDFCUL))
#define DEMCR_MON_EN         (1UL << 16)
#define DEMCR_MON_PEND       (1UL << 17)
#define DEMCR_MON_STEP       (1UL << 18)
#define DEMCR_MON_REQ        (1UL << 19)
#define DEMCR_VC_CORERESET   (1UL << 0)

/* C_DEBUGEN lives in the DHCSR, which is only meaningfully writable by an
 * external debugger over DAP; from firmware we can only READ it to detect
 * "is a halting debugger currently attached", per design doc section 4
 * (SWD-vs-DebugMon mutual exclusion caveat). */
#define DHCSR               (*(volatile uint32_t *)(0xE000EDF0UL))
#define DHCSR_C_DEBUGEN      (1UL << 0)

/* SHPR3 holds the priority for SysTick (bits[31:24]) and DebugMonitor
 * (bits[23:16]) among others on ARMv7-M. */
#define SCB_SHPR3            (*(volatile uint32_t *)(0xE000ED20UL))
#define SHPR3_DEBUGMON_SHIFT 16
#define SHPR3_DEBUGMON_MASK  (0xFFUL << SHPR3_DEBUGMON_SHIFT)

/* TODO(bringup): pick the actual priority value here once the rest of this
 * firmware's interrupt priority map is known (design doc section 4.1 —
 * DebugMonitor cannot preempt equal/higher-priority ISRs, so this value
 * must be chosen relative to every other ISR priority in the build, not
 * in isolation). 0x20 is a placeholder mid-range priority (assuming 8
 * priority bits implemented, which is itself a TODO to confirm against
 * this part's NVIC_PRIO_BITS). */
#define DEBUGMON_PRIORITY_PLACEHOLDER  0x20UL

/* ------------------------------------------------------------------------
 * Per-comparator hook state.
 * ------------------------------------------------------------------------ */
typedef enum {
    SLOT_FREE = 0,
    SLOT_ARMED,     /* comparator enabled, watching for a match */
    SLOT_STEPPING,  /* just matched; comparator disabled, single-stepping
                      * one instruction before re-arming (see design doc
                      * section 3.3) */
} slot_state_t;

typedef struct {
    slot_state_t state;
    uint32_t     func_addr;
    uint8_t      deref_len;
} hook_slot_t;

static hook_slot_t s_slots[MAX_COMPARATORS];
static uint32_t    s_comparator_count = 0;   /* discovered at init */
static bool        s_initialized = false;

uint32_t hook_comparator_count(void) { return s_comparator_count; }

uint32_t hook_comparator_free(void)
{
    uint32_t free_count = 0;
    for (uint32_t i = 0; i < s_comparator_count; i++) {
        if (s_slots[i].state == SLOT_FREE) free_count++;
    }
    return free_count;
}

bool hook_subsystem_init(void)
{
    /* Refuse to proceed if a halting debugger already owns the debug
     * hardware (design doc section 4 — SWD halting-debug and DebugMonitor
     * both ultimately arbitrate the same FPB comparators; don't fight an
     * attached debugger). */
    if (DHCSR & DHCSR_C_DEBUGEN) {
        return false;
    }

    uint32_t ctrl = FP_CTRL;
    uint32_t num_lo = (ctrl & FP_CTRL_NUM_CODE_LO_MASK) >> FP_CTRL_NUM_CODE_LO_SHIFT;
    uint32_t num_hi = (ctrl & FP_CTRL_NUM_CODE_HI_MASK) >> FP_CTRL_NUM_CODE_HI_SHIFT;
    uint32_t count = num_lo | (num_hi << 4);

    if (count == 0 || count > MAX_COMPARATORS) {
        /* 0 => FPB reports no code comparators, which would be unusual for
         * this part but must be handled; >MAX_COMPARATORS => our static
         * array is undersized for this silicon, also handled as an error
         * rather than silently truncating. TODO(bringup): if a real part
         * reports more than MAX_COMPARATORS, raise MAX_COMPARATORS rather
         * than clamp count, so capacity is reported accurately. */
        return false;
    }
    s_comparator_count = count;

    memset(s_slots, 0, sizeof(s_slots));

    /* Enable the FPB unit itself (per-comparator enable is separate, done
     * in install_hook). KEY must be written as 1 alongside ENABLE per the
     * ARM TRM's documented write sequence for this register. */
    FP_CTRL = FP_CTRL_ENABLE | FP_CTRL_KEY;

    /* Configure DebugMonitor: enable it, set its priority. TODO(bringup):
     * replace DEBUGMON_PRIORITY_PLACEHOLDER with a value chosen against
     * this build's real priority map (see comment above the define). */
    uint32_t shpr3 = SCB_SHPR3;
    shpr3 &= ~SHPR3_DEBUGMON_MASK;
    shpr3 |= (DEBUGMON_PRIORITY_PLACEHOLDER << SHPR3_DEBUGMON_SHIFT) & SHPR3_DEBUGMON_MASK;
    SCB_SHPR3 = shpr3;

    DEMCR |= DEMCR_MON_EN;

    s_initialized = true;
    return true;
}

static int find_slot_for_addr(uint32_t addr)
{
    for (uint32_t i = 0; i < s_comparator_count; i++) {
        if (s_slots[i].state != SLOT_FREE && s_slots[i].func_addr == addr) {
            return (int)i;
        }
    }
    return -1;
}

static int find_free_slot(void)
{
    for (uint32_t i = 0; i < s_comparator_count; i++) {
        if (s_slots[i].state == SLOT_FREE) return (int)i;
    }
    return -1;
}

hook_status_t install_hook(uint32_t func_addr, uint8_t deref_len)
{
    if (!s_initialized) {
        return HOOK_ERR_FPB_UNAVAILABLE;
    }
    /*
     * TODO(bringup, policy): this is the enforcement point referenced by
     * docs/fc-instrument-design.md section 4 and README.md's banned-
     * address table — "never hook a control-loop function". As written,
     * this function does NOT itself consult a control-loop address list
     * (none is authoritative yet in docs/symbols/m0306.tsv). Once such a
     * list exists, add a check here that rejects func_addr against it
     * before doing anything else, returning a new error status. Until
     * then this is a documentation-level, not code-level, safety
     * constraint — flagged explicitly rather than silently assumed.
     */
    if (find_slot_for_addr(func_addr) >= 0) {
        return HOOK_ERR_ALREADY_HOOKED;
    }

    int slot = find_free_slot();
    if (slot < 0) {
        return HOOK_ERR_NO_FREE_SLOT;
    }

    if (deref_len > HOOK_MAX_DEREF_LEN) {
        deref_len = HOOK_MAX_DEREF_LEN;
    }

    s_slots[slot].state = SLOT_ARMED;
    s_slots[slot].func_addr = func_addr;
    s_slots[slot].deref_len = deref_len;

    /* Program the comparator. FPBv1 address field is bits[28:2]; func_addr
     * must be instruction-aligned (Thumb => at least 2-byte aligned,
     * enforced implicitly by the mask below truncating bit0). */
    FP_COMP(slot) = (func_addr & FP_COMP_ADDR_MASK) | FP_COMP_ENABLE;

    return HOOK_OK;
}

hook_status_t release_hook(uint32_t func_addr)
{
    int slot = find_slot_for_addr(func_addr);
    if (slot < 0) {
        return HOOK_ERR_NOT_HOOKED;
    }

    FP_COMP(slot) = 0; /* clears ENABLE and the address field */
    s_slots[slot].state = SLOT_FREE;
    s_slots[slot].func_addr = 0;
    s_slots[slot].deref_len = 0;

    return HOOK_OK;
}

void release_all_hooks(void)
{
    for (uint32_t i = 0; i < s_comparator_count; i++) {
        if (s_slots[i].state != SLOT_FREE) {
            FP_COMP(i) = 0;
            s_slots[i].state = SLOT_FREE;
            s_slots[i].func_addr = 0;
            s_slots[i].deref_len = 0;
        }
    }
}

/* ------------------------------------------------------------------------
 * Exception frame layout, as pushed by the Cortex-M4 on exception entry
 * (ARMv7-M, basic frame — no FPU context here since R0-R3/R12/LR/PC/xPSR
 * are all that's needed for an AAPCS argument capture; the FPU lazy-stack
 * extension, if active, does not change these offsets, it only appends
 * FPU registers further up the stack).
 * ------------------------------------------------------------------------ */
typedef struct __attribute__((packed)) {
    uint32_t r0, r1, r2, r3, r12, lr, pc, xpsr;
} exc_frame_t;

/* TODO(bringup): this must be written in a way that reliably recovers the
 * exact SP that was active at exception entry (MSP or PSP, selected by
 * EXC_RETURN bit 2 / CONTROL.SPSEL at the time) — typically implemented as
 * a naked asm trampoline that reads the right SP and tail-calls a C
 * handler with the frame pointer as an argument, since a plain C function
 * has no portable way to read "the SP as it was for the interrupted
 * context" versus its own. Sketch:
 *
 *   __attribute__((naked)) void DebugMon_Handler(void) {
 *       asm volatile (
 *           "tst lr, #4            \n" // bit2 of EXC_RETURN: 0=MSP,1=PSP
 *           "ite eq                \n"
 *           "mrseq r0, msp         \n"
 *           "mrsne r0, psp         \n"
 *           "b debugmon_c_handler  \n" // tail-call with frame* in r0
 *       );
 *   }
 *
 * debugmon_c_handler(exc_frame_t *frame) below is that C-level handler.
 * Left as two pieces (asm trampoline + C body) rather than one function
 * because the trampoline must not have a C prologue (it would corrupt the
 * SP it's trying to read) — this file provides the C body; the trampoline
 * is a TODO for the actual build (a tiny .s file or inline asm block, per
 * the toolchain chosen).
 * ------------------------------------------------------------------------ */

static void debugmon_c_handler(exc_frame_t *frame)
{
    uint32_t matched_pc = frame->pc;

    /* Find which slot is in SLOT_STEPPING (a single-step completion) vs
     * which ARMED slot's address equals matched_pc (a fresh match). Both
     * cases are possible in principle if comparators land back-to-back;
     * check STEPPING first since that resolution must happen before any
     * new ARMED match is processed, to keep the per-slot state machine
     * (design doc section 3.3) correct. */
    for (uint32_t i = 0; i < s_comparator_count; i++) {
        if (s_slots[i].state == SLOT_STEPPING) {
            /* Step completed: re-arm this comparator, clear MON_STEP only
             * if no other slot is also mid-step (another comparator could
             * have matched in the same single-step window — handled by
             * only clearing MON_STEP once, after the loop, see below). */
            FP_COMP(i) = (s_slots[i].func_addr & FP_COMP_ADDR_MASK) | FP_COMP_ENABLE;
            s_slots[i].state = SLOT_ARMED;
        }
    }
    /* All stepping slots resolved for this entry; stop single-stepping.
     * TODO(bringup): if hooks can nest (a hooked function calls another
     * hooked function before the first's step completes), this needs a
     * per-slot MON_STEP reference count instead of a single global clear
     * — flagged as a known race per design doc section 4's
     * single-step-resume race caveat. */
    DEMCR &= ~DEMCR_MON_STEP;

    int slot = find_slot_for_addr(matched_pc);
    if (slot < 0) {
        /* Not a known hook address and not a pending step — spurious or
         * stale match; nothing to record. Should not happen in normal
         * operation; TODO(bringup): consider a diagnostic counter here. */
        return;
    }
    if (s_slots[slot].state != SLOT_ARMED) {
        /* Already mid-step for this slot somehow (shouldn't happen given
         * the handling above) — avoid double-processing. */
        return;
    }

    hook_record_t rec;
    rec.timestamp = trace_pipe_timestamp_now();
    rec.func_addr = matched_pc;
    rec.r0 = frame->r0;
    rec.r1 = frame->r1;
    rec.r2 = frame->r2;
    rec.r3 = frame->r3;
    rec.lr = frame->lr;
    rec.deref_len = 0;
    rec.deref_status = READMEM_OK;

    uint8_t want = s_slots[slot].deref_len;
    if (want > 0) {
        readmem_status_t st;
        size_t got = readmem_guarded_copy(rec.buf, (const void *)(uintptr_t)frame->r0,
                                           want, &st);
        rec.deref_len = (uint8_t)got;
        rec.deref_status = (uint8_t)st;
        /*
         * NOTE: readmem_guarded_copy's reentrancy guard (readmem.c) is
         * documented there as task-context-oriented; calling it from this
         * exception context is exactly the case flagged as a TODO in that
         * file. Do not ship this path without resolving that — a hook
         * that fires while command A's readmem handler is mid-copy on the
         * same core will currently get HOOK_ERR_BUSY-equivalent
         * (READMEM_ERR_BUSY) behavior rather than a clean interleave,
         * which is CORRECT (no corruption) but means a deref may be
         * silently skipped under contention. Acceptable for a bench tool,
         * but documented here rather than assumed.
         */
    }

    trace_pipe_push(&rec); /* ISR-safe, lock-free, drops-on-full */

    /* Disable this comparator and single-step past matched_pc, per the
     * design doc's resume sequence, so it doesn't immediately refire on
     * the instruction we're about to retire. */
    FP_COMP(slot) = 0;
    s_slots[slot].state = SLOT_STEPPING;
    DEMCR |= DEMCR_MON_STEP;
}

/*
 * Placeholder C-callable entry point. TODO(bringup): replace with the
 * naked-asm trampoline described above once the toolchain/build is set
 * up; this body is correct and complete for the register-capture and
 * resume LOGIC, only the "how do I get the right frame pointer into here"
 * plumbing is left for bring-up, since that is inherently
 * compiler/ABI-specific rather than a design question.
 */
void DebugMon_Handler(void)
{
    /* TODO(bringup): obtain the real exception frame pointer per the
     * trampoline sketch above; `frame` must NOT be read via a local
     * variable the compiler might spill through the (already consumed)
     * stack in a way that aliases the hardware-pushed frame. */
    exc_frame_t *frame = (exc_frame_t *)0; /* placeholder — see TODO above */
    if (frame != (exc_frame_t *)0) {
        debugmon_c_handler(frame);
    }
}
