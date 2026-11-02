# Cross-module bus/port topology reconciliation

One reconciled table of every known physical bus/port and both its endpoints, built **from
already-documented per-module findings only** — no new facts invented. Where two modules
disagree or no documented match exists, marked "unreconciled," not guessed. Tags: **V**
verified in code (address cited), **I** inferred, **U** unknown, **W** wiki-sourced (not
independently checked). Method: `docs/re-rules.md`. Draws on #36 (m0900 CAN), #41 (m0400
CAN/UART), #61 (intel i6050 USB/PHY context).

**Already settled elsewhere — read first, not re-derived here:**

- **`docs/fpga-air-vs-ground.md`** already does the air/ground FPGA side-matching (DUML
  module-name table cross-match, receiver-type arithmetic `0x13`/`0x14`, xV4 container kind
  byte, package membership) for `m1900` (air) vs `m2000`/`m2001`/`m2002` (ground). This doc
  does **not** repeat that reconciliation — every row below that touches an FPGA image cites
  that doc instead of re-deriving the side.
- **`docs/board-connections.md`** already has the P01007.06 physical port inventory
  (CAMERA/CENTER connectors, SWD/JTAG/SPI/CAN/UART service pads) and its own "Connection
  table." The UART/SPI/CAN rows below cross-check against that table rather than re-guessing
  pin roles, and cite it rather than reprint it.
- Reconciliation table layout (claim / existing-module-A / existing-module-B / verdict /
  citation) follows the house convention already used in
  `fpga/m2001/docs/lightbridge-ofdm-reconciliation.md`'s "claim / existing / ours / verdict /
  behind ours" tables (that doc is PHY numerology, not ports — different subject, same
  layout, reused for consistency).

**Stale-input flag:** same as `docs/dji-shared-code.md`'s table — `m0306` is **mid-flight**
(uncommitted TSV/struct changes, new untracked TSVs) at read time; treat every m0306 CAN/bus
claim below as provisional. `m0400`/`m1400` TSVs are committed but their Ghidra project
directories show uncommitted changes in `git status` — lower risk, noted.

---

## 1. CAN bus

### 1.1 The headline reconciliation: does m0900's CAN 0x412/0x413 match m0400's?

