/*
 * trace_pipe.h — ring buffer + drain task: hook_record_t -> USB/DUML.
 *
 * BENCH DIAGNOSTIC ONLY. See docs/fc-instrument-design.md section 3.4.
 *
 * Single-producer (DebugMon_Handler, exception context) / single-consumer
 * (one FreeRTOS task) ring buffer. The producer side must be O(1),
 * non-blocking and never wait — it drops and counts on overflow rather
 * than ever stalling the exception it's called from.
 */
#ifndef FC_INSTRUMENT_TRACE_PIPE_H
#define FC_INSTRUMENT_TRACE_PIPE_H

#include <stdint.h>
#include <stdbool.h>
#include "hook.h"

#ifdef __cplusplus
extern "C" {
#endif

/* Ring buffer depth. TODO(bringup): size against actual trace volume
 * expected (how many hook hits/sec at the chosen hook points, e.g.
 * duml_send call rate) vs available SRAM; each hook_record_t is
 * sizeof(hook_record_t) bytes (roughly 24 + HOOK_MAX_DEREF_LEN). */
#define TRACE_PIPE_DEPTH   64

/*
 * Transport-agnostic send function, shared with readmem.c's
 * fc_instrument_send_fn shape (design doc section 1 — both commands'
 * replies go out through the same kind of hook, either the clean-room
 * app's own DUML stack or a thin wrapper over the stock duml_send at
 * 0x0804f862 in the appended-patch-payload build mode).
 */
typedef void (*fc_instrument_send_fn)(const uint8_t *bytes, uint16_t len);

/* Install the transport used to drain trace records out. Call once at
 * init; can be the same function pointer passed to readmem_set_transport,
 * or a distinct one if traces and read-mem replies should go out
 * different channels (e.g. traces over USB bulk, read-mem replies over
 * CAN1 DUML) — the design intentionally allows either. */
void trace_pipe_set_transport(fc_instrument_send_fn send_fn);

/* Push one record from the producer side (DebugMon_Handler). Returns
 * false if the buffer was full (record dropped, drop counter bumped) —
 * never blocks, never allocates. Safe to call from exception context. */
bool trace_pipe_push(const hook_record_t *rec);

/* Monotonic microsecond-ish timestamp for hook_record_t.timestamp. Backed
 * by TIM2 per docs/fc-instrument-design.md section 3.1 (TIM2 is already
 * the dominant free-running time-base in the stock firmware per
 * fc-io-inventory.md — reuse it, don't stand up a second timer). */
uint32_t trace_pipe_timestamp_now(void);

/* How many records have been dropped since boot/last reset, for the host
 * to detect "the trace is lossy at this hook rate" rather than silently
 * missing data. */
uint32_t trace_pipe_dropped_count(void);

/*
 * FreeRTOS drain task entry point. Blocks on a counting semaphore/task
 * notification bumped by trace_pipe_push, then batches whatever's
 * available into DUML frames (one hook_record_t per frame, or several
 * packed per frame up to the transport's max payload — TODO(bringup):
 * decide batching once the real DUML max-payload-per-transport figure is
 * confirmed, see readmem.h's READMEM_CHUNK_MAX note for the same
 * open question) and calls the installed transport.
 *
 * Signature matches the common FreeRTOS `TaskFunction_t` shape
 * (void (*)(void *)) so it can be passed directly to xTaskCreate.
 */
void trace_pipe_drain_task(void *params);

#ifdef __cplusplus
}
#endif

#endif /* FC_INSTRUMENT_TRACE_PIPE_H */
