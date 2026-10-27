/*
 * readmem.h — DUML "read-any-memory" command handler (Command A)
 *
 * BENCH DIAGNOSTIC ONLY. Part of the fc/instrument tool described in
 * docs/fc-instrument-design.md. Read-only: this module has no write/erase
 * entry point at all, by design (option bytes / OTP are one careless write
 * away from a brick; there is no code path here that can do that).
 *
 * See docs/fc-instrument-design.md section 2.
 */
#ifndef FC_INSTRUMENT_READMEM_H
#define FC_INSTRUMENT_READMEM_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/* Wire format (DUML payload), packed, little-endian (Cortex-M4 default). */
typedef struct __attribute__((packed)) {
    uint32_t addr;
    uint16_t len;      /* total bytes requested; handler splits into chunks */
} readmem_req_t;

/* One response chunk. Sent as the payload of one DUML frame each. */
#define READMEM_CHUNK_MAX 128  /* TODO: tune to the DUML max payload size used
                                 * by the chosen transport (CAN1 frames vs USB
                                 * bulk); must match duml_build_send's limits. */

typedef enum {
    READMEM_OK           = 0,
    READMEM_ERR_RANGE    = 1,  /* address/len rejected by the static whitelist */
    READMEM_ERR_FAULT    = 2,  /* BusFault caught during the actual read */
    READMEM_ERR_BUSY     = 3,  /* guard already in use (reentrancy — see .c) */
} readmem_status_t;

typedef struct __attribute__((packed)) {
    uint32_t addr;
    uint16_t chunk_len;        /* 0 when status != READMEM_OK */
    uint8_t  status;           /* readmem_status_t */
    uint8_t  data[READMEM_CHUNK_MAX];
} readmem_resp_chunk_t;

/*
 * Transport-agnostic send hook. The instrument's two build modes (clean-room
 * app vs appended patch payload calling the stock duml_send at 0x0804f862,
 * see design doc section 1) both satisfy this by providing one small
 * function; readmem.c never calls a transport directly.
 */
typedef void (*fc_instrument_send_fn)(const uint8_t *bytes, uint16_t len);

/* Install the DUML send callback used to stream response chunks. Call once
 * at init, from either build mode's glue code. */
void readmem_set_transport(fc_instrument_send_fn send_fn);

/*
 * Handle one incoming read_mem_req. Splits into READMEM_CHUNK_MAX-byte
 * chunks, sends one response frame per chunk via the installed transport.
 * Safe to call from the DUML dispatch task context (not an ISR — it may
 * briefly install a BusFault handler, see readmem.c).
 */
void readmem_handle_request(const readmem_req_t *req);

/*
 * Fault-guarded memory copy, exposed for reuse by hook.c (the DebugMon
 * handler needs to safely dereference a hooked function's pointer argument
 * without risking a fault inside exception context — see design doc
 * section 3.3). Returns the number of bytes actually copied; on a
 * rejected/faulted read this is less than len (possibly 0) and *out_status
 * explains why.
 *
 * NOTE: when called from exception context (as hook.c does), the BusFault
 * handler swap in readmem.c must be reentrancy-safe against being invoked
 * from a higher-priority exception than the one that is already using the
 * guard — see the TODO in readmem.c's guard install/restore.
 */
size_t readmem_guarded_copy(void *dst, const void *src, size_t len,
                             readmem_status_t *out_status);

#ifdef __cplusplus
}
#endif

#endif /* FC_INSTRUMENT_READMEM_H */
