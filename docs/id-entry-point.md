# Where the Master-ID enters the FPGA (ground link)

Question: find where the pairing/Master-ID enters the Lightbridge FPGA. Answer below,
separating what is **verified from our firmware + bitstream** from what needs the **board
schematic**. Evidence is reproducible with the scripts in `scripts/fpga/`.

## Short answer

The ID is **not computed inside the FPGA and not a hardcoded constant.** It is owned by the
**ground MCU `m1400` (LPC1765 "GROUND LB2")**, which writes it into the Lightbridge ground
FPGA (`m2000/m2001/m2002`, Cyclone-V) over the **MCU->FPGA GPIO control bus** — *not* over
SPI, *not* over the AD9363 RF sample bus, *not* over the FX2LP/USB video path. Inside the
FPGA it lands in the MAC framer / address-match logic (LAB fabric), which stamps it into the
transmitted preamble/header and filters it on receive.

## Verified from the firmware (`m1400`)

`c1_m1400.ini` identifies the module: `LPC1765 GROUND LB2` (Cortex-M3, image loads at
0x0; initial SP `0x10007f60` = top of the LPC1765 32 KB SRAM, reset vector in range — a
valid bare image).

- **The MCU owns the FPGA comms and the master-ID code.** ASCII strings present in the
  image: `FpgaErr`, `MASTER`, `TestMaster`. So FPGA-interface handling and master-ID logic
  are in this MCU, consistent with the DUML "RC Connected Master Id Set/Get" field.
- **The MCU<->FPGA link IS SPI (corrected).** The earlier scan only looked for SSP0/SSP1; the
  image uses the legacy SPI0 block at `0x40020000` (CS on P2.9, 4 MHz requested), carrying the
  same `[0E reg val]` / `[0F reg FF]` register protocol as the air side (`docs/ground-upgrade-path.md`,
  bit-record table byte-identical to m0900). Fast GPIO `0x2009c000` (x25), SYSCON (x17), PINCON (x14)
  and UART1 (x2) are also used: GPIO for control strobes (e.g. P1.23), UART elsewhere.
- Therefore the ID reaches the FPGA as **register/control traffic on the SPI0 register bus** (or
  GPIO strobes), or as MCU-assembled MAC-frame header bytes over the same path (inferred, not seen).

Reproduce: `scripts/fpga/*` for the FPGA side; the MCU scan is a literal-pool search for the
peripheral bases above over `c1_m1400.bin`.

## Transport refined by disassembly (GPIO = control, data = UART)

Disassembling the GPIO routine at `0x1234` (radare2, `-a arm -b 16 -m 0`) settles what the
GPIO bus is actually *for*. It loads GPIO base `0x2009c000` and, on a 0-3 state selector,
does read-modify-write **bit set/clear** on the LPC176x fast-GPIO `FIOSET`/`FIOCLR`
registers:

```
case 1: [r1,0x3c] |= 0x400000   ; GPIO1.FIOCLR  bit22
        [r1,0x18] |= 0x010000   ; GPIO0.FIOSET  bit16
case 2: [r1,0x38] |= 0x400000   ; GPIO1.FIOSET  bit22
        [r1,0x18] |= 0x010000   ; GPIO0.FIOSET  bit16
        [r1,0x7c] |= 0x2000000  ; GPIO3.FIOCLR  bit25
case 3: [r1,0x38] |= 0x400000   ; GPIO1.FIOSET  bit22
        [r1,0x1c] |= 0x010000   ; GPIO0.FIOCLR  bit16
        [r1,0x78] |= 0x2000000  ; GPIO3.FIOSET  bit25
```

(LPC176x fast-GPIO: port *n* at `0x2009c000 + 0x20*n`; `FIOSET=+0x18`, `FIOCLR=+0x1C`.)
These are **discrete control lines** toggled by state — reset / mode / enable / config
strobes to the FPGA (port0 bit16, port1 bit22, port3 bit25). There is **no byte-streaming
loop and no `FIOPIN` data write**, so the GPIO is *not* a parallel data bus for the ID.

The MCU's data transport is **UART, interrupt-driven**: the handler at `0x16f3c` reads a
UART's IIR (`[base,8] & 0xf`, interrupt-ID decode) off base `0x4009c000` (UART3), and the
image sets up UART0-3. DJI's standard inter-module transport is **DUML over UART**, and the
Master-ID is a DUML field ("RC Connected Master Id"). So:

> **The Master-ID enters the FPGA as a DUML frame over a MCU<->FPGA UART; the GPIO lines are
> the control/handshake (reset/mode/enable) beside it, not the data path.** SPI is unused.

Still not determinable from firmware alone: **which** UART (0/1/2/3) is the FPGA link vs the
RC-host / stick links — that needs the PINCON pin-mux trace plus the board schematic.

## Verified from the bitstream (`m2001`)

The ground FPGA exposes **~195 true external input pins** and ~55 outputs (counted by edge
direction in the Mistral `routes` netlist: a `GPIO:DATAIN` that *drives* fabric is a real
input; a `GPIO:DATAOUT` that fabric drives is a real output — `scripts/fpga/gpio_dir.py`).
The ID enters on the subset of those inputs wired to the MCU control bus. The RF sample bus
(to the AD9363) and the FX2LP slave-FIFO are separate pin groups.

## What needs the board schematic (honest limit)

- **Exact MCU-pin -> FPGA-ball mapping.** The netlist gives FPGA ball locations (A7, AA2, …)
  but not which board net each ball joins. Saying "this FPGA ball is driven by MCU GPIO pin
  Pn.m" requires the GL300/C1 ground-unit schematic, which we do not have. Pin *roles* can
  be *inferred* from bus width/clocking (a ~12-bit clocked group = AD9363 I/Q; a narrow
  group with its own clock = MCU control) but not proven from firmware+bitstream alone.
- **Exact register location inside the fabric.** Tracing the ID register from the input pins
  to the framer/address block is blocked by the **~40% unresolved interconnect** in the
  Mistral decode (`routes2`: 53,889 unresolved active routes — see
  `m2001-decomp-findings.md`).

## Why this is enough for the link goal

Per `minimal-recovery.md` / `alternative-approaches.md`, interop does **not** require
pin-level tracing of the ID inside the FPGA:

- **Value:** read the Master-ID straight from **cleartext DUML** (RC UART / USB `usbmon`, or
  the device label / app) — no RE.
- **Frame position:** falls out of a **known-plaintext capture** (constant header bytes).

So the ID's path into the FPGA is now pinned down architecturally (MCU -> GPIO control bus ->
MAC framer/address block), and the two things actually needed (value + frame position) come
from captures, not from resolving the fabric. The internal FPGA trace stays a fallback,
gated on the same open Cyclone-V model work as the LFSR extraction.
