/* m0900 (air_router_stm32f103) struct layouts - reverse-engineered, Ghidra /m0900 category.
   Companion to m0306-structs.h; produced by the systematic completeness pass documented in
   docs/air-router-stm32-full-pass.md. Two structs (radio_cfg_page_s, radio_state_s) predate
   this pass and are NOT re-declared here (see air-router-io-and-naming.md); everything below
   is new this pass, applied at the literal RAM addresses shown, with the flash-side literal-pool
   pointer words also retyped so the decompiler shows ->field_name at call sites (confirmed by
   re-decompile, not just comments).

   Tags: V verified (decompiled + reproducible via m0900_fullpass_{1,2,4,6}.py in
   scratchpad/ghscripts/), I inferred (structure/offsets are V, the real-world meaning of the
   field is I), U unknown (xref'd but role not resolved this pass). */

/* ---- PA1FaultCounters @ 0x200000a4, 8 bytes ----
   V structure (decompiled: pa1_fault_counter_tick @ 0x0800b808, pa1_pulse_strobe @ 0x0800b7cc).
   I meaning: looks like a link/error-rate counter gating a PA1 "antenna/relay" pulse -- consistent
   with the pre-existing pa1_pulse_strobe note and the upstream map's switch_active_quadrant name
   (not proven; no caller of pa1_fault_counter_tick itself was found this pass, same open item as
   pa1_pulse_strobe's own trigger). */
struct PA1FaultCounters {           // 0x8 bytes
  +0x00 uint32  fail_count;         // incremented each pa1_fault_counter_tick() call; >10 forces
                                    // GPIOA ODR bit1 (PA1) high directly, bypassing the timed pulse
  +0x04 uint32  call_count;         // gates pa1_pulse_strobe: must reach 0x4b (75) before a pulse
                                    // fires; both fields zeroed together once the pulse fires
};

/* ---- AntennaQuadrantState @ 0x200000c4, 4 bytes ----
   V structure (decompiled: quadrant_state_apply @ 0x0800bb1c).
   V address-exact match with upstream V01.07.0060 map's active_quadrant_state/quadrant_state/
   active_quadrant_num/quadrant_num at 0x200000C4-C7 (air-router-io-and-naming.md §4.3) -- this
   pass adds the actual field semantics the upstream map's bare names didn't carry.
   I meaning of the bit patterns written (RF path / antenna selection is the working hypothesis,
   not proven -- the two 32-bit registers toggled, read here as DAT_0800bbd8/DAT_0800bbdc, were
   not identified to a specific peripheral this pass). */
struct AntennaQuadrantState {       // 0x4 bytes
  +0x00 byte  applied_a;            // last value written back for field a (mirrors requested_a)
  +0x01 byte  requested_a;          // 1: set bit0x100 / clear bit0x80 in reg pair; 3: inverse
  +0x02 byte  applied_b;            // last value written back for field b
  +0x03 byte  requested_b;          // 2: set bit0x40 / clear bit4 in a 2nd reg; 4: inverse
};

/* ---- FpgaSensorAvgState @ 0x200000cc, 8 bytes ----
   V structure (decompiled: fpga_sensor_avg_update @ 0x0800be36). Ring storage is the separate
   10-float array fpga_sensor_avg_ring @ 0x20001638 (not inline in this struct).
   U meaning: the raw value being filtered comes from a chain of float-library calls whose flash
   operands (DAT_0800bea8..DAT_0800beb8) were not traced back to an FPGA/AD9363 register this
   pass -- read as "some periodic sensor-like reading, 10-sample moving average" rather than
   a proven temperature/RSSI value. Feeds a DUML GET reply (confirmed caller: the existing
   cmd_exec_set09_cmd13 note "float(0x0800be36)*10" in air-router-io-and-naming.md literally calls
   this function by address). */
struct FpgaSensorAvgState {         // 0x8 bytes
  +0x00 byte     ring_index;        // 0..9, wraps; indexes fpga_sensor_avg_ring[10] @ 0x20001638
  +0x01 byte[3]  pad_1;             // unused this pass
  +0x04 float    cached_avg;        // returned as-is while ring_index < 10; recomputed as the
                                     // mean of the 10-slot ring once the ring is full
};

