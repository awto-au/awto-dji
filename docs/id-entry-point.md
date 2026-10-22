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
- **The MCU<->FPGA link is NOT SPI.** Scanning the image for LPC176x peripheral-base
  literals: **zero** SSP0/SSP1 references (`0x40088000`/`0x40030000`), and **zero** SSP
  register-address literals. The heavily used peripherals are **fast GPIO `0x2009c000` (x25)**,
  SYSCON (x17), PINCON (x14), and UART1 (x2). So the control/data path to the FPGA is a
  **GPIO-driven parallel/serial bus** (with UART used elsewhere), not a hardware SPI port.
- Therefore the ID reaches the FPGA as **register/control traffic on that GPIO bus**, or as
  MCU-assembled MAC-frame header bytes over the same path — either way, through the MCU<->FPGA
  GPIO interface.

Reproduce: `scripts/fpga/*` for the FPGA side; the MCU scan is a literal-pool search for the
peripheral bases above over `c1_m1400.bin`.

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
