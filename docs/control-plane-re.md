# Reverse the control plane (the MCU), not the FPGA

Key reframing: the FPGA is a **fixed OFDM modem + whitener** that is *configured at
runtime*; it doesn't hold the IDs, the channel plan, or the pairing logic. The **radio
MCU (STM32F103, module `m0900`)** on each end is the control plane — it configures the
AD9363 over SPI, drives the FPGA's config/reset lines, and handles the DUML that carries
the Master ID, pairing and frequency. So reversing the MCU is higher-value and far more
tractable than attacking the bitstream.

## Why the MCU is the right target

- **It's code, not gates.** `m0900` is ARM Cortex-M3 Thumb-2 (Ghidra/radare2 decompile
  it). The bitstream is an opaque compressed config blob.
- **The AD9363 has a public register map.** The AD9361/AD9363 is documented (Analog
  Devices UG-570). The MCU's SPI write sequence therefore **decodes directly into the RF
  setup** DJI never published: LO/centre frequency, channel bandwidth, sample rate, gain,
  filter config — i.e. the OFDM channel parameters. The chip config hands you the
  "unknown" numbers.
- **The ID is fed here.** The MCU implements the DUML radio command set (Master ID,
  `RC Pairing` = Frequency Set, join/bind). Reversing it shows how the ID is stored and
  inserted into frames, and the MCU->FPGA register writes may carry the **scrambler seed
  / frame mode**.

## Concrete targets inside `m0900`

Load base: the image begins with a Cortex-M vector table at `0x08000000` (SP
`0x20004cb8`, reset -> `0x08008200`), i.e. a bootloader region then the app at
`~0x08008000`. In Ghidra/radare2 set ARM Cortex-M, load at `0x08000000`.

1. **AD9363 SPI configuration** — find writes to the STM32F103 SPI peripheral
   (SPI1 `0x40013000`, SPI2 `0x40003800`); each AD9361/3 access is a 16-bit word
   (R/W + 10-bit register address `0x000-0x3FF` + data). Decode the sequence against
   UG-570 -> exact frequency/bandwidth/sample-rate/gain. This alone yields the OFDM
   channel parameters.
2. **FPGA config/control writes** — GPIO (APB2 `0x40010800+`) config/reset lines and any
   parallel/serial config path; look for a scrambler-seed or frame-mode register being
   loaded at bring-up.
3. **DUML radio command handling** — the parser for the RC command set (Master ID
   set/get, available master id, request/list join slave, RC Pairing). Shows ID storage
   and the pairing state machine.

## Tooling

- **Ghidra** (best for Thumb-2 decompilation; not installed here) or **radare2 5.5.0**
  (installed). `arm_bin2elf.py` from dji-firmware-tools can wrap the raw image as ELF with
  the right base for analysis.
- The **AD9361/AD9363 register map (UG-570)** and the **STM32F103 reference manual
  (RM0008)** for peripheral addresses — both public — are the decode keys.
- Do this for **both ends**: `m0900` on the aircraft and the radio MCU in the remote
  (same STM32F103 family), to see both sides of the pairing/config.

## How it combines with the SDR work

The MCU gives the **control plane + RF setup (+ possibly the scrambler seed)**; the OFDM
**symbol datapath** still lives in the FPGA and is recovered from an SDR capture via
standard WiMAX-family demod. But MCU-derived parameters turn the SDR side from blind
estimation into a near-turnkey demod: you already know the bandwidth, sample rate, centre
frequency and (maybe) the seed, so sync + descramble fall into place. MCU + SDR together
are the practical path; the bitstream is not on the critical path.

## What radare2 actually found in `m0900` (this session)

Analysed the real `m0900` image (load `0x08000000`, Cortex-M Thumb-2):

- **Peripheral map (32-bit base constants in literal pools):** `GPIOA/B/C` (9/7/4 refs),
  `RCC` (2), `SPI1` and `SPI2` (adjacent at `0x08001c00`), `USART1/2`. So the MCU uses
  **SPI** (AD9363 + FPGA config), **GPIO** (FPGA config/reset lines), **USART** (DUML),
  with **RCC** enabling the clocks — exactly the control-plane role.
- **SPI driver identified:** disassembly around the SPI literals is the **ST Standard
  Peripheral Library** SPI code — halfword ops on the peripheral base at offset `0x00`
  (CR1; set/clear bits `0x2000`/`0x4000`), `0x08` (SR; `tst` for TXE/RXNE/BSY flags),
  `0x0C` (DR), `0x10/14/18` (CRC regs). Bare-metal STM32 on ST's StdPeriph lib, no RTOS.

This confirms the model from the binary itself. The next (manual, Ghidra-grade) step is to
trace the callers of the SPI send/flag helpers to recover the **AD9363 register-write
table** (decode vs UG-570 -> frequency/bandwidth/sample rate) and to find where the
**Master-ID is written into the outgoing frame header** (the addressing/"tagging" the
hypothesis describes). That tracing wasn't completed this session.

## On the "FPGA just tags the ID" hypothesis

Consistent with everything found: the "key" is an **address/ID**, not crypto — frames
carry the Master-ID and receivers filter out frames not addressed to them. Whether the ID
is inserted by the MCU (building the frame header, then handing payload to the FPGA) or in
the FPGA itself is the open question; the StdPeriph SPI + DUML code in `m0900` suggests the
**MCU builds/handles the addressed frames** and the FPGA does PHY (modulate + whiten).
Confirming it means finding the frame-build routine in `m0900` (trace from the USART/DUML
parser to the SPI/FPGA path).