/* ---- FlycDetectSampler @ 0x2000019c, 8 bytes ----
   V structure (decompiled: flyc_detect_ring_write @ 0x08011324, flyc_detect_ring_read @
   0x08011368). Matches and formalizes the existing air-router-deep-dive.md §1 note on DUML cmd
   0xda (FLYC Detection, cmdset 3): "rate-limited sample into RAM ring 0x20001f08, counter at
   0x2000019c+4 resets at 0x47=71" -- that note already had the right addresses and threshold;
   this pass adds the Ghidra Structure and the two functions' real names.
   Ring storage is the separate 0x34-byte array flyc_detect_ring @ 0x20001f08 (13 x 4-byte
   records: byte0 = ring_index<<4, bytes1-3 = 3 payload bytes copied from the DUML packet). */
struct FlycDetectSampler {          // 0x8 bytes
  +0x00 byte     ring_index;        // 0..12, wraps; indexes flyc_detect_ring[13] @ 0x20001f08
  +0x01 byte[3]  pad_1;             // unused this pass
  +0x04 uint32   sample_timer;      // counts DUML cmd 0xda packets seen since the last sample;
                                     // >0x46 (70) triggers a sample + reset to 0
};

/* ---- Plain globals typed this pass (not full structs) ----
   All V for "this address is dereferenced this way by this function"; I/U for the hardware
   meaning, as noted per-row. */

// 0x200000ac  void* tim3_cb_ptr;   (was exti_cb1_ptr; corrected 2026-11-02)
//   V: setter tim3_cb_set 0x0800b8a2; tim3_irq 0x0800b830 (vector 45 = IRQ29 TIM3) tests TIM3 UIF
//   (TIM_GetITStatus(0x40000400,1)), clears it, calls *tim3_cb_ptr. TIM3 = PSC 71, ARR 13999 => 14 ms (0x0800b858).

// 0x200000b0  void* tim2_cb_table[4];   (was exti_cb_table; corrected 2026-11-02)
//   V: setter tim2_cb_table_set 0x0800ba14; tim2_irq 0x0800b8f2 (vector 44 = IRQ28 TIM2) tests TIM2 flags
//   {1,4,8,0x10}, clears the one set, calls the matching slot. TIM2 OC1..4 at 999/5999/8999/13499 us in a 14 ms period (0x0800b97a).

// 0x200000c0  void* exti1_cb_ptr;   (was exti_cb2_ptr)
//   V: setter exti1_cb_set 0x0800bac8; exti1_irq (vector 23 = IRQ7 EXTI1) 0x0800ba60 clears EXTI line 1 and jumps to *ptr.

// 0x200000e4  byte assoc_table_init_flag;
//   read/set inside assoc_table_lookup_or_insert() @ 0x0800c440: a generic 20-slot x 6-byte
//   {key_byte, uint32 value, status_byte} association table, lazily zero-initialized on first
//   call via this flag. Table = assoc_table @ 0x200016c4 (AssocEntry[20]); aged and reported by status_report_tick
//   (DUML cs0 cmd 0xf9, 5-byte records) every 25 ticks. Keys written by callers of assoc_table_lookup_or_insert: U.

// 0x20000104  uint32 rcc_clock_cache_scalar;
//   written by rcc_clock_calc_cached() @ 0x0800ddfa, which is structurally identical to
//   rcc_get_clocks_freq() @ 0x08009854 (same AHB/APB prescaler-table idiom) but computes and
//   caches a single derived clock value instead of filling a 5-word buffer. I: likely a cached
//   PCLK/HCLK-derived value consumed by a timing calculation elsewhere (e.g. delay_units or a
//   baud/timer reload); U which consumer (not traced).

// 0x200001bc  uint16 duml_notify_seq_counter;
//   shared DUML sequence number for 5 near-identical "push notification" senders
//   (0x08011682/0x080116e8/0x08011738/0x08011786/0x080117d2), all of which build a 2-byte
//   payload and send cmdset 0 cmd 0x7c via FUN_08011c1e with this counter as the frame seq.
//   I: an event-class notification mechanism (each of the 5 functions maps a 0/1/2 input to a
//   different status code: 6/1, 7/2, 8/3, 9/4, and a bare-0 "no event" case) -- which physical
//   events map to which function is U (not traced to callers this pass).

// 0x200001c0  uint32 route_counter_generic;
//   incremented (no other logic) by FUN_080118b8 @ 0x080118b8. U: which route/stat this counts
//   (not traced to callers).

/* ---- Naming pass 2026-11-02 (issues #36, #83): SRAM objects, addresses at link base 0x08008000 ---- */
/* Tags: V verified in decompile/disasm, I inferred, U unknown. Sizes from stride/neighbour arithmetic. */

