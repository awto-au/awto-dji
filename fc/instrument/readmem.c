/*
 * readmem.c — DUML "read-any-memory" command handler (Command A)
 *
 * BENCH DIAGNOSTIC ONLY — see docs/fc-instrument-design.md section 2 and the
 * safety banner in fc/instrument/README.md. Read-only by construction: no
 * function in this file ever treats `addr` as a write destination.
 *
 * Two layers of safety, both required:
 *   1. A static whitelist of known-good regions, checked BEFORE any
 *      dereference (cheap, catches typos/garbage addresses with zero fault
 *      risk).
 *   2. A fault-guarded read (temporary BusFault_Handler) for addresses that
 *      are nominally in-range but might still fault (e.g. unmapped holes
 *      inside the 0x40000000+ peripheral space, or a flash sector mid-erase).
 */

#include "readmem.h"
#include <string.h>
#include <stdbool.h>

/* ------------------------------------------------------------------------
 * TODO(bringup): confirm these against the actual CMSIS device header for
 * the exact F427 part in this FC (STM32F427xx / STM32F427xI etc.) — pull
 * from stm32f4xx.h / core_cm4.h once the toolchain is wired up. Values below
 * match the standard ARMv7-M SCB layout, which does not vary by vendor.
 * ------------------------------------------------------------------------ */
#define SCB_BASE        (0xE000ED00UL)
#define SCB_SHCSR       (*(volatile uint32_t *)(SCB_BASE + 0x24))
#define SCB_CFSR        (*(volatile uint32_t *)(SCB_BASE + 0x28))
#define SCB_SHCSR_BUSFAULTENA   (1UL << 17)

/* CFSR bus-fault sub-register bits we care about for reporting, not for
 * deciding fault vs no-fault (that's "did the handler run at all"). */
#define CFSR_BFARVALID  (1UL << 15) /* BFSR bit 7, in CFSR byte 1 => <<8 */

/* ------------------------------------------------------------------------
 * Static whitelist — docs/fc-instrument-design.md section 2.2.
 * TODO(bringup): fill in the real flash/SRAM sizes for this part from the
 * linker script / DBGMCU->IDCODE once on real hardware; the sizes below are
 * the STM32F427 datasheet nominal maxima and should be treated as
 * upper bounds, not verified facts, until confirmed on this exact chip.
 * ------------------------------------------------------------------------ */
typedef struct {
    uint32_t base;
    uint32_t size;
    const char *name;   /* for trace/debug logging only */
} mem_region_t;

static const mem_region_t s_whitelist[] = {
    { 0x08000000UL, 0x00100000UL, "flash (loader+app, banks 1+2)" },
    { 0x20000000UL, 0x00030000UL, "SRAM (112KB SRAM1+2, nominal)" },
    { 0x10000000UL, 0x00010000UL, "CCM RAM (64KB)" },
    { 0x1FFF7800UL, 0x00000210UL, "OTP area (0x1FFF7800-0x1FFF7A0F)" },
    { 0x1FFF7A10UL, 0x0000000CUL, "96-bit UID" },
    { 0x1FFFC000UL, 0x00000010UL, "option bytes (read-only here)" },
    { 0x40000000UL, 0x00100000UL, "peripheral region (AHB/APB1/APB2)" },
    /* TODO(bringup): add external memory via FSMC (0xA0000000) only if/when
     * confirmed in use (fc-io-inventory.md marks FSMC usage as likely
     * unused/minimal — I). Omitted for now rather than guessed. */
};
#define WHITELIST_COUNT (sizeof(s_whitelist) / sizeof(s_whitelist[0]))

static fc_instrument_send_fn s_send = NULL;

void readmem_set_transport(fc_instrument_send_fn send_fn)
{
    s_send = send_fn;
}

/* ------------------------------------------------------------------------
 * Whitelist check. Rejects any request whose [addr, addr+len) is not
 * wholly contained in exactly one whitelisted region. No dereference here.
 * ------------------------------------------------------------------------ */
