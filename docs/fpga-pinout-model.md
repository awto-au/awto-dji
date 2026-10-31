# FPGA pinout model: what each Lightbridge FPGA must connect to (air and ground)

The FPGA bitstreams are encrypted or not decoded (`fpga-images.md`), so no pin comes from a
netlist. This page derives each FPGA's external interfaces from the **other side** of every
link: the MCU, Cypress and DaVinci firmware that drives it. Tags: **V** = read from that
firmware (address cited), **I** = inferred, **U** = unknown. It supersedes the wiki-based
table in `fpga-interfaces.md` where they differ (that table has an FX2 on the ground and the FC
UART on the FPGA; both are wrong for P3P/GL300C).

## Air FPGA (`m1900` / `air_fpga_cyclonev`, Cyclone V e50f family by header; package U)

```
                      +------------------------- air FPGA -------------------------+
DM368 -USB-> FX2 ---- | 8-bit sync slave FIFO  (FPGA = master, drives IFCLK)      |
 (m1500)              | FD[7:0], FIFOADR[1:0], SLRD#, SLWR#, SLOE#, PKTEND#,      |
                      | FLAGA/B/C (+SLCS#)          ~17-18 pins                   |
m0900 SPI2 ---------- | SPI slave: SCK, MOSI, MISO, CS(PB12)   4 pins             |
m0900 GPIO ---------- | PB3 reset pulse (active low), PA13 control   2 pins       |
m0900 USART3 -------- | UART 257143 baud, DUML both ways   2 pins (I)             |
                      | AD9363 data port  (CMOS 28 or LVDS 32 pins, mode U)       | ---- AD9363
                      | AD9363 SPI master + RESETB/ENABLE/TXNRX  ~7 pins          | ---- AD9363
config flash -------- | Active Serial (DCLK, nCSO, AS_DATA) + nCONFIG/nSTATUS/    |
 (4 MiB image)        | CONF_DONE, MSEL straps, JTAG                              |
                      +------------------------------------------------------------+
```

| Interface | Facts | Tag |
|---|---|---|
| FX2 (`m1500` / `air_fx2_cy68013`) slave FIFO | `IFCONFIG=0x03`: slave FIFO, synchronous, external IFCLK (the FPGA clocks it). `EP2FIFOCFG=0x10` AUTOOUT, 8-bit. `EP6FIFOCFG=0x08` AUTOIN, 8-bit. PINFLAGS and polarity left at defaults (flags active low, indexed by FIFOADR) | V (FX2 side), pin use I |
| Stream direction | DM368 → USB EP2 OUT → FIFO → FPGA reads raw H.264 slices. FPGA writes → EP6 IN → DM368 (return channel, consumer U) | V (`m0800-dm368-provenance.md` §7) |
| m0900 (`air_router_stm32f103`) SPI2 | mode 1, 4.5 MHz, 3-byte frames, CS PB12; FPGA register file (`fpga_regmap`), boot handshake via reg 0x8A | V (`m0900-buses.tsv`, `fpga-bringup.md`) |
| m0900 GPIO | PB3 reset pulse, PA13 control | V lines, roles I |
| m0900 USART3 | DUML to the link side, 257143 baud actual | V on m0900; FPGA end I (by elimination, `dataflow.md`) |
| AD9363 SPI | the FPGA relays AD9363 register access for m0900 (set 0x09 id 06 hi≠0xFE path) | V (m0900), pins I |
| AD9363 data | ~12-bit I/Q, ~11.2 MHz sample rate | I (`phy-params.md`); CMOS vs LVDS U |
| Config | 4 MiB container, 2.06 MB used → 32 Mbit serial flash class | I by size |
| Not on the FPGA | FC/camera/gimbal CAN and USART1: those are m0900's (`m0900-can-channels.md`) | V |

**Air I/O estimate:** about 35–40 (AD9363) + ~18 (FX2) + 8 (m0900) + config/clock, i.e. about
**65–75 user I/O**. I.

## Ground FPGA (`m2000`/`m2002` Cyclone V — `gnd_fpga_cyclonev_r0`/`gnd_fpga_cyclonev_r2`, `m2001` Cyclone IV GX-format — `gnd_fpga_cyc4gx_r1`; board rev decides)

```
                      +----------------------- ground FPGA ------------------------+
FX3 (m1601) GPIF II - | 8-bit sync slave FIFO (FPGA = master, drives PCLK)        |
                      | DQ[7:0], CTL0-3 strobes in (CTL2 = OE#), A1:A0 thread     |
                      | select in, CTL4 empty/full flag out, CTL5 partial flag out|
                      |                                   ~15-16 pins             |
m1400 SPI0 ---------- | SPI slave: SCK P0.15, MISO P0.17, MOSI P0.18, CS P2.9     |
                      | 4 MHz                                       4 pins        |
m1400 GPIO ---------- | FPGA reset pulse P1.23; P0.16/P1.22/P3.25 are RC          |
                      | status-LED outputs, NOT FPGA control (corrected) 4 pins   |
m1400 UART? --------- | downlink and uplink DUML (I/U, see below)   2 pins        |
                      | AD9363 data port + SPI master + control  (as air)         | ---- AD9363
config flash -------- | 8 MiB image class -> 64 Mbit serial flash (I)             |
                      +------------------------------------------------------------+
```