## Cross-product reuse (is there an easier build elsewhere?)

The radio stack is shared across DJI's Lightbridge-family products — the same `xV4`
format and module slots appear in Inspire 1 (`WM610`), Matrice 100/600, A3, the GL300/C1
remotes, etc. Tested the idea by unpacking **Inspire 1 `WM610_FW_V01.11.01.50`** and
diffing its `m0900` against the P3's:

- Same slot/role (Lightbridge STM32 MCU), but **different build**: Inspire v05.00.0000
  (88 KB) vs P3 v04.01.0000 (76 KB); nearly all bytes differ.
- Inspire build is **not richer**: no debug/symbol strings, similar string count — equally
  stripped. So a sibling product doesn't automatically give an easier target.

Still-useful directions this opens:
- **Standalone DJI Lightbridge / Lightbridge 2** — an integrator-facing product (HDMI/SDI,
  documented serial controls in its manual); its firmware is the most likely to expose a
  richer/serial-documented interface. Best next candidate to unpack.
- **DJI Onboard SDK** (A3/N3/M100/M600) — DJI's **open-source** SDK documents the serial
  command/telemetry protocol (the control layer) officially. It is the genuine "DJI
  published it" source for the command protocol (not the radio PHY), and gives a PC/Linux
  companion-computer UART path to those flight controllers (the P3 does not officially
  expose it).
- **Comparative diffing** across versions/products to isolate the stable config tables
  (e.g. the AD9363 register sequence) from the churn — a standard RE shortcut even when no
  single build is symbol-bearing.

There is no PC-based software Lightbridge demod; the "base station" is the LB2 ground
unit (hardware), and the PC "DJI GroundStation"/"GS Pro" tools are app-layer (DUML), not
radio.

### Lightbridge 2 (C1) firmware — the ground/RX side + a richer MCU (unpacked)

Unpacking `C1_FW_V01.06.0000` (Lightbridge 2) gave the **ground/RX side** the aircraft
firmware lacked:

- `m1300` — DM365 video **decoder** (ground), 4.4 MB.
- `m1400`/`m1401` — ground radio MCU, **NXP LPC1765** (different chip from the air-side
  STM32F103), v04.10.0006. **Least-stripped radio firmware found** — 683 strings, source
  paths (`@LPC17xx_LIB\lpc17xx_rtc.c`), and the `ch/mcs/bw/snr/rssi/harq` link-telemetry
  string (see link-security.md). Best MCU RE target so far.
- `m1600`/`m1601` — receiver USB firmware: FX2LP (`68013`) is a tiny 2.7 KB 8051 image;
  the CY2014 variant is 190 KB.
- `m2000`/`m2001`/`m2002` — ground FPGA bitstream, **8 MB** (vs the air FPGA's 4 MB), three
  board-revision variants, same compressed (entropy ~7.99) style as the air image but a
  distinct, larger bitstream (RX differs from TX).

So "look at another product" paid off here: LB2 completes both ends of the radio and the
LPC1765 ground MCU is the richer target for recovering the AD9363 config + link framing.

## FPGA image reuse + the ASIC/DSP (software-defined) generations

Measured P3 vs Inspire 1 per module: **only `m1900` (the air FPGA bitstream) is
byte-identical** (both `01.00.2144`, SHA `f3a55dea…`, 4 MiB). Every other module (camera,
FC, gimbal, ESC, radio MCU, video) differs per product. So the OFDM modem is one shared,
fixed bitstream across the Lightbridge family — one RE effort covers all, and there is no
richer in-family variant to exploit.

"Maybe some designs use a DSP/processor instead of an FPGA" — correct, and it maps to
three DJI generations of increasing reversibility:

1. **Early P3 / Inspire (FPGA):** modem = Altera Cyclone-V bitstream (`m1900`). Gates;
   hard to reverse; not accessible as code.
2. **Later P3 / GL300 (Artosyn ASIC):** AR8001 "data encoder/DSP" replaced the FPGA, with
   a design that *exactly matches the previous FPGA bitstream* (board-compatible). Same
   logic hardened into an ASIC — **not** easier (fixed silicon, no bitstream, no modem
   code exposed). AR8003 replaced the AD9363; an STM32F103 still drives both.
3. **P4 Pro / Mavic / Spark (OcuSync):** moved to a CPU+DSP chipset running *custom modem
   software* (Leadcore LC1860C-class lineage). **This is the reversible case** — the modem
   is software on a DSP/CPU, not gates, which is why the community decodes OcuSync and not
   Lightbridge. Trade-off: those firmwares are IMaH-signed/encrypted (harder to extract),
   but once extracted the modem is analyzable code.

Implication: a "software-defined DJI modem" to reverse exists — in the **OcuSync
generation**, not the P3. For the P3 the modem stays FPGA/ASIC, so its practical path is
**SDR capture + MCU-derived parameters**, not reversing the modem logic.

## Honest boundary

The MCU will not contain the OFDM math (that's the FPGA) or the H.264 codec (that's the
DaVinci/Ambarella chips). It yields configuration, control, IDs, channel/pairing, and the
AD9363 setup — which is exactly the glue needed to point the SDR demod at the right
signal with the right parameters.
