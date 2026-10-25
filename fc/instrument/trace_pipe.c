/*
 * trace_pipe.c — lock-free SPSC ring buffer + FreeRTOS drain task.
 * See docs/fc-instrument-design.md section 3.4 and trace_pipe.h.
 *
 * BENCH DIAGNOSTIC ONLY.
 */

#include "trace_pipe.h"
#include <string.h>

/* ------------------------------------------------------------------------
 * TODO(bringup): these three includes/decls are STM32Cube HAL / FreeRTOS
 * APIs; left as forward declarations rather than real #includes so this
 * file's structure/logic can be read without the actual SDK present. Wire
 * up the real headers (`FreeRTOS.h`, `semphr.h`, `stm32f4xx_hal.h` or the
 * TIM2 register pair directly) when building for real.
 * ------------------------------------------------------------------------ */
typedef void *SemaphoreHandle_t;   /* TODO(bringup): real FreeRTOS type */
extern SemaphoreHandle_t xSemaphoreCreateCounting(uint32_t max, uint32_t initial);
extern int xSemaphoreGive(SemaphoreHandle_t sem);          /* ISR-unsafe variant name kept simple here */
extern int xSemaphoreGiveFromISR(SemaphoreHandle_t sem, void *pxHigherPriorityTaskWoken);
extern int xSemaphoreTake(SemaphoreHandle_t sem, uint32_t ticks_to_wait);
#define TRACE_PIPE_WAIT_FOREVER  0xFFFFFFFFUL

/* TIM2 direct register access, per fc-io-inventory.md: TIM2 base
 * 0x40000000, used as the dominant free-running microsecond time-base
 * already in the stock firmware. TODO(bringup): confirm TIM2's configured
 * prescaler on THIS build gives microsecond ticks (the stock firmware's
 * own TIM2 config is not necessarily what this instrument's build uses —
 * if this is the appended-patch-payload mode, TIM2 is already running
 * under DJI's own config and this just reads CNT; if it's the clean-room
 * app mode, this instrument must configure TIM2's PSC/ARR itself at init,
 * which is not yet written here). */
#define TIM2_BASE     (0x40000000UL)
#define TIM2_CNT      (*(volatile uint32_t *)(TIM2_BASE + 0x24))

/* ------------------------------------------------------------------------
 * Ring buffer state.
 * ------------------------------------------------------------------------ */
static hook_record_t s_ring[TRACE_PIPE_DEPTH];
static volatile uint32_t s_head = 0;   /* next slot producer will write */
static volatile uint32_t s_tail = 0;   /* next slot consumer will read */
static volatile uint32_t s_dropped = 0;

static SemaphoreHandle_t s_data_ready = (SemaphoreHandle_t)0;

static fc_instrument_send_fn s_send = NULL;

void trace_pipe_set_transport(fc_instrument_send_fn send_fn)
{
    s_send = send_fn;
}

uint32_t trace_pipe_timestamp_now(void)
{
    return TIM2_CNT;
}

uint32_t trace_pipe_dropped_count(void)
{
    return s_dropped;
}

static inline uint32_t ring_next(uint32_t idx)
{
    uint32_t n = idx + 1;
    return (n == TRACE_PIPE_DEPTH) ? 0 : n;
}

bool trace_pipe_push(const hook_record_t *rec)
{
    /* SPSC lock-free: producer only ever touches s_head, consumer only
     * ever touches s_tail; both read the other's index but never write
     * it. This is safe on Cortex-M4 without extra barriers for this
     * single-word-index pattern, PROVIDED s_ring[s_head] is fully written
     * before s_head is advanced (ensured by the memcpy-then-advance order
     * below) — TODO(bringup): if the compiler is allowed to reorder
     * aggressively, add an explicit __DMB() (data memory barrier) between
     * the record copy and the s_head store; on a single core without
     * reordering-capable write buffers between SRAM accesses this is
     * usually unnecessary on Cortex-M4, but verify rather than assume
     * once real silicon/compiler flags are in hand.
     */
    uint32_t head = s_head;
    uint32_t next = ring_next(head);

    if (next == s_tail) {
        /* full */
        s_dropped++;
        return false;
    }

    memcpy(&s_ring[head], rec, sizeof(hook_record_t));
    s_head = next;

    if (s_data_ready) {
        /* TODO(bringup): this must use the FromISR variant with the
         * higher-priority-task-woken pattern (and a subsequent
         * portYIELD_FROM_ISR / taskYIELD as appropriate) once this is
         * actually called from DebugMon_Handler's exception context —
         * calling the non-ISR xSemaphoreGive from exception context is
         * a bug, flagged here rather than silently done wrong. */
        int higher_prio_woken = 0;
        xSemaphoreGiveFromISR(s_data_ready, &higher_prio_woken);
        (void)higher_prio_woken;
    }

    return true;
}

static bool ring_pop(hook_record_t *out)
{
    uint32_t tail = s_tail;
    if (tail == s_head) {
        return false; /* empty */
    }
    memcpy(out, &s_ring[tail], sizeof(hook_record_t));
    s_tail = ring_next(tail);
    return true;
}

/* ------------------------------------------------------------------------
 * Drain task.
 * ------------------------------------------------------------------------ */
void trace_pipe_drain_task(void *params)
{
    (void)params;

    if (!s_data_ready) {
        /* TODO(bringup): size the counting semaphore's max count to
         * TRACE_PIPE_DEPTH; this placeholder create call keeps the
         * control flow readable but is not the final init-ordering (this
         * really belongs in a one-time trace_pipe_init() called before
         * hook_subsystem_init(), so the semaphore exists before any hook
         * can fire — flagged rather than fixed here since the overall
         * task/init ordering is an integration decision for main()). */
        s_data_ready = xSemaphoreCreateCounting(TRACE_PIPE_DEPTH, 0);
    }

    for (;;) {
        xSemaphoreTake(s_data_ready, TRACE_PIPE_WAIT_FOREVER);

        hook_record_t rec;
        /* Drain everything currently available before blocking again —
         * batches naturally if several hits queued up while this task was
         * off the CPU, rather than round-tripping the semaphore once per
         * record. */
        while (ring_pop(&rec)) {
            if (s_send) {
                /*
                 * TODO(bringup): wrap `rec` in the real DUML frame header
                 * (SOF 0x55 / CRC8 seed 0x77 / CRC16 seed 0x3692, per
                 * app/packages/duml's codec and duml_crc16 0x0804f024 in
                 * the appended-payload build mode) before handing bytes
                 * to s_send — this file, like readmem.c, stays framing-
                 * agnostic by design (design doc section 1's transport
                 * interface). Also TODO: respect whatever max payload the
                 * chosen transport has; sizeof(hook_record_t) with
                 * HOOK_MAX_DEREF_LEN=64 is ~88 bytes, check that against
                 * the real CAN1/USB DUML frame limit and split if needed,
                 * mirroring readmem.c's chunking.
                 */
                s_send((const uint8_t *)&rec, (uint16_t)sizeof(rec));
            }
        }
    }
}
