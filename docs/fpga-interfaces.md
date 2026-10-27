# FPGA data interfaces (streams in/out), both ends

> **Superseded in part (2026-10-24): see `fpga-pinout-model.md`.** On P3P/GL300C the ground
> FPGA talks to a Cypress **FX3** (`m1601`, 8-bit synchronous slave FIFO, FPGA-clocked), not an
> FX2LP. The air FPGA talks to the FX2 (`m1500`), also 8-bit synchronous slave FIFO. The
> 256000 8N1 CENTER UART to the FC is m0900's USART1, not an FPGA pin (`m0900-can-channels.md`).


What goes into and out of the Lightbridge FPGA, and the bus types/widths. Interface
*types* and control signals are documented (dji-firmware-tools OFDM-receiver-board wiki
+ the module map); exact **widths are not published** and the adjoining MCU
(`air_router_stm32f103` / `gnd_rc_lpc1765`) is stripped, so widths are the chips' standard
buses, flagged as such. Confirming the exact widths is a
logic-analyzer job (see end).

## Ground (remote controller) FPGA — Cyclone V `5CEFA4` (wiki-sourced; not confirmed by any bitstream)

Bitstream evidence on the part is mixed: m2000/m2002 are Cyclone V streams, m2001 is Cyclone III/IV-format (`fpga-images.md`). No pin or width below comes from a bitstream decode.

| Link | Direction (vs FPGA) | Interface | Width / notes |
|---|---|---|---|
| FPGA ↔ **FX2LP** (CY7C68013A) → USB → phone | **out** (recovered H.264) | **Cypress Slave-FIFO**: `IFCLK`, `SLRD#`, `SLWR#`, `FLAGB#`, `FLAGC#` (on service pads) | parallel `FD` bus **8- or 16-bit** — FX2LP is configurable; width **not documented** |
| FPGA ↔ **AD9363** transceiver | **both** (RX samples in, TX samples out) | AD936x **sample data port** | ~**12-bit I/Q**, LVDS-DDR or parallel-CMOS (12-bit ADC/DAC); port mode **not documented** |
| **STM32F103** → AD9363 | — (MCU drives) | **SPI** | serial — radio config |
| STM32F103 → FPGA | — (MCU drives) | **config/reset GPIO** (+ SPI `MOSI/MISO/SCK/NSS` pads) | discrete / serial |
| FPGA/MCU ↔ flight controller | both | **UART** (CENTER connector) | serial, **256000 8N1**, DUML |
| FX2LP ↔ phone | both | **USB 2.0** (CAMERA connector `DP/DM`) | — |

Summary: RF samples in/out on the ~12-bit AD9363 port; video out on the 8/16-bit
slave-FIFO parallel bus; config via SPI/GPIO; DUML via UART.

## Air (aircraft) FPGA — `m1900` (`air_fpga_cyclonev`)

Less documented; from the module map and symmetry:

```
Ambarella A9SE camera ─► DaVinci DM368 (H.264 encode) ─► air FPGA (m1900) ─► AD9363 ─► PA ─► antenna
```

- **DM368 → air FPGA:** encoded H.264 in. Interface **not publicly documented** — likely
  a parallel video/FIFO bus (unconfirmed).
- **air FPGA ↔ AD9363:** same ~12-bit sample data port (TX).
- **STM32F103 (`m0900` / `air_router_stm32f103`):** configures AD9363 (SPI) and drives FPGA config/reset.

## What the FPGA does (from the data flow)

Ground: takes RF I/Q samples from the AD9363, runs the OFDM demod + **descrambler**
(whitening, fixed-polynomial — see `link-security.md`), and streams recovered H.264 out
to the FX2LP. Air: takes encoded H.264 from the DM368, runs the scrambler + OFDM mod, and
drives the AD9363 for transmit. In both cases the FPGA is the **baseband modem +
whitener** between a parallel sample port (AD9363) and a parallel payload port
(FX2LP / DM368), with an MCU configuring it over SPI/GPIO.

## Confirming the widths (probe plan)

Widths aren't in the code/docs, but they're directly measurable — this is the "probe the
data as it passes through" approach:

- **FX2LP bus width (8 vs 16):** logic analyzer on `IFCLK` + the `FD` lines while video
  streams; count active data lines, and use `SLRD#/SLWR#/FLAG` to frame it.
- **AD9363 port (LVDS vs CMOS, lane count):** probe the transceiver data-port pins; LVDS
  differential pairs vs single-ended CMOS, and DDR vs SDR, are visible on a scope/LA.
- **DM368 → FPGA bus:** probe the encoder's output port on the air board.
- Tap points are the documented service pads (SWD, UART `256000 8N1`, SPI); the MCU↔FPGA
  config lines also show the bring-up sequence (and the scrambler seed load).

Until probed, treat the widths above as the chips' standard buses, not measured values.
