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

## Honest boundary

The MCU will not contain the OFDM math (that's the FPGA) or the H.264 codec (that's the
DaVinci/Ambarella chips). It yields configuration, control, IDs, channel/pairing, and the
AD9363 setup — which is exactly the glue needed to point the SDR demod at the right
signal with the right parameters.