| Interface | Facts | Tag |
|---|---|---|
| FX3 (`m1601` / `gnd_fx3_cyusb2014`) GPIF II | `GPIF_CONFIG=0x80000380`: sync, SDR, **clock input on the CLK pin** (FPGA-driven). `GPIF_BUS_CONFIG=0x1003`: 31-pin allocation, **8-bit DQ**, OE present. `CTRL_BUS_DIRECTION=0x500`: CTL4/5 outputs, rest inputs. `CTRL_BUS_SELECT[4]=24` (current-thread empty/full), `[5]=25` (partial). `POLARITY=0xbf` (CTL0-5 and 7 active low). `AD_CONFIG=0x44`: address lines are inputs, data thread selected by A1:A0. 4 threads → PIB sockets 0-3 | V (`m1601` table at `0x400300d8`; decoded with FX3 SDK 1.3.1 `gpif_regs.h`, checked against bladeRF and Ettus B200 configs) |
| FX3 stream use | FPGA → socket 2 = video only (2 KB buffers). Socket 0 (FX3 → FPGA) is created but unused in phone mode; it is EP2 → FPGA raw in GPIO41-high (HDMI-board) mode | V (`ground-fx3-m1601.md`) |
| m1400 (`gnd_rc_lpc1765`) SPI0 and GPIO | listed pins, 4 MHz, same `0E`/`0F` register protocol and bit records as air; FPGA id word in regs 0x8B-0x8E. **The Master-ID is written over this SPI0 bus** (`fpga_set_receiver_id` 0x16850: `0E reg val` to regs 3..7, bracketed by reg0 bit7), not over GPIO strobes as earlier versions of this doc and `id-entry-point.md` claimed — the 3 GPIO pins once read as "ID strobes" are the RC status LED outputs (see corrected row above) | V (`cycloneiv_clean_pairing` analysis via `awtoau/pluribus`; `m1400` disasm `FUN_00016850`/`FUN_00015d4a`) |
| AD9363 SPI | relayed through FPGA reg 1 (`0xbec8`/`0xbf16` in m1400) | V (m1400), pins I |
| DUML path to and from m1400 | All phone-side DUML, air senders included, reaches the FX3 over its UART from (I) m1400, so m1400 must exchange DUML with the FPGA. A UART is the likely carrier (wiki-era docs say so). Reading it through SPI0 registers is not excluded | I/U |
| Config | 8 MiB images; three board revisions with different families (rev 01 is Cyclone IV GX-format, best match EP4CGX150) | V (sizes, headers), I (flash part) |

**Ground I/O estimate:** about 35–40 (AD9363) + ~16 (FX3) + ~10 (m1400) + config/clock,
i.e. about **65–75 user I/O**. I. The pinout differs by board revision (00/01/02), since the
families differ.

## What this says about the link (I)

- **Both FPGAs present the same shape:** an 8-bit synchronous slave-FIFO master towards a
  Cypress USB chip (raw video), a low-speed serial DUML port towards its adjoining MCU
  (`air_router_stm32f103` on the air side, `gnd_rc_lpc1765` on the ground side), an SPI
  register slave towards the same MCU, and the AD9363 on the other side. The mux and demux of
  video and DUML is FPGA logic; neither Cypress chip nor DaVinci adds DUML to video (V both
  ends).
- **The bandwidth is very asymmetric.** The 8-bit FIFO buses can move tens of MB/s, the video
  is about 1–2 MB/s, and DUML is capped by its UARTs (≈25.7 kB/s air USART3, ≈11.5 kB/s ground
  FX3 UART at 115200).

## How to make it V on hardware (owner's own aircraft and RC)

1. **FX2/FX3 side (no FPGA knowledge needed):** probe the Cypress chip's IFCLK/PCLK (frequency),
   FD/DQ activity, and FLAG pins. The Cypress pinouts are public, so each probe point is known.
2. **AD9363 port mode:** differential pairs (LVDS) versus single-ended (CMOS) are visible on a
   scope at the transceiver's P0/P1 pins.
3. **UARTs:** logic-probe m0900 USART3 (PB10/PB11) and the ground FX3 UART pins. DUML at
   257143 / 115200 baud identifies each FPGA UART and the m1400 hop.
4. **JTAG IDCODE** on each FPGA identifies the exact device and package. A boundary scan then
   gives the real pin map.

Reproduce the FX3 numbers: `python3 scripts/re/fx3_m1601.py <m1601.bin>` (GPIF section).