/* ByteRing (V, ring_push 0x0800c274 / ring_pop 0x0800c294 / ring_count 0x0800c24c), 0x14 B
   head = next write idx, tail = next read idx, size, mask = size-1, buf. */
/* CanQueue (V, can_queue_init 0x0800b3ec): std_id, embedded ByteRing at +4, is_tx at +0x18; 0x1c B.
   Instances: 0x20002330 (0x412 TX), 0x2000234c (0x413 RX), 0x20002538 (0x414 TX), 0x20002554 (0x415 RX). */
/* CanState (V, can1_tx_irq 0x0800b298, can_queue_init): tx_idle set when TX queues drained; counts of registered queues. */
/* CanTables (V): rx[13] then tx[13] pointer slots; can_rx0_handler walks rx, can1_tx_irq walks tx. */
/* UartIo @0x20000014 (V, uart_send 0x0800b0a4): busy[0]=port1 [1]=port3 [2]=port2 (guard vs re-entry), then 6 packed rings
   (unaligned u32 fields; Cortex-M3 allows it): usart1 tx 0x17, rx 0x2b; usart2 tx 0x3f, rx 0x53; usart3 tx 0x67, rx 0x7b. */
/* DumlParser (V, duml_parser_init 0x08011a7e / duml_parser_feed 0x08011a8e), 0x10 B:
   +0 buf, +4 frame_cb (all channels: duml_crc16_check 0x08011be7), +8 bufsize, +0xa expected_len (10-bit),
   +0xc cur_len, +0xe state (0..0xc). */
/* DinDebounce @0x2000009c (V disasm; I role): level flag + sample counter of a board-dependent input pin. */
/* TickState @0x200000dc (V, tick_scheduler 0x0800c154): 5/20/100 ms flags (SysTick 1 ms) + tick counter. */
/* StatusState @0x200000e8 (V, status_report_tick 0x0800c34a): status bit word (set/clear by status_flags_set/clear),
   report tick counter, last-sent word. */
/* AssocEntry (V, assoc_table_lookup_or_insert 0x0800c440): key (0 = free), 4-byte value, age (dropped at >=7). */

/* @ghidra-begin */
#pragma pack(push, 1)
typedef struct PA1FaultCounters { unsigned int fail_count; unsigned int call_count; } PA1FaultCounters;
typedef struct AntennaQuadrantState { unsigned char applied_a; unsigned char requested_a; unsigned char applied_b; unsigned char requested_b; } AntennaQuadrantState;
typedef struct FpgaSensorAvgState { unsigned char ring_index; unsigned char pad_1[3]; float cached_avg; } FpgaSensorAvgState;
typedef struct FlycDetectSampler { unsigned char ring_index; unsigned char pad_1[3]; unsigned int sample_timer; } FlycDetectSampler;
typedef struct ByteRing { unsigned int head; unsigned int tail; unsigned int size; unsigned int mask; unsigned char *buf; } ByteRing;
typedef struct CanQueue { unsigned int std_id; ByteRing ring; unsigned char is_tx; unsigned char pad[3]; } CanQueue;
typedef struct CanState { unsigned char tx_idle; unsigned char pad[3]; unsigned int tx_count; unsigned int rx_count; } CanState;
typedef struct CanTables { CanQueue *rx[13]; CanQueue *tx[13]; } CanTables;
typedef struct UartIo { unsigned char busy[3]; ByteRing usart1_tx; ByteRing usart1_rx; ByteRing usart2_tx; ByteRing usart2_rx; ByteRing usart3_tx; ByteRing usart3_rx; } UartIo;
typedef struct DumlParser { unsigned char *buf; void *frame_cb; unsigned short bufsize; unsigned short expected_len; unsigned short cur_len; unsigned short state; } DumlParser;
typedef struct DinDebounce { unsigned char level; unsigned char pad[3]; unsigned int count; } DinDebounce;
typedef struct TickState { unsigned char flag_5ms; unsigned char flag_20ms; unsigned char flag_100ms; unsigned char pad; unsigned int count; } TickState;
typedef struct StatusState { unsigned int flags; unsigned int tick; unsigned int flags_sent; } StatusState;
typedef struct AssocEntry { unsigned char key; unsigned int value; unsigned char age; } AssocEntry;
#pragma pack(pop)
/* @ghidra-end */
