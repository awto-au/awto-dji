# Naming map — modules and buses

**Adopted 2026-10-25.** The canonical names for every module and bus, so a bare `m####` or a bus is
self-describing. Use these alongside the `m####` code in docs and in script variables; roll-out
across the existing docs is tracked in issue #54.

**Convention.**
- **Modules carry the chip:** `<side>_<role>_<chip>` — e.g. `air_fc_stm32f427`, `air_router_stm32f103`.
- **Buses use the short role token only:** `<medium>_<side>_<roleA>_<roleB>` — the chip stays in the
  module row so bus names stay short, and `side` disambiguates tokens shared across sides (e.g. the
  two `fx2`s / `fpga`s). So the bus is `uart_air_router_fc`, not `uart_air_stm32f103_stm32f427`.
- `air_` = aircraft, `gnd_` = RC. Role tokens: `cam fc fcldr gimbal venc vdec router rc fx2 fx3 fpga
  ad9363`. Tags: **V** verified in code/strings, **I** inferred, **U** unknown.

## Modules (`m####` → proposed name)

Each row is a distinct processor, **except `air_fcldr` (m0305)** — a loadable RAM payload for the
FC's STM32F427, not its own chip (see its row).

| m-code | DJI tag | Proposed `side_role_chip` | Chip / role | Side |
|---|---|---|---|---|
| `m0100` | FC300X / CAMLDR | `air_cam_a9se` | Ambarella A9SE camera SoC (ThreadX + Linux) | air |
| `m0306` | — | `air_fc_stm32f427` | Flight controller (µC/OS-III) | air |
| `m0305` | — | `air_fcldr_stm32f427` | **Loadable** 2nd-stage flash-loader *image* for `air_fc` (same STM32F427) — not a distinct chip. Runs from SRAM only during an update; downloaded by the FC resident loader, then erase/program + OPTKEYR option-bytes + A/B boot-decision, image in via DUML-over-CAN (decompiled, V; `fc-bootloader.md`) | air |
| `m0400` | GIMBAL0 | `air_gimbal` | Gimbal controller (STM32F4x5/x7 1 MB 168 MHz, exact part **U**; `m0400-naming-pass.md`) | air |
| `m0800` | DM368 | `air_venc_dm368` | DaVinci DM368 H.264 encoder (Linux) | air |
| `m0900` | MCA1765 | `air_router_stm32f103` | Lightbridge air MCU — **the air-side DUML router / gateway** (walks a dispatch table, forwards by receiver type; `dataflow.md` §3) | air |
| `m1300` | DM365 | `gnd_vdec_dm365` | DaVinci DM365 decoder — GL300a/HDMI RC only | gnd |
| `m1400` | MCG1765A | `gnd_rc_lpc1765` | RC main MCU: sticks, GPS, pairing/master-id, battery, RF-module + ground FPGA bridge (Lightbridge ground MCU) | gnd |
| `m1500` | — | `air_fx2_cy68013` | Cypress FX2LP (CY7C68013A) USB↔FIFO bridge (on the DM368) | air |
| `m1600` | — | `gnd_fx2_cy68013` | Ground FX2LP (CY7C68013A) receiver USB fw — GL300a/HDMI RC | gnd |
| `m1601` | — | `gnd_fx3_cyusb2014` | Cypress FX3 (CYUSB2014) phone USB — GL300b/c (owner's GL300C) | gnd |
| `m1900` | FPGAA | `air_fpga_cyclonev` | Air FPGA (Cyclone V e50f; device-type 19 "FPGA Air") | air |
| `m2000` | FPGAG | `gnd_fpga_cyclonev_r0` | Ground FPGA rev00 (device-type 20 "FPGA Ground") | gnd |
| `m2001` | — | `gnd_fpga_cyc4gx_r1` | Ground FPGA rev01 (Cyclone IV GX-format) | gnd |
| `m2002` | — | `gnd_fpga_cyclonev_r2` | Ground FPGA rev02 | gnd |

Notes: `m1300`/`m1600` exist only on the GL300a/HDMI RC; the owner's **GL300C** uses `m1601`
(`gnd_fx3_cyusb2014`) and drops the DM365 (`ground-fx3-m1601.md`). Air/ground FPGA split is V from the DUML
device-type enum (19/20), the module tags (FPGAA/FPGAG) and DJI's own in-firmware `FPGA.A`/`FPGA.G`
name table in `m0100` (`fpga-air-vs-ground.md` R1); which of `m2000/01/02` sits on which RC board
revision is still open (`fpga-air-vs-ground.md`).

## Buses (proposed name → endpoints / medium)

Two-ended buses: `<medium>_<side>_<roleA>_<roleB>` (role tokens, not chips). Rates/addresses in the cited docs.

### Aircraft-internal
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `uart_air_router_fc` | `air_router_stm32f103` ↔ `air_fc_stm32f427` | USART1, 256000 8N1 DMA (`dataflow.md`) | V route, FC end I |
| `uart_air_router_fpga` | `air_router_stm32f103` ↔ `air_fpga_cyclonev` | USART3, 257143 8N1 DMA, IDLE-framed | V; faces FPGA I |
| `uart_air_router_aux` | `air_router_stm32f103` ↔ ? | USART2, 250000 (board code 7 only) | V; peer U |
| `spi_air_router_fpga` | `air_router_stm32f103` ↔ `air_fpga_cyclonev` | SPI2, 4.5 MHz mode 1, 3-byte frames (+AD9363 relayed) | V |
| `can_air_primary` | `air_fc_stm32f427` ↔ `air_router_stm32f103` ↔ `air_gimbal` ↔ `air_cam_a9se` ↔ center/ESC | CAN, std IDs 0x412/0x413 (cam/gimbal), 0x414/0x415 (rx type 30); FC CAN1 PD0/PD1 AF9 | V IDs; some nodes I |
| `can_air_fc2` | `air_fc_stm32f427` ↔ ? | FC CAN2, PB12/PB13 AF9 — second bus, role unclear | V bus, role U |
| `iq_air_fpga_ad9363` | `air_fpga_cyclonev` ↔ air AD9363 | ~12-bit I/Q sample port, ~11.2 MHz | I |
| `usb_air_venc_fx2` | `air_venc_dm368` ↔ `air_fx2_cy68013` | USB bulk EP2, raw H.264 (`m0800-dm368-provenance.md`) | V |
| `fifo_air_fx2_fpga` | `air_fx2_cy68013` ↔ `air_fpga_cyclonev` | 8-bit slave FIFO, AUTO | V config; peer=FPGA I |
| `usb_air_cam_fx2` | `air_cam_a9se` ↔ `air_fx2_cy68013` | USB (switched; control + FX2 fw-load) | V |
| `vid_air_cam_venc` | `air_cam_a9se` ↔ `air_venc_dm368` | camera→encoder H.264 path | U medium |
| `eth_air_cam` | `air_cam_a9se` (GMAC) | Ethernet/GMAC, board_info/random MAC (not chip-locked) | V present; peer U |

### RC-internal (GL300C)
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `uart_gnd_rc_fx3` | `gnd_rc_lpc1765` ↔ `gnd_fx3_cyusb2014` | UART, 115200 8N1 DUML (`ground-fx3-m1601.md`); m1400 end is UART3 by baud match (`control-plane-re.md`) — UART2 ruled out (256000, wrong baud), not yet pin-level confirmed | V FX3 end; m1400-side UART3 I by baud, pins U |
| `spi_gnd_rc_fpga` | `gnd_rc_lpc1765` ↔ gnd FPGA | SPI0 @0x40020000, CS P2.9, 4 MHz, 3-byte `[0E reg val]`/`[0F reg FF]` frames, polled (no SPI IRQ, burst primitives unused). Carries: Master-ID (regs 3-7, `id-entry-point.md`); the **ground→air uplink record** (56 B to regs `0x44..0x7B` per frame: one 23-byte DUML chunk + sticks + ID, `control-plane-re.md` "SPI0 ↔ FPGA"); status readback `0xC0..0xEF`; and the **AD9363 bridge** (reg `0x01`=01 brackets each radio frame; boot script + run-time atten/band writes, then engine mode `0x01`=02). **No air→ground DUML on this link** (V) | V |
| `gpio_gnd_rc_fpga_sync` | gnd FPGA → `gnd_rc_lpc1765` | P2.3 falling edge, EINT3/GPIO IRQ 21 → TIMER1 one-shot: +1.4 ms status read, +8.3 ms config, +12.5 ms uplink record + hop words (times assume 72 MHz CCLK) — the frame-sync the MCU's radio schedule hangs off | V code; FPGA pad U |
| `spi_gnd_rc_rfm` | `gnd_rc_lpc1765` ↔ second RF module ("RFM") | bit-banged 4-wire SPI on GPIO0: P0.6 CS, P0.7 SCK, P0.8 MISO, P0.9 MOSI, ~0.35-1 MHz; `55 len ~len .. CRC-8(0xAA)` records; port-1 transport in RC-to-RC slave mode; strings `5.8G_VER_ERR`, `RFM_CRC_ERR` | V code; chip U |
| `uart_gnd_rc_unknown2` | `gnd_rc_lpc1765` ↔ ? | UART2, 256000 8N1 — live both ways: a DUML RX source (poller `FUN_000104ca`) and the port-1 uplink transport in transport mode `0x0b` (40-byte chunks). Peer U: `m1300` doubtful (likely unpopulated on this variant, `ground-fx3-m1601.md`; its own baud unchecked, image `Salted__`-encrypted); the ground FPGA is a candidate only if a 256000 UART exists on an untagged pad (pluribus #177) | V config+use; peer U |
| `gpio_gnd_rc_fpga` | `gnd_rc_lpc1765` ↔ gnd FPGA | config/reset/handshake strobes | V |
| `gpif_gnd_fpga_fx3` | gnd FPGA ↔ `gnd_fx3_cyusb2014` | 8-bit GPIF, PIB socket 2 — video | V |
| `usb_gnd_fx3_phone` | `gnd_fx3_cyusb2014` ↔ phone | USB; `55 CC` chunks (0x5749 DUML, 0x574A video) | V |
| `iq_gnd_fpga_ad9363` | gnd FPGA ↔ ground AD9363 | ~12-bit I/Q sample port | I |

### Shared RF
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `rf_air_gnd` | air AD9363/FPGA ↔ ground AD9363/FPGA | 2.4 GHz OFDM link, ~39 ch; over-the-air encryption not ruled out | I |

Full edge-by-edge evidence and rates: `dataflow.md`, `data/m0900-buses.tsv`, `m0900-can-channels.md`,
`ground-fx3-m1601.md`, `fc-io-inventory.md`, `id-entry-point.md`.