| Claim | m0900 (`air_router_stm32f103`, #36) | m0400 (`air_gimbal`, #41) | Verdict | Citation |
|---|---|---|---|---|
| StdId `0x412` direction | **TX** — `route_path_a 0x0801141c` sends receiver types 1 (camera), 4 (gimbal), 8 (DM368), 15 to `can_enqueue_and_tx(0x20002330)`, boards 2/4/5/6 | **RX** — `can_rx_dispatch 0x080195b8` switches on std id incl. `0x412`, pushes payload into `can_rx_ring` | **Match — same physical wire, complementary directions** | `m0900-can-channels.md` §3; `m0400-naming-pass.md` §4 "CAN RX std ids" |
| StdId `0x413` direction | **RX** — exact-match filter bank 0, `can413_pump 0x0801148c` → `duml_dispatch` | **TX** — `duml_send_frame 0x08016d94` port 1 = "CAN 0x413"; also listed as `can_rx_ring`'s own `field id = 0x413` in the ringbuf struct (naming artifact, not a second RX) | **Match — same physical wire, complementary directions** | `m0900-can-channels.md` §3; `m0400-naming-pass.md` §3-4 |
| Framing | `0x55` sync, CRC8 seed `0x77`, CRC16 seed `0x3692`, same parser class as every other m0900 port | `0x55` sync, CRC8/CRC16 same seeds, `duml_assemble_can` 5-state machine | **Match** — DUML, not a second protocol, on both ends | `m0900-can-channels.md` §4; `m0400-naming-pass.md` §3; also `docs/dji-shared-code.md` §1.1 (table-byte match) |

**Answer: yes — m0900 is the `0x412`-TX/`0x413`-RX node and m0400 is the `0x412`-RX/`0x413`-TX
node of the *same* physical CAN1 bus.** This was independently traced twice (two separate RE
passes, #36 and #41, neither reading the other's conclusion at trace time) and the directions
land exactly complementary — the strongest kind of cross-check this repo can produce without
a hardware capture. This **resolves** `dataflow.md` §7.11 Q1's closing paragraph, which only
had m0900's own trace and could say "CAN1 0x412/0x413 is the CAMERA/GIMBAL/DM368/TRANSFORM
relay... this reopens who's on the other end" — m0400 (the gimbal) is now a *confirmed* peer
on that bus (not just a device-type label match), not the only one: types 1/8/15 (camera,
DM368, "TRANSFORM") still need their own peer's independent CAN trace to close fully, same as
noted in `m0900-can-channels.md` §6.

### 1.2 m0400's extra CAN ids — not a contradiction, a filter-list mismatch

`dataflow.md` §7.11 "New data point" flagged m0400's registered StdId `0x321` as **not** in
m0900's set `{0x412,0x413,0x414,0x415}` and left it as "Open (U) — either separate physical
buses, or one side has an undiscovered additional endpoint."

Resolved by re-reading `m0400-naming-pass.md`'s own detail: m0400's full CAN id set is wider
than previously cited — **RX** `0x101`, `0x200-0x205`, `0x2f0-0x2f6`, `0x412`; **TX** `0x20b`,
`0x20d`, `0x23d`, `0x321` (**staging default only** — `can_tx_stage`/`can_tx_msg_s` is the
shared CAN-mailbox staging struct, and `0x321` is the value `can1_init` loads into it at
boot, before any real send overwrites it — not necessarily a value that ever reaches the
wire as live traffic), `0x413`.

**This is fully consistent with one shared physical bus, not evidence of two buses:** a
bxCAN hardware filter (m0900's `CAN_FilterInit`, exact-match on `0x413`/`0x415` only) silently
drops any frame whose StdId doesn't match — m0900 would never see or report `0x321`,
`0x101`, `0x200-0x205`, or `0x2f0-0x2f6` even if they ride the identical physical bus as
`0x412`/`0x413`, because it never asks for them. **Not reconciled further: whether
`0x101`/`0x200-0x205`/`0x2f0-0x2f6` are on the *same* wire as `0x412`/`0x413` or a second,
gimbal-only CAN segment is still genuinely U** — nothing in either module's own trace
distinguishes "same bus, unfiltered" from "separate bus." The `0x412`/`0x413` pair itself
(§1.1) is V; the rest of m0400's CAN traffic's physical bus identity is U, not contradicted.

### 1.3 Other modules' CAN — unreconciled (U), each for a different, already-documented reason

| Module | CAN hardware | Arbitration IDs found | Why unresolved | Citation |
|---|---|---|---|---|
| `m0306` (flight controller) | CAN1 (`0x40006400`) **and** CAN2 (`0x40006800`), both genuinely initialised (own GPIO AF9 config, own RCC gate, own BTR write) | **None** — IDs are read from an external data-struct pointer (`DAT_08035534`), not instruction immediates, so the literal-scan method that closed m0900's set structurally cannot find them | Data-driven, not code-driven; table not located this pass or any prior one | `dataflow.md` §7.10, Q2 "`m0306`: NOT closed — different reason" |
| `m1400` (ground RC MCU) | CAN1 (10 base-literal hits) + CAN2 (3 base-literal hits); `port_send` routes types `0x19`/`0x1C` to port 5 = CAN1/CAN2 | **None confirmed** — a 2-byte sub-header (`0x0203`/`0x0403`) was found prepended to some CAN-queue payloads, type/length-tag-shaped, but not confirmed as the actual 11-bit arbitration ID | Byte-push call sites traced (`FUN_0001bc08`), but the mailbox TID-equivalent pointers didn't resolve to a clean literal | `dataflow.md` §7.11 Q2 "`m1400`: NOT closed" |

**Net honest answer for Goal 2's CAN question:** 4 StdIds are system-wide confirmed
(`0x412`/`0x413`/`0x414`/`0x415`, all on `m0900`'s CAN1), and **two of those four
(`0x412`/`0x413`) are now cross-confirmed on `m0400`'s end too** (§1.1, new this pass).
`0x414`/`0x415` (receiver type 30 only) has **no confirmed peer anywhere** — not m0400, not
m0306 (data-driven, unknown IDs), not m1400 (unconfirmed IDs). `m0306` and `m1400` each have
at least one more live CAN node whose own ID(s) remain genuinely unknown, unchanged from
`dataflow.md`'s own prior "NOT closed" verdict for both.

---

## 2. UART / USART

| Claim | Module A | Module B | Verdict | Citation |
|---|---|---|---|---|
| CENTER connector = m0900 USART1, 256000 8N1 | `board-connections.md` "Connection table": `MCU on CENTER, USART1 (by routing), 256000 nominal (256228 actual), tag V rate+route, wiring I` | m0900 own trace: USART1 256000 8N1 DMA, FC/center-board link, receiver types 3/5/10/11/12/18/21/23 all boards | **Already settled, not re-derived here** | `board-connections.md` connection table row 4; `m0900-can-channels.md` §5 |
| m0900 USART3 = link to air FPGA, 257143 8N1 | `board-connections.md`: SPI2 to FPGA is V; no USART3-to-FPGA wiring row (open gap, item 1 in "What a real schematic would confirm") | m0900 own trace: USART3 257143 8N1 DMA, IDLE-framed, types 2/6/13/14/16/20/22 | **Unreconciled on the wiring, not the rate** — rate/framing is V on the m0900 side; which physical pads carry it to the FPGA is still open per `board-connections.md` itself | `board-connections.md` §"What a real schematic would confirm" item 1; `dataflow.md` §2 edge note |
| m0400's own DUML UARTs (USART2 tag0, UART4 tag2) at 115200 | m0400: `usart1_init/usart2_init/uart4_init (115200 from main)`; USART1 confirmed **not** a live DUML port despite being initialised | No m0900/m1400 bus runs 115200 **except** `uart_gnd_rc_fx3` (m1400↔FX3, ground side) and `m1400`'s UART0-3 internal set | **Not the same bus — different side, different peer.** m0400's 115200 UARTs are gimbal-internal (peer chip U, "USART1's intended peer" listed as still-open in m0400's own doc); no evidence connects them to m1400's 115200 FX3 link, which is ground-side only | `m0400-naming-pass.md` §3 and §6 "Not named/still U"; `naming-map.md` `uart_gnd_rc_fx3` row |
| m0900 USART2, 250000, board code 7 only | m0900 own trace: live only on board strap 7 | No cross-module match attempted/found | **Unreconciled** — board-code-gated, peer unknown on every pass that touched it | `m0900-can-channels.md` table; `dataflow.md` §1 |
| Ground FPGA → m1400 downlink DUML UART | m1400: UART0/1 (ring `0x10006740`) or UART2 (256000) listed as candidates, peer **not** SPI0 (that's confirmed uplink-only) | Ground FPGA side: no UART trace exists (FPGA bitstreams carry no RE-recoverable logic per `fpga-air-vs-ground.md`'s own negative-strings finding) | **Unreconciled, structurally** — the FPGA side of this link can never be independently traced from bitstream RE (`fpga-air-vs-ground.md`: "do not expect the bitstreams to say which side they are," same logic applies to internal routing) | `dataflow.md` §5 item 7; `naming-map.md` `uart_gnd_rc_unknown2` row |

---

## 3. SPI

| Claim | Endpoint A | Endpoint B | Verdict | Citation |
|---|---|---|---|---|
| m0900 SPI2 → air FPGA (+AD9363 relay) | SPI2, 4.5 MHz mode 1, 3-byte `[reg val]` frames, CS=PB12 | air FPGA, bridged to AD9363 | **V, already settled** — matches `board-connections.md`'s own connection table exactly (SPI2 row, same 4.5 MHz / mode 1 / 3-byte-frame numbers) | `naming-map.md` `spi_air_router_fpga`; `board-connections.md` connection table |
| m1400 SPI0 → ground FPGA (+AD9363 bridge) | SPI0 @ `0x40020000`, CS P2.9, 4 MHz, 3-byte frames, polled | ground FPGA, bridges AD9363 | **V, already settled, not re-derived** | `naming-map.md` `spi_gnd_rc_fpga` |
| m0900 SPI1 | unused (dead code, V by absence) | — | **Confirmed negative, cross-checked twice already** (`control-plane-re.md` "SPI1 resolved", issue #18) — no new work needed | `board-connections.md` connection table last row |
| m0306 (flight controller) SPI | **none referenced anywhere in the image** — "no SPI, no DMA, no ADC referenced anywhere in m0306" | n/a | **New cross-check this pass: the FC has no SPI bus at all**, unlike the radio (m0900) and gimbal (m0400, next row), which both have one | `dataflow.md` §7.10 "Full peripheral map" |
| m0400 SPI1 | IMU (MPU-family burst read, `imu_dma_buf`), with a 2-wire (`sw2w_*`) fallback bus on the same pins | on-board IMU chip only, not another MCU | **Not a cross-chip bus** — sensor-local, included here for completeness since it's the only other SPI user in the family besides the two radio links above | `m0400-naming-pass.md` §4 "`imu_out`/`imu_dma_buf`", §5 |

---

## 4. USB

| Claim | Endpoint A | Endpoint B | Verdict | Citation |
|---|---|---|---|---|
| Air FX2LP VID:PID | `m1500` (`air_fx2_cy68013`, CY7C68013A) | `cam_server`'s `fxload -t fx2 -d 0547:1002 -i /home/Vend_Ax.iic` (Linux side, loads the FX2's firmware) | **V, cross-confirmed this pass** — the Linux-side `fxload` target VID:PID (`0547:1002`) matches the air FX2LP chip identity already in `naming-map.md`; new corroboration, not a new fact | `naming-map.md` `air_fx2_cy68013`; `docs/camera-linux-reversing.md` §1a |
| Ground FX3 phone link | `m1601` (`gnd_fx3_cyusb2014`) | phone (iAP2/AOA), `55 CC` chunk header | **Already settled, not re-derived** | `naming-map.md` `usb_gnd_fx3_phone`; `ground-fx3-m1601.md` |
| m1400 own USB | **none — LPC1765 USB peripheral base (`0x50008000`) has zero literal hits, confirmed by two independent methods** (flat literal scan + Ghidra xref scan) | n/a | **Confirmed negative** — m1400 itself never touches USB; all USB on the RC side lives on the separate FX2/FX3 chip (`m1600`/`m1601`), not the MCU | `ground-upgrade-path.md` "SVD + peripheral-map corrections" table |
| USB mode-switch (A9 host/device role) ties into CAN/UART topology? | `/proc/ambarella/uport` (Linux-side A9 controller-role switch) + RTOS GPIO mux (A9 vs DM368 port ownership) | — | **Checked, negative** — neither switch touches CAN1 (`0x412`-`0x415`) or any UART in this doc; it's a USB-only mechanism between the A9 and DM368 sharing one physical USB port, orthogonal to the DUML CAN/UART buses | `docs/camera-linux-reversing.md` §6; cross-checked in `docs/dji-shared-code.md` §3.1 |

---

## 5. Unreconciled / contradicts — summary

- **m0306's CAN1/CAN2 arbitration IDs**: unknown, data-driven, not code-driven (§1.3).
- **m1400's CAN1/CAN2 arbitration IDs**: unknown, sub-header found but not confirmed as the
  real ID (§1.3).
- **`0x414`/`0x415` peer**: no module traced here owns it; "who is receiver type 30" remains
  fully open (§1.3, unchanged from `m0900-can-channels.md` §6).
- **m0400's wider CAN id set (`0x101`, `0x200-0x205`, `0x2f0-0x2f6`) vs m0900's filtered set**:
  explained as filter-list mismatch, not contradiction, but **which physical bus** carries
  them is still U (§1.2) — stated as open, not resolved.
- **m0900 USART3 ↔ air FPGA wiring**: rate/framing V, physical pad wiring still open per
  `board-connections.md`'s own gap list (§2).
- **Ground-FPGA-to-m1400 downlink UART**: structurally untraceable from the FPGA side with
  tools available in this repo (§2) — not a contradiction, a hard limit of bitstream RE
  already documented in `fpga-air-vs-ground.md`.

## Reproduce

All claims above are read from already-committed docs/TSVs, cited inline; no new script was
needed for this doc (the CRC byte-comparison script supporting the related shared-code doc
is `scripts/re/crc_table_crosscheck.py`, unrelated to bus topology).
