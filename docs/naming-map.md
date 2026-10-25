# Naming map — modules and buses (PROPOSAL, for review)

Short, side-prefixed names so a bare `m####` or a bus is self-describing. **Draft — review and
edit the names before we adopt them repo-wide** (that roll-out is tracked in a GitHub issue).
Convention: `air_` = aircraft, `gnd_` = remote controller. Tags: **V** verified in code/strings,
**I** inferred, **U** unknown.

## Modules (`m####` → proposed name)

| m-code | DJI tag | Proposed | Chip / role | Side |
|---|---|---|---|---|
| `m0100` | FC300X / CAMLDR | `air_cam_a9` | Ambarella A9SE camera SoC (ThreadX + Linux) | air |
| `m0306` | — | `air_fc` | Flight controller, STM32F427 (µC/OS-III) | air |
| `m0305` | — | `air_fc_updater` | RAM-resident flash updater for `air_fc` (A/B-capable) | air |
| `m0400` | GIMBAL0 | `air_gimbal` | Gimbal controller | air |
| `m0800` | DM368 | `air_video_enc` | DaVinci DM368 H.264 encoder (Linux) | air |
| `m0900` | MCA1765 | `air_lb_mcu` | Lightbridge air MCU, STM32F103 — DUML router | air |
| `m1300` | DM365 | `gnd_video_dec` | DaVinci DM365 decoder — GL300a/HDMI RC only | gnd |
| `m1400` | MCG1765A | `gnd_lb_mcu` | Lightbridge ground MCU, LPC1765 | gnd |
| `m1500` | — | `air_fx2` | Cypress FX2LP USB↔FIFO bridge (on the DM368) | air |
| `m1600` | — | `gnd_fx2` | Ground FX2LP receiver USB fw — GL300a/HDMI RC | gnd |
| `m1601` | — | `gnd_fx3` | Cypress FX3 phone USB — GL300b/c (owner's GL300C) | gnd |
| `m1900` | FPGAA | `air_fpga` | Lightbridge air FPGA (Cyclone V e50f; device-type 19 "FPGA Air") | air |
| `m2000` | FPGAG | `gnd_fpga_r0` | Ground FPGA rev00 (device-type 20 "FPGA Ground") | gnd |
| `m2001` | — | `gnd_fpga_r1` | Ground FPGA rev01 (Cyclone IV GX-format) | gnd |
| `m2002` | — | `gnd_fpga_r2` | Ground FPGA rev02 | gnd |

Notes: `m1300`/`m1600` exist only on the GL300a/HDMI RC; the owner's **GL300C** uses `m1601`
(`gnd_fx3`) and drops the DM365 (`ground-fx3-m1601.md`). Air/ground FPGA split is V from the DUML
device-type enum (19/20), the module tags (FPGAA/FPGAG) and DJI's own in-firmware `FPGA.A`/`FPGA.G`
name table in `m0100` (`fpga-air-vs-ground.md` R1); which of `m2000/01/02` sits on which RC board
revision is still open (`fpga-air-vs-ground.md`).

## Buses (proposed name → endpoints / medium)

Two-ended buses: `<medium>_<side>_<endA>_<endB>`. Rates/addresses live in the cited docs.

### Aircraft-internal
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `uart_air_lbmcu_fc` | `air_lb_mcu` ↔ `air_fc` | USART1, 256000 8N1 DMA (`dataflow.md`) | V route, FC end I |
| `uart_air_lbmcu_fpga` | `air_lb_mcu` ↔ `air_fpga` | USART3, 257143 8N1 DMA, IDLE-framed | V; faces FPGA I |
| `uart_air_lbmcu_aux` | `air_lb_mcu` ↔ ? | USART2, 250000 (board code 7 only) | V; peer U |
| `spi_air_lbmcu_fpga` | `air_lb_mcu` ↔ `air_fpga` | SPI2, 4.5 MHz mode 1, 3-byte frames (+AD9363 relayed) | V |
| `can_air_primary` | `air_fc` ↔ `air_lb_mcu` ↔ `air_gimbal` ↔ `air_cam_a9` ↔ center/ESC | CAN, std IDs 0x412/0x413 (cam/gimbal), 0x414/0x415 (rx type 30); FC CAN1 PD0/PD1 AF9 | V IDs; some nodes I |
| `can_air_fc2` | `air_fc` ↔ ? | FC CAN2, PB12/PB13 AF9 — second bus, role unclear | V bus, role U |
| `iq_air_fpga_ad9363` | `air_fpga` ↔ air AD9363 | ~12-bit I/Q sample port, ~11.2 MHz | I |
| `usb_air_dm368_fx2` | `air_video_enc` ↔ `air_fx2` | USB bulk EP2, raw H.264 (`m0800-dm368-provenance.md`) | V |
| `fifo_air_fx2_fpga` | `air_fx2` ↔ `air_fpga` | 8-bit slave FIFO, AUTO | V config; peer=FPGA I |
| `usb_air_a9_fx2` | `air_cam_a9` ↔ `air_fx2` | USB (switched; control + FX2 fw-load) | V |
| `vid_air_a9_dm368` | `air_cam_a9` ↔ `air_video_enc` | camera→encoder H.264 path | U medium |
| `eth_air_a9` | `air_cam_a9` (GMAC) | Ethernet/GMAC, board_info/random MAC (not chip-locked) | V present; peer U |

### RC-internal (GL300C)
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `uart_gnd_lbmcu_fx3` | `gnd_lb_mcu` ↔ `gnd_fx3` | UART, 115200 8N1 DUML (`ground-fx3-m1601.md`) | V FX3 end; peer m1400 I |
| `uart_gnd_lbmcu_fpga` | `gnd_lb_mcu` ↔ ground FPGA | DUML-over-UART; carries the Master-ID (`id-entry-point.md`) | V strings; I |
| `spi_gnd_lbmcu_fpga` | `gnd_lb_mcu` ↔ ground FPGA | SPI0 @0x40020000, CS P2.9, ~4 MHz — register/control | V |
| `gpio_gnd_lbmcu_fpga` | `gnd_lb_mcu` ↔ ground FPGA | config/reset/handshake strobes | V |
| `gpif_gnd_fpga_fx3` | ground FPGA ↔ `gnd_fx3` | 8-bit GPIF, PIB socket 2 — video | V |
| `usb_gnd_fx3_phone` | `gnd_fx3` ↔ phone | USB; `55 CC` chunks (0x5749 DUML, 0x574A video) | V |
| `iq_gnd_fpga_ad9363` | ground FPGA ↔ ground AD9363 | ~12-bit I/Q sample port | I |

### Shared RF
| Proposed | Endpoints | Medium / detail | Tag |
|---|---|---|---|
| `rf_air_gnd` | air AD9363/FPGA ↔ ground AD9363/FPGA | 2.4 GHz OFDM link, ~39 ch; over-the-air encryption not ruled out | I |

Full edge-by-edge evidence and rates: `dataflow.md`, `data/m0900-buses.tsv`, `m0900-can-channels.md`,
`ground-fx3-m1601.md`, `fc-io-inventory.md`, `id-entry-point.md`.
