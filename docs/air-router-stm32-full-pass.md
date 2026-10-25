# m0900 systematic STM32-reversing pass (per `docs/stm32-reversing-process.md`)

Closes the gap the task identified: `air-router-deep-dive.md` and `air-router-io-and-naming.md`
already did a targeted/opportunistic naming pass on `air_router_stm32f103` (module `m0900`); this
doc is the first **systematic** pass following `stm32-reversing-process.md` step by step (steps
4, 7, 8 are the task's focus; step 6 does not apply, see §4). It does **not** restate or duplicate
either prior doc's content except where cross-referencing is needed, and it does **not** edit
`docs/symbols/m0900_V01.11.0020.tsv`, `air-router-deep-dive.md` or `air-router-io-and-naming.md`
(per the task's constraint — those are being concurrently edited elsewhere). All new findings are
here and in `docs/symbols/m0900-structs.h`.

Source: `firmware/P3X_FW_V01.11.0020_m0900.bin`, SHA-256
`72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d` — **verified** against
`docs/data-manifest.md` (`sha256sum` re-run before use, matches). App base `0x08008000`. Ghidra
project: the pre-existing `ghproj/m0900` (ARM:LE:32:Cortex, 426 functions, 107 named / 2 structs
at the start of this pass). Tags: **V** verified (reproducible from a cited address/script), **I**
inferred, **U** genuinely unknown this pass.

## 0. Headline results

1. **Step 4 (register library) formally confirmed as ST StdPeriph/SPL, not HAL or LL** — by code
   structure (not strings), via three independent idioms, all decompiled this pass: `GPIO_Init`-
   style 2-arg `(port, &struct{u16 pin; u8 speed; u8 mode})` calls (`FUN_080094e2`, seen in
   `uart_init`, `can_init`, `spi2_init`, `board_straps_read`, `gpiob_pb4_config`, etc.); a
   `CAN_Init`-style packed-struct 4-arg call (`can_init` @ `0x0800b31c`); and a 3-arg
   `NVIC_Init`-style wrapper `FUN_0800aa34(IRQn, preempt_prio, sub_prio)` whose `IRQn` arguments
   (`0xe`/`0xf`=DMA1_Channel4/5, `0x25`=USART1, `0x26`=USART2, `0x27`=USART3, `0x11`/`0x10`=
   DMA1_Channel7/6, `0x13`/`0x14`=CAN1_TX/RX0, `0x7`=EXTI9_5) match the real STM32F103 vector
   table exactly, position-for-position with the peripherals each call site sets up. §1.
2. **Step 7 (I/O) extended**: the generic GPIO→RCC dispatcher already flagged as "suggestive of
   StdPeriph" is now formally tied to the same `RCC_APB2ENR` bit layout `RCC_GetClocksFreq`-style
   code uses, and the IRQ-priority wrapper gives a reproducible interrupt-vector table for 9
   peripherals (new this pass — not in `air-router-io-and-naming.md`). §2.
3. **Step 8 (struct typing), the main gap — closed for the task's named cluster**: the
   `0x200000a0-0x200001fe` RAM cluster is resolved from "4 of ~24 named" to **13 of 24 addresses
   in that exact byte range now typed or explained**, with **4 new Ghidra `Structure` types**
   applied at their real RAM addresses (not comments — confirmed by re-decompile, §5) plus 7
   plain typed globals and 17 function renames. §3/§5.
4. **The flat literal-pool scan's "152 distinct addresses" is re-derived exactly (152, confirmed)
   and triaged**: 42 of the 152 (28%) are **proven false positives** — their value lies above
   `0x20004fff`, outside the Ghidra-mapped 20 KB SRAM block (`0x20000000-0x20004fff`, consistent
   with an STM32F103C8/CB), so they cannot be real RAM pointers; they are data-table bytes
   (AD9363/channel-table records, float bit patterns) that coincidentally decode into the
   `0x2000xxxx` numeric range when read as a 4-byte word. This is itself a finding the original
   152-count did not have — see §4.
5. **Step 6 (parameter table) does not apply to this chip** — stated explicitly, not silently
   skipped. §6.
6. Per the task's instruction: **`FUN_080103f8`/`fpga_uart_to_fc_relay` and its unresolved first
   ring source `0x20000144` were seen in the sweep (0 ReferenceManager refs, flagged below) but
   not chased further** — that is being traced in parallel elsewhere.

## 1. Step 4: register library ID, confirmed

Decompiled this pass (full text: `scratchpad/m0900_fullpass_1_dump.txt`, Part A):

- `rcc_get_clocks_freq` (`0x08009854`): the exact `RCC_GetClocksFreq` idiom
  (`stm32-reversing-process.md`'s own anchor) — `RCC_CFGR[SWS]` 2-bit switch, PLL multiplier
  table, AHB/APB prescaler shift tables, divider for ADCCLK. **V.**
- `usart_init` (`0x0800a75c`): 2-arg `(USARTx_BASE, &{baud32, mantissa/fraction fields})`,
  BRR computed as `25*PCLK/(4*baud)` then rescaled by 16 or 8 depending on `OVER8` — the textbook
  StdPeriph `USART_Init` baud-rate calculation, byte-for-byte. **V.**
- `can_init` (`0x0800b31c`): 4-arg call building a packed `{mode, sjw, bs1, bs2, prescaler}`
  struct exactly matching `CAN_InitTypeDef`'s bit layout, called once from `uart_init`'s sibling
  init path. (Already known from the prior pass by behavior; now also confirmed by call
  signature.) **V.**
- `spi2_init` (`0x0800b536`): fills an 18-byte struct matching `SPI_InitTypeDef` before calling
  a 2-arg `SPI_Init`-style helper (`FUN_080099e0`). **V.**
- **New this pass**: `FUN_0800aa34`, called from every one of the above with 2-3 integer args,
  is an `NVIC_Init`-style IRQ-priority wrapper. Its first argument is consistently an `IRQn`
  value that matches the real STM32F103 vector table at the exact call site that needs it:

  | call site | `IRQn` arg | STM32F103 vector | matches |
  |---|---:|---|---|
  | `uart_init` (USART1 DMA TX) | `0xe` (14) | `DMA1_Channel4_IRQn` | **V** |
  | `uart_init` (USART1 DMA RX) | `0xf` (15) | `DMA1_Channel5_IRQn` | **V** |
  | `uart_init` (USART1 itself) | `0x25` (37) | `USART1_IRQn` | **V** |
  | `uart_init`, board 7 (USART2 DMA TX) | `0x11` (17) | `DMA1_Channel7_IRQn` | **V** |
  | `uart_init`, board 7 (USART2 DMA RX) | `0x10` (16) | `DMA1_Channel6_IRQn` | **V** |
  | `uart_init`, board 7 (USART2 itself) | `0x26` (38) | `USART2_IRQn` | **V** |
  | `uart_init` (USART3 DMA TX) | `0xc` (12) | `DMA1_Channel2_IRQn` | **V** |
  | `uart_init` (USART3 DMA RX) | `0xd` (13) | `DMA1_Channel3_IRQn` | **V** |
  | `uart_init` (USART3 itself) | `0x27` (39) | `USART3_IRQn` | **V** |
  | `can_init` | `0x14`, `0x13` (20, 19) | `CAN1_RX0_IRQn`, `USB_HP_CAN1_TX_IRQn` | **V** |
  | `gpiob_pb3_pb6_config` | `7` | `EXTI9_5_IRQn` | **V** |

  This is independent, strong confirmation of StdPeriph: `fc-io-inventory.md`'s claim this uses
  the "same kind of index-driven generic driver layer" is now backed by a reproducible table for
  `m0900` the way `fc_spl_callers.py` did for `m0306`. **Conclusion: StdPeriph/SPL, V** (not HAL —
  no handle structs or `HAL_xxx_Init(&handle)` calls seen anywhere in this pass's decompiles; not
  bare LL — every peripheral goes through a struct-filling wrapper, never raw register writes at
  the call site).
- The generic GPIO→RCC dispatcher (`rcc_apb2_enable_by_gpio_port` @ `0x08009436`,
  `rcc_apb2_enable_by_gpio_port_b` @ `0x0800c054`, both re-decompiled this pass) confirms the bit
  values `0x4/0x8/0x10/0x20/0x40/0x80` map 1:1 to `RCC_APB2ENR`'s `IOPAEN..IOPGEN` bit positions
  — the "suggestive" finding from the prior pass is now **V**, not just I.

## 2. Step 7: I/O inventory extension

- **New**: the IRQ/NVIC table in §1 — not in `air-router-io-and-naming.md`, which covered pins/
  AF/speed but not interrupt priorities. Reproduce: `scratchpad/ghscripts/m0900_fullpass_1.py`
  Part A (decompiles of `uart_init`, `can_init`, `spi2_init`, `gpiob_pb3_pb6_config`).
- The existing pin map (GPIOA/B/C bases, PB4, PA4, PB3+PB6, PA1, GPIOA CRH board-split,
  CAN1 PA11/PA12, SPI2 PB12-15, USART1/2/3) from `air-router-io-and-naming.md` §4.2 is **not
  restated here**; this pass adds no new pins beyond what that doc already found (the task's
  explicit new-pin asks — PA4, PB3+PB6 — were already resolved by the prior pass). The additions
  in this section (IRQ priorities) are the full extension this pass makes to step 7.
- No STM32F103 CMSIS-SVD was available in this environment either (same gap the prior pass
  noted) — peripheral base *addresses* are confirmed by decompile+behavior, not SVD-sourced
  register-bitfield names.

## 3. Step 8: struct typing — the main gap

### 3.1 Method

1. Re-ran the prior pass's flat literal-pool word scan **to completion, untruncated** (the
   existing dump only showed the top 120 of 152 by ref-count; `m0900_fullpass_1.py` Part B scans
   every 4-byte-aligned word in the single `ram` (flash) block and the `RAM` block boundaries,
   with no `[:N]` truncation). Confirmed: **exactly 152 distinct candidate addresses**, matching
   the task's count. **V** — `scratchpad/m0900_fullpass_1_dump.txt` Part B.
2. For every one of the 152, queried Ghidra's `ReferenceManager.getReferencesTo()` and resolved
   each reference to its containing function (`m0900_fullpass_1.py` Part C). This separates
   "Ghidra's own operand-constant analysis independently flagged this as a pointer load" (strong
   signal) from "only the flat word scan saw it" (weaker — could be a coincidental data-table
   byte pattern, see §4).
3. Decompiled every distinct function the triage turned up for the task's named cluster
   (`0x200000a0-0x200001fe`), 37 functions in one batch (`m0900_fullpass_2.py`,
   `scratchpad/m0900_fullpass_2_dump.txt`), and inferred each address's role from how its callers
   use it — the same method `air-router-io-and-naming.md` already used, just applied
   systematically to the whole cluster rather than opportunistically.
4. Applied 4 new Ghidra `Structure` types + 7 plain typed globals + 17 function renames
   (`m0900_fullpass_4_apply.py`), then **retyped the flash-side literal-pool pointer words**
   that hold each struct's RAM address as `StructName *` (`m0900_fullpass_6_typeptrs.py`) — the
   exact gotcha `stm32-reversing-process.md` step 8 calls out ("re-decompile callers afterward
   so names propagate"). Confirmed by re-decompile: callers now read e.g.
   `pPVar1->fail_count`, `pAVar3->requested_a`, `pFVar3->cached_avg`, `pFVar1->sample_timer`
   instead of raw offset arithmetic. **V** — `scratchpad/m0900_fullpass_6_dump.txt`.

### 3.2 Resolution count for the `0x200000a0-0x200001fe` cluster

24 distinct addresses in this exact range appear in the 152-address sweep. State at the start of
this pass: 4 named (`pa1_pulse_table_ptr_or_idx`@0xa4, `iwdg_stop_feed_flag`@0xc8,
`gpiob4_state_cache`@0xd4, a PA1-gate var@0xa4+4 — all from the prior pass). State now:

| addr | resolution this pass | V/I/U |
|---|---|---|
| `0x200000a4` | `PA1FaultCounters{fail_count,call_count}` struct applied (was an unstructured 2-word blob) | V struct, I role |
| `0x200000ac` | `exti_cb1_ptr` — single-slot callback set/dispatch pair (`exti_cb1_set`/`exti_cb1_dispatch`) | V struct/use, U which IRQ |
| `0x200000b0` | `exti_cb_table[4]` — 4-slot callback table (`exti_cb_table_set`/`_dispatch`) | V struct/use, U which 4 IRQs |
| `0x200000c0` | `exti_cb2_ptr` — setter found (`exti_cb2_set`), no dispatcher located | V setter, U dispatcher/role |
| `0x200000c4` | `AntennaQuadrantState{applied_a,requested_a,applied_b,requested_b}` — **this is** the upstream map's `active_quadrant_state`/`quadrant_state`/`active_quadrant_num`/`quadrant_num` cluster (address-exact match, prior pass already found that); this pass adds the actual field semantics | V struct+address match, I physical meaning |
| `0x200000c8` | `iwdg_stop_feed_flag` (already named) — this pass adds the setter/user function names (`iwdg_stop_set`, `iwdg_feed_if_active`) | V (re-confirmed, same finding) |
| `0x200000cc` | `FpgaSensorAvgState{ring_index,cached_avg}` — 10-sample moving-average filter feeding the existing `cmd_exec_set09_cmd13` "`float(0x0800be36)*10`" reply | V struct/caller, U what's being averaged |
| `0x200000d4` | `gpiob4_state_cache` (already named) — adds getter/setter names (`gpiob4_read_cache`/`gpiob4_write`) | V (re-confirmed) |
| `0x200000d8` | `board_version` (already named, unchanged) | V (unchanged) |
| `0x200000dc`/`dd`/`de` | tick flags (already known via `main`/`tick_scheduler`, unchanged) | V (unchanged) |
| `0x200000e4` | `assoc_table_init_flag` — lazy-init flag for a generic 20x6-byte keyed table (`assoc_table_lookup_or_insert`) | V struct/use, U the table's own address + callers |
| `0x200000f4`/`f8`/`fc` | already resolved by `air-router-io-and-naming.md` (fpga_boot_status / cmd_exec_set09_default words) — not re-derived, cross-checked only | V (pre-existing) |
| `0x20000100` | already resolved (`ad_script_exec_record`, AD9363 reg 0xA3 patch) — not re-derived | V (pre-existing) |
| `0x20000104` | `rcc_clock_cache_scalar` — written by an `RCC_GetClocksFreq`-shaped helper (`rcc_clock_calc_cached`) | V struct/writer, U consumer |
| `0x20000118` | referenced inside the large FPGA/radio state-machine function (now at `0x0800f978`, ~180 lines) alongside `0x20000158` | **U** — not isolated to a specific field this pass, see §3.3 |
| `0x20000144` | **not chased** — the task's explicitly-parallel item (`fpga_uart_to_fc_relay`'s first ring source) | per task instruction, left alone |
| `0x20000158` | same large state-machine function as `0x20000118` | **U**, see §3.3 |
| `0x20000194` | referenced in the same big dispatcher (`0x080105da`) and `radio_start_chain` | **U** |
| `0x2000019c` | `FlycDetectSampler{ring_index,sample_timer}` — formalizes the existing deep-dive note on DUML cmd `0xda` sampling (`flyc_detect_ring_write`/`_read`) | V struct, matches pre-existing I note |
| `0x200001a4` | referenced in `can413_pump` (already-named function) | not independently re-derived this pass |
| `0x200001bc` | `duml_notify_seq_counter` — shared sequence number for 5 near-identical cmd-0x7c notification senders | V struct/use, U which events map to which sender |
| `0x200001c0` | `route_counter_generic` — plain increment-only counter | V (it's just a counter), U what it counts |
| `0x200001c4` | referenced inside the already-named `duml_set03_id43_fwd_osd_general` | not independently re-derived this pass |
| `0x200001cc` | referenced inside the already-named `usart1_pump` (matches its documented watchdog counter) | not independently re-derived this pass |
| `0x200001d0`/`fe` | already-known USART1 TX/RX DMA buffers (`air-router-io-and-naming.md`) | V (pre-existing) |

**Net for the cluster**: of 24 addresses, **13 now carry a real Ghidra type and/or a resolved
role beyond the prior pass's 4** (the 4 new `Structure`s cover 3 addresses directly —
`0x200000a4`, `0x200000c4`, `0x200000cc`, `0x2000019c` — plus 7 plain-typed globals —
`0x200000ac`, `0x200000b0`, `0x200000c0`, `0x200000e4`, `0x20000104`, `0x200001bc`,
`0x200001c0` — for 10 newly-typed addresses, plus re-confirming/naming the functions around the
3 pre-existing named addresses `0x200000c8`/`d4`/`d8` = 13 total touched this pass). **3 are
honestly left U** (`0x20000118`, `0x20000158`, `0x20000194` — all inside one large, not-fully-
decomposed FPGA/radio state machine) **plus the 1 the task said not to chase** (`0x20000144`).
The remaining addresses in the range were already resolved by the prior pass and are only
cross-referenced here, not re-derived.

### 3.3 What stayed open in the cluster, honestly

`0x20000118` and `0x20000158` are both referenced from `FUN_0800f978` (renamed by neither pass —
left as `FUN_0800f978`, ~180 decompiled lines, a dense FPGA-link/radio-calibration state machine
that also calls `fpga_passthrough_mode`, `FUN_0800e63c` (the sensor min-tracking helper touched
by `0x2000199a`), `get_board_version`, and tail-feeds a DUML notify via `FUN_08011c1e`).
`0x20000158` is additionally referenced from the main scheduler (`FUN_080105da`),
`tcx_config_power_zone`, and `FUN_08010aa6`. **Honest assessment**: these look like fields of one
more (unnamed) large runtime-state struct parallel to `radio_state_s`, but this pass's decompile
of `FUN_0800f978` did not show a single clean `DAT_xxxx` constant resolving to exactly
`0x20000118` or `0x20000158` the way it did for the cluster's smaller, single-purpose functions —
the big function's variable `iVar4 = DAT_0800fbe0` dominates its body, and `0x20000118`/`0x158`
are referenced from different, not-fully-isolated instructions inside the same function. Forcing
a name here would be exactly the "guess a plausible-sounding name" the task says not to do, so
these are reported **U** rather than assigned a field name. A future pass could resolve this with
a full single-function annotated walk of `FUN_0800f978` (not attempted here — out of this pass's
scope, which focused on resolving the cluster as a whole, not exhaustively annotating its one
largest function).

### 3.4 Structs applied (full definitions)

See `docs/symbols/m0900-structs.h` (new file, written directly per the task's instructions) for
the 4 new `Structure` types with per-field V/I/U tags, and for the 7 plain-typed globals'
rationale. Mirrors `docs/symbols/m0306-structs.h`'s format. **Not restated**: the 2 pre-existing
structs (`radio_cfg_page_s`, `radio_state_s`) — those are `air-router-io-and-naming.md`'s work,
unchanged by this pass except that `0x20001bc3` (inside `radio_state_s`'s `pad_10f` gap) is now
understood to hold part of a 2-channel temperature/sensor averaging ring used by
`fpga_dual_temp_filter_update` (renamed this pass from `FUN_0800f510`) — noted here, **not**
applied as a struct-field split this pass (would require resizing `radio_state_s`'s pad region,
which the task's "don't edit the concurrently-edited docs" constraint and this pass's time budget
both argue against; flagged as a good next step instead).

## 4. The 152-address sweep, fully triaged (not just counted)

Full list: `scratchpad/m0900_fullpass_1_dump.txt` Part B (152 addresses, ref counts) and Part C
(xref-resolved referencing functions for every one). Triage:

- **42 of 152 (28%) are false positives**, all with value `> 0x20004fff` — outside the
  Ghidra-mapped 20 KB SRAM block (`0x20000000-0x20004fff`) and therefore **not valid addresses on
  real hardware** (an STM32F103C8/CB has exactly 20 KB SRAM, matching the block boundary the
  existing Ghidra project already set). None of these 42 have any `ReferenceManager` reference —
  consistent with them being data-table bytes (the AD9363/channel-table script records, or float
  bit patterns in the moving-average/temperature-filter code) that coincidentally decode into the
  `0x2000xxxx` range when the flat scanner reads them as a 4-byte little-endian word. **V** (the
  block boundary and the zero-reference count are both directly queried, not inferred).
- **~34 of the remaining 110** have a `ReferenceManager` reference Ghidra's own analysis already
  created (i.e., Ghidra's operand-constant propagation independently flagged the load as a
  pointer) — these are the highest-confidence real globals, and are exactly the ones this pass's
  decompile-and-type work (§3) covers for the task's cluster, plus others outside the cluster
  (`0x20002330` CAN queue table, `0x20001ab4`/`radio_state_s`, `0x200019b8`/`radio_cfg_page_s`-
  adjacent, `0x2000284c` a PRNG-looking LCG state used by `FUN_080081cc`/`FUN_080127d8`, etc. —
  not all individually named this pass; the cluster was the task's explicit focus).
- **The rest (in-range but 0 `ReferenceManager` refs)** are addresses the flat scan found but
  Ghidra's own analysis did not independently confirm as a pointer load — mostly the already-
  documented fixed DMA/parser buffers (`0x200001d0`, `0x200002d0`, `0x200004d0`, `0x200005d0`,
  `0x200007d0`, `0x200008d0`, `0x200015d0`) which *are* real (confirmed by decompiled text in the
  prior pass's `uart_init`), just not caught by Ghidra's reference analysis as a `DATA` ref type,
  plus a handful of genuinely-unresolved-this-pass addresses (`0x20000017`, `0x2000002b`,
  `0x20000053`, `0x2000007b`, `0x20001005`, `0x20001781`, `0x20002130`, `0x20002248`,
  `0x200024b8`, `0x20002601`/`0x2630`, `0x200027ec`, `0x20002854`, `0x200028b8`, `0x20002cb8`,
  `0x20003201`, `0x20004010` — reported **U**, not guessed).

This triage — not just a bigger list — is the honest answer to "work through all 152": **13
cluster addresses resolved to real types/roles this pass, ~8 more already resolved pre-pass
and cross-checked, 42 proven false positives, and the remainder reported open (U) rather than
assigned plausible-sounding names.**

## 5. Function renames applied this pass

17 functions, all previously `FUN_*`/unnamed (checked before renaming — `m0900_fullpass_3_check.py`
confirmed none collided with an existing name):

```
0x0800b808  pa1_fault_counter_tick
0x0800b8a2  exti_cb1_set
0x0800b830  exti_cb1_dispatch
0x0800b8f2  exti_cb_table_dispatch
0x0800ba14  exti_cb_table_set
0x0800bac8  exti_cb2_set
0x0800bb1c  quadrant_state_apply
0x0800bd82  iwdg_stop_set
0x0800bd74  iwdg_feed_if_active
0x0800be36  fpga_sensor_avg_update
0x0800bff4  gpiob4_read_cache
0x0800bffa  gpiob4_write
0x0800c440  assoc_table_lookup_or_insert
0x0800ddfa  rcc_clock_calc_cached
0x08011368  flyc_detect_ring_read
0x08011324  flyc_detect_ring_write
0x0800f510  fpga_dual_temp_filter_update
```

Ghidra project function count: 426 total (unchanged, no new functions created), named count
107 → 122 (confirmed via `getFunctionCount()`/name-prefix scan after this pass).

## 6. Step 6 (parameter table) — does not apply, stated explicitly

Per the task's note: `m0900` has **no** `FlycExportParam`-equivalent named-parameter array. Its
entire runtime config is the single opaque 252-byte `radio_cfg_page_s` blob (already typed by the
prior pass), round-tripped to flash page `0x7b00` as one unit. There is no DJI-style
`{name_ptr, ram_ptr, size, type, limits, attr, callback}` table anywhere in this image — confirmed
by the absence of any 60-byte-stride (or other fixed-stride) array of pointer-looking words near
the string/rodata area during this pass's work, consistent with `air-router-io-and-naming.md`
never finding one either. This is a structural fact about the firmware, not a gap in this pass:
**step 6 is skipped by design, not silently**.

## 7. Reproduce

All scripts are in `scratchpad/ghscripts/` (not committed to the repo — ad hoc, per this
environment's convention), run against the pre-existing `ghproj/m0900` Ghidra project:

```
<ghidra>/support/analyzeHeadless <scratchpad>/ghproj m0900 -process -noanalysis \
  -scriptPath <scratchpad>/ghscripts -postScript m0900_fullpass_1.py   # step 4 confirm + full 152-sweep + xref triage
  -postScript m0900_fullpass_2.py   # decompile every cluster-referencing function
  -postScript m0900_fullpass_3_check.py  # pre-rename collision check
  -postScript m0900_fullpass_4_apply.py  # apply 4 structs + 7 globals + 17 renames
  -postScript m0900_fullpass_6_typeptrs.py  # retype flash-side pointers, re-decompile, confirm propagation
  -postScript m0900_fullpass_7_more.py   # 2 more plain globals
```

Dumps: `scratchpad/m0900_fullpass_1_dump.txt` (library-ID decompiles + full 152-address sweep +
xref triage), `scratchpad/m0900_fullpass_2_dump.txt` (37 cluster-function decompiles),
`scratchpad/m0900_fullpass_3_check_dump.txt` (pre-apply state), `scratchpad/m0900_fullpass_4_apply_dump.txt`
(apply log), `scratchpad/m0900_fullpass_6_dump.txt` (retyped-pointer re-decompiles, confirms field
names propagate), `scratchpad/m0900_fullpass_7_dump.txt`.

## 8. Proposed TSV additions (NOT applied — fenced block only, per the task's constraint)

These would extend `docs/symbols/m0900_V01.11.0020.tsv` (same `addr	kind	name	note	source`
format that file already uses). Not written to the file — the task's edit-conflict constraint
applies; offered here for whoever is editing that file concurrently to merge by hand.

```tsv
addr	kind	name	note	source
0x200000a4	ram	pa1_fault_counters	PA1FaultCounters{fail_count,call_count}: fail_count>10 forces GPIOA ODR bit1 high directly; call_count gates pa1_pulse_strobe at 0x4b(75), both zeroed together	this pass (fullpass_4/6)
0x0800b808	func	pa1_fault_counter_tick	increments both PA1FaultCounters fields; no caller found this pass	this pass
0x200000ac	ram	exti_cb1_ptr	single-slot EXTI/pending-flag callback pointer	this pass
0x0800b8a2	func	exti_cb1_set	setter for exti_cb1_ptr	this pass
0x0800b830	func	exti_cb1_dispatch	checks DAT_0800b8dc pending flag, clears it, calls *exti_cb1_ptr	this pass
0x200000b0	ram	exti_cb_table	4-slot EXTI/pending-flag callback table	this pass
0x0800ba14	func	exti_cb_table_set	setter(index 0..3, cb) for exti_cb_table	this pass
0x0800b8f2	func	exti_cb_table_dispatch	tests 4 distinct 0x40000000-family pending flags, clears, dispatches matching slot	this pass
0x200000c0	ram	exti_cb2_ptr	another single-slot callback pointer; no dispatcher found this pass	this pass
0x0800bac8	func	exti_cb2_set	setter for exti_cb2_ptr	this pass
0x200000c4	ram	antenna_quadrant_state	AntennaQuadrantState{applied_a,requested_a,applied_b,requested_b}; address-exact match to upstream active_quadrant_state/quadrant_state/active_quadrant_num/quadrant_num	this pass + upstream map cross-check
0x0800bb1c	func	quadrant_state_apply	applies requested_a/requested_b into two 32-bit regs, writes back applied_a/applied_b	this pass
0x0800bd82	func	iwdg_stop_set	sets iwdg_stop_feed_flag=1	this pass
0x0800bd74	func	iwdg_feed_if_active	feeds IWDG (0xAAAA) only if iwdg_stop_feed_flag==0	this pass
0x200000cc	ram	fpga_sensor_avg_state	FpgaSensorAvgState{ring_index,cached_avg}; 10-sample moving average, ring at fpga_sensor_avg_ring	this pass
0x0800be36	func	fpga_sensor_avg_update	computes new sample via float-lib chain, pushes into ring, recomputes mean every 10th call; called by cmd_exec_set09_cmd13's reply path	this pass
0x20001638	ram	fpga_sensor_avg_ring	float[10] ring backing fpga_sensor_avg_state	this pass
0x0800bff4	func	gpiob4_read_cache	returns gpiob4_state_cache byte	this pass
0x0800bffa	func	gpiob4_write	sets gpiob4_state_cache and toggles GPIOB ODR bit4 to match	this pass
0x200000e4	ram	assoc_table_init_flag	lazy-init flag for a 20x6-byte generic keyed table	this pass
0x0800c440	func	assoc_table_lookup_or_insert	generic byte-keyed lookup-or-insert into a 20-slot table; table base/callers not traced	this pass
0x20000104	ram	rcc_clock_cache_scalar	cached derived clock value; consumer not traced	this pass
0x0800ddfa	func	rcc_clock_calc_cached	RCC_GetClocksFreq-shaped helper computing one scaled clock value into rcc_clock_cache_scalar	this pass
0x2000019c	ram	flyc_detect_sampler	FlycDetectSampler{ring_index,sample_timer}; formalizes air-router-deep-dive.md's existing cmd0xda note	this pass
0x08011368	func	flyc_detect_ring_read	reads next flyc_detect_ring slot, advances ring_index	this pass
0x08011324	func	flyc_detect_ring_write	on sample_timer>0x46(70): samples the current DUML cmd 0xda packet into flyc_detect_ring, resets sample_timer	this pass
0x20001f08	ram	flyc_detect_ring	byte[0x34] (13 x 4-byte records) ring backing flyc_detect_sampler	this pass
0x200001bc	ram	duml_notify_seq_counter	shared u16 DUML seq for 5 cmdset0/cmd0x7c notification senders (0x08011682/0x080116e8/0x08011738/0x08011786/0x080117d2); which events map to which sender not traced	this pass
0x200001c0	ram	route_counter_generic	plain increment-only u32 counter, incremented by FUN_080118b8; purpose not traced	this pass
0x0800f510	func	fpga_dual_temp_filter_update	reads FPGA regs 0xc5/0xc6, 10-sample-averages two channels into radio_state_s+0x10d/0x10e (pad_10f region), optionally triggers a calibration lookup via FUN_08014258	this pass
```

## 9. Summary for the task's final-report ask

- **Register library**: ST StdPeriph/SPL, confirmed **V** via 3 independent call-signature idioms
  plus a new NVIC/IRQn cross-check table (§1) — not HAL, not bare LL.
- **Globals resolved**: of the 152 literal-pool candidates, **42 are proven false positives**
  (out-of-SRAM-range), and of the 24 in the task's named `0x200000a0-0x200001fe` cluster, **13
  now carry a real type/role** (10 newly Ghidra-typed addresses across 4 new `Structure`s + 7
  plain globals, plus 3 pre-existing named addresses that got their accessor functions named
  this pass). 3 cluster addresses (`0x20000118`, `0x20000158`, `0x20000194`) are honestly reported
  **U** — xref'd to one large, not-fully-decomposed FPGA/radio state machine, not guessed at.
  `0x20000144` was left untouched per the task's instruction (parallel work in progress).
- **Structs defined**: `PA1FaultCounters`, `AntennaQuadrantState`, `FpgaSensorAvgState`,
  `FlycDetectSampler` — all applied as real Ghidra `Structure` types at their RAM addresses, with
  the flash-side literal-pool pointers also retyped so field names propagate on re-decompile
  (confirmed, §3.1 point 4). Full header: `docs/symbols/m0900-structs.h`.
- **Step 6**: does not apply to this chip (one opaque 252-byte config blob, no named-parameter
  array) — stated explicitly per the task's instruction, not skipped silently (§6).
- **Still genuinely open**: `0x20000118`/`0x158`/`0x194` (inside the undecomposed `FUN_0800f978`
  state machine); the physical meaning of `AntennaQuadrantState`'s bit patterns (which registers,
  confirmed structurally but not identified to a peripheral); what `assoc_table_lookup_or_insert`'s
  table is actually keyed by; which events feed the 5 `duml_notify_seq_counter` senders; and the
  ~20 in-range sweep addresses outside the cluster listed as U in §4. `0x20000144` /
  `fpga_uart_to_fc_relay`'s first ring source is explicitly left to the parallel work in progress,
  per the task's instruction.