static bool range_is_whitelisted(uint32_t addr, uint32_t len)
{
    for (size_t i = 0; i < WHITELIST_COUNT; i++) {
        uint32_t base = s_whitelist[i].base;
        uint32_t size = s_whitelist[i].size;
        /* reject on any overflow too, not just out-of-range */
        if (addr >= base && (uint64_t)addr + len <= (uint64_t)base + size) {
            return true;
        }
    }
    return false;
}

/* ------------------------------------------------------------------------
 * Fault-guarded copy.
 *
 * Design (docs/fc-instrument-design.md section 2.3): install a temporary
 * BusFault_Handler, perform the copy one word/byte at a time through a
 * recognizable helper (so the fault handler can tell "did the fault happen
 * inside my probe read"), and have the fault handler advance the stacked PC
 * past the faulting instruction and set a sticky flag instead of escalating.
 *
 * TODO(bringup): the real implementation needs a small assembly helper
 * (e.g. `readmem_probe_load_word`) whose entry/exit addresses are known at
 * link time, so BusFault_Handler can check "was the faulting PC inside
 * [probe_start, probe_end)" and, if so, fix up the stacked PC to point just
 * after the load and return cleanly; otherwise it must chain to whatever
 * the *real* system BusFault handler would have done (this guard must not
 * swallow a genuine, unrelated bus fault elsewhere in the system).
 *
 * The sketch below shows the intended control flow and state machine; the
 * actual fault recovery (stack-frame PC fixup) is the one piece that must
 * be written in/validated against real disassembly on target, so it is
 * left as a clearly marked TODO rather than a guess.
 * ------------------------------------------------------------------------ */

static volatile bool     s_probe_active = false;
static volatile bool     s_probe_faulted = false;
/* TODO(bringup): extern declarations for the probe helper + its address
 * bounds, defined in a small .s file once the toolchain is set up, e.g.:
 *   extern uint8_t readmem_probe_load_byte(const volatile uint8_t *p);
 *   extern const uint32_t readmem_probe_start, readmem_probe_end;
 */

/* Saved/prior BusFault_Handler, if the application already had one
 * installed (e.g. the host app's own fault reporting) — must be restored
 * afterwards either way. TODO(bringup): on real hardware this needs to
 * read/write the actual vector table entry (NVIC/VTOR-relative), not a
 * plain function pointer, unless the build uses a weak-symbol override
 * scheme at link time instead. Both approaches are valid; pick one when
 * the toolchain is in hand and the vector table's final location (flash
 * vs a RAM-remapped copy, relevant for the appended-patch-payload build
 * mode) is known.
 */
typedef void (*fault_handler_fn)(void);
static fault_handler_fn s_prior_busfault_handler = NULL;

static void readmem_bus_fault_handler(void)
{
    /* TODO(bringup): real implementation —
     *   1. read the stacked exception frame (MSP, since this guard only
     *      runs from thread-mode task context, never from within another
     *      exception — see READMEM_ERR_BUSY below for why that matters);
     *   2. if s_probe_active and stacked PC is within the probe helper's
     *      address range, set s_probe_faulted = true, rewrite the stacked
     *      PC to the instruction after the probe's load, clear
     *      SCB->CFSR bus-fault bits, and return (exception return resumes
     *      just past the fault, s_probe_active's caller sees the flag);
     *   3. otherwise, this is a real, unrelated bus fault: chain to
     *      s_prior_busfault_handler (or hang/log, matching whatever this
     *      firmware build's default behavior is) — do NOT silently eat it.
     */
    s_probe_faulted = true; /* placeholder until (1)-(3) above are written */
}

