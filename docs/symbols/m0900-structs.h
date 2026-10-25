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

// 0x200000ac  void* exti_cb1_ptr;
//   setter: exti_cb1_set(cb) @ 0x0800b8a2 (*ptr = cb)
//   dispatcher: exti_cb1_dispatch() @ 0x0800b830 -- checks an EXTI-pending-style flag via
//     FUN_0800a6de(DAT_0800b8dc,1), clears it via FUN_0800a6f6, then calls *exti_cb1_ptr if non-null
//   I: this is a single-slot EXTI (or similar level-interrupt) callback registration/dispatch
//   pair, structurally confirmed; WHICH EXTI line/peripheral triggers it is U (not traced).

// 0x200000b0  void* exti_cb_table[4];
//   setter: exti_cb_table_set(index 0..3, cb) @ 0x0800ba14
//   dispatcher: exti_cb_table_dispatch() @ 0x0800b8f2 -- tests 4 distinct pending-flag values
//     (FUN_0800a6de(0x40000000,{1,4,8,0x10})), clears whichever fired, calls the matching slot
//   I: a 4-way EXTI/pending-flag callback table, same family as exti_cb1_ptr but 4 slots;
//   U which 4 physical lines map to indices 0..3.

// 0x200000c0  void* exti_cb2_ptr;
//   setter: exti_cb2_set(cb) @ 0x0800bac8 (*ptr = cb)
//   U: no dispatcher for this exact slot was identified this pass (the candidate caller at
//   0x0800ba6a is not a function boundary Ghidra recognizes -- not chased further).

// 0x200000e4  byte assoc_table_init_flag;
//   read/set inside assoc_table_lookup_or_insert() @ 0x0800c440: a generic 20-slot x 6-byte
//   {key_byte, uint32 value, status_byte} association table, lazily zero-initialized on first
//   call via this flag. I: a generic keyed cache/registry (DJI-style generic helper, same
//   "index-driven generic driver layer" pattern air-router-io-and-naming.md already flagged for
//   the GPIO-port->RCC-bit mapper). U: the table's own base address and what keys/callers use it
//   (not traced -- callers of assoc_table_lookup_or_insert were not enumerated this pass).

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