size_t readmem_guarded_copy(void *dst, const void *src, size_t len,
                             readmem_status_t *out_status)
{
    /* Reentrancy guard: this swaps a core exception vector, so it must
     * never be interrupted by another caller doing the same thing. In the
     * normal command-A path this is called from one FreeRTOS task, so a
     * mutex is enough; hook.c's DebugMon_Handler also calls this (design
     * doc section 3.3) from exception context, which is a DIFFERENT
     * caller context — TODO(bringup): decide whether hook.c gets its own
     * lighter-weight guard (it already knows it's reading a function
     * argument pointer, a narrower and arguably safer case than arbitrary
     * command-A addresses) rather than sharing this one, to avoid a
     * priority-inversion-shaped bug where an exception-context caller
     * blocks on a guard a task context caller is holding.
     */
    if (s_probe_active) {
        if (out_status) *out_status = READMEM_ERR_BUSY;
        return 0;
    }

    s_probe_active = true;
    s_probe_faulted = false;

    /* TODO(bringup): swap in readmem_bus_fault_handler, remembering the
     * prior one in s_prior_busfault_handler; ensure SCB_SHCSR's
     * BUSFAULTENA bit is set so this is a BusFault, not an escalated
     * HardFault (a HardFault is NOT recoverable the same way). */
    SCB_SHCSR |= SCB_SHCSR_BUSFAULTENA;

    size_t copied = 0;
    uint8_t *d = (uint8_t *)dst;
    const volatile uint8_t *s = (const volatile uint8_t *)src;
    for (size_t i = 0; i < len; i++) {
        /* TODO(bringup): replace this direct dereference with the
         * recognizable probe helper (readmem_probe_load_byte) once it
         * exists, so the fault handler can identify "the fault happened
         * here". A plain volatile read, as written, WILL still fault the
         * CPU on a bad address — that's expected and desired; what's
         * missing until the helper exists is the handler's ability to
         * resume cleanly rather than just setting the flag after the
         * fact (which, on real hardware, happens only because the
         * exception return address was fixed up — this sketch is
         * intentionally incomplete here, flagged for bring-up). */
        d[i] = s[i];
        copied++;
        if (s_probe_faulted) {
            copied = i; /* this byte did not actually land */
            break;
        }
    }

    /* TODO(bringup): restore s_prior_busfault_handler. */
    s_probe_active = false;

    if (out_status) {
        *out_status = s_probe_faulted ? READMEM_ERR_FAULT : READMEM_OK;
    }
    return copied;
}

/* ------------------------------------------------------------------------
 * Command handler entry point.
 * ------------------------------------------------------------------------ */
void readmem_handle_request(const readmem_req_t *req)
{
    if (!s_send) {
        return; /* transport not installed — nothing we can do but drop */
    }

    uint32_t addr = req->addr;
    uint16_t remaining = req->len;

    if (!range_is_whitelisted(addr, remaining)) {
        readmem_resp_chunk_t resp;
        resp.addr = addr;
        resp.chunk_len = 0;
        resp.status = READMEM_ERR_RANGE;
        /* TODO(bringup): wrap in the actual DUML frame header (SOF 0x55,
         * CRC8 seed 0x77, CRC16 seed 0x3692 per app/packages/duml) before
         * calling s_send — this file intentionally stays DUML-framing-
         * agnostic per the design doc's transport-interface split; the
         * glue code (clean-room app's DUML stack, or the appended-payload
         * wrapper over duml_send 0x0804f862) owns framing. */
        s_send((const uint8_t *)&resp,
                (uint16_t)(sizeof(resp) - sizeof(resp.data)));
        return;
    }

    while (remaining > 0) {
        uint16_t chunk = remaining > READMEM_CHUNK_MAX ? READMEM_CHUNK_MAX
                                                        : remaining;
        readmem_resp_chunk_t resp;
        resp.addr = addr;

        readmem_status_t st;
        size_t got = readmem_guarded_copy(resp.data, (const void *)(uintptr_t)addr,
                                           chunk, &st);

        resp.chunk_len = (uint16_t)got;
        resp.status = (uint8_t)st;

        size_t frame_len = sizeof(resp) - sizeof(resp.data) + resp.chunk_len;
        s_send((const uint8_t *)&resp, (uint16_t)frame_len);

        if (st != READMEM_OK) {
            /* stop streaming further chunks once we hit a fault/guard
             * conflict — the host gets the error status for this chunk
             * and can decide whether to retry a narrower range */
            break;
        }

        addr += chunk;
        remaining -= chunk;
    }
}
