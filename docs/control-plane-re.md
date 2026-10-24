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

- **Ghidra 12.2 DEV is installed** (`/home/dan/tools/ghidra_12.2_DEV`, shim
  `~/.local/bin/ghidra`) — best for Thumb-2 decompilation, headless via
  `support/analyzeHeadless` (see `scripts/re/m1500_fx2_disasm.py` for a worked headless
  8051 example; same pattern applies with `-processor ARM:LE:32:Cortex` for `m0900`).
  **radare2 5.5.0** (installed) is also available. `arm_bin2elf.py` from
  dji-firmware-tools can wrap the raw image as ELF with the right base for analysis.
- The **AD9361/AD9363 register map (UG-570)** and the **STM32F103 reference manual
  (RM0008)** for peripheral addresses — both public — are the decode keys.
- Scope: `m0900` (aircraft, STM32F103) only. The remote radio MCU is **not** STM32:
  `m1400` is NXP LPC1765 (`docs/ground-upgrade-path.md`, "Chip identity"). `m1401` is LPC1549.
- Debug-info check on `m0900` (2026-10-24): no ELF, no DWARF (`.debug_*`), no `.symtab`/`.strtab`,
  no map-file or source-path strings. Only format strings survive (e.g. `Fpga Cfg : OK`,
  `Error: ad9363 reg17 - %.2X`, `WM32X A4_FPGA 20150902`). Nothing to recover; manual RE only.

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

## SPI1 resolved: dead code, not a second config path (issue #18)

`SPI1` (`0x40013000`) and `SPI2` (`0x40003800`) were previously lumped together as an
untested "AD9363 + FPGA config" guess (only `SPI2` was ever actually traced — register-only
3-byte frames to the FPGA, `docs/board-connections.md`). `SPI1` is now independently
resolved, by **two separate disassembly methods** on `firmware/P3X_FW_V01.11.0020_m0900.bin`:

1. **`scripts/re/m0900_trace.py`** — capstone linear sweep, resyncing over literal pools,
   31,035 instructions across the whole 75,796 B image.
2. **`scripts/re/m0900_ghidra_disasm.py`** + **`scripts/re/ghidra/DumpARM.java`** — Ghidra
   12.2 headless (`ARM:LE:32:Cortex`, base `0x08008000`), flow-directed auto-analysis from
   the reset vector, 328 functions / 15,119 instructions reached.

**Result (V, both tools agree):** the *only* place the bare `SPI1` base literal
(`0x40013000`) appears anywhere in the image is one `ldr` at `0x08009998`, inside the
generic ST StdPeriph-library `SPI_DeInit()` dispatcher (`push {r4,lr}`; `cmp r0,SPI1_BASE`
-> branch; `cmp r0,SPI2_BASE` -> branch; else return) — and that function has **zero
callers**. Ghidra's flow-directed analyzer, seeded from the reset vector and every real
call/branch target, never disassembles `0x08009998-0x080099de` at all: nothing in the
firmware reaches it. The bare `SPI2` base literal appears in the *same* dead dispatcher
and nowhere else — every live `SPI2` access folds the offset into the pool constant at
compile time (e.g. `0x40003808` = `SPI2_BASE+8`, loaded directly at `0x0800b604`), which is
why a naive literal search for the pure base undercounts real `SPI2` use.

No other `SPI1` evidence exists in the firmware: no `RCC_APB2ENR` bit for `SPI1EN` is ever
set (every `RCC_*PeriphClockCmd` call site targets `GPIOA/B/C`, `CAN1`, or `SPI2`'s `APB1`
bit — never `SPI1`'s `APB2` bit); no GPIO alternate-function config of `PA4-7` (`SPI1`'s
standard `NSS/SCK/MISO/MOSI` pins on this part) — every `PA` pin configured in this image is
`PA0` (board-strap input), `PA1` (single GPIO output strobe), `PA2/PA9-12` (USART/CAN), never
`PA4-7`; no `CR1/CR2/DR` access at `SPI1`'s base anywhere.

**Conclusion (V):** `SPI1` is completely inert in this firmware build — not initialized, not
clocked, not wired to GPIO, never read or written. It is not a second register bus to the
FPGA, and it rules out `m0900`'s `SPI1` as the FPGA config-flash writer the issue is
tracking. It does **not** identify who *does* write the flash — combined with the existing
eliminations (`SPI2` too small/register-only, `m0100`/A9 has no SPI driver, `m1500`/FX2LP is
a verified pure USB pipe), the issue's open question stands: no traced chip on this board
writes the `ATH520` config flash. One possibility not yet checked: the flash may not be
field-updated by any in-system MCU at all (e.g. factory-programmed only) — **U, not checked
this pass**.

**Secondary check — no byte-wide parallel bus from `m0900` to the FX2LP:** every `GPIOA/B/C`
literal-pool reference in the image (14/9/4 by Ghidra's count, matching the capstone sweep)
was reviewed. All are single-pin or 2-pin groups: `PA0` board-strap in (`fn 0x0800c0bc`,
feeds `get_board_version`'s RAM word `0x200000d8`, alongside `PC14/15`), `PA1` single output
strobe (`fn 0x0800b79c`), `PA2`/`PA11`/`PC13` board-version-dependent strap in
(`fn 0x0800b60c`/`0x0800b6ac`), `PB8/PB9` 2-pin output (`fn 0x0800b70c`), plus the already-known
`PB12` (SPI2 CS), `PB13-15` (SPI2 AF), USART and CAN AF pins. No 8- or 16-bit contiguous GPIO
group exists anywhere in `m0900`'s code (also checked Ghidra's full disassembly for
byte-mask immediates like `#0xff00` near these functions — none are GPIO-register operands).
**V (by absence, two tools):** if `m0900` has any path to the FX2LP, it is not a direct
byte-wide parallel link off its own GPIO; this is consistent with `board-connections.md`'s
existing framing of FX2LP sitting downstream of the FPGA's slave FIFO, not wired to the air
MCU directly.

Reproduce: `python3 scripts/re/m0900_trace.py` (SPI1/SPI2 section);
`python3 scripts/re/m0900_ghidra_disasm.py` (full dump at `tmp/m0900_ghidra/m0900_dump.txt`,
log `tmp/logs/m0900_ghidra_disasm.log`).

## MCU emulation attempt (Unicorn) + debug interfaces

Attempted to extract the AD9363 config by running `m0900` in a Unicorn Cortex-M harness
(map flash `0x08000000`/SRAM/MMIO, pre-set "ready" status regs, hook SPI_DR writes). It
boots and executes, but the stripped firmware **diverges to `0x0` after ~10 instructions**
without fuller system modelling, and — more fundamentally — the AD9363 config is almost
certainly **triggered by a runtime DUML command from the main controller, not emitted at
cold boot**. So cold-boot emulation does not just dump the config.

Reliable routes instead: (a) **static** — the SPI driver is already located
(`~0x08001b70`, ST StdPeriph); trace its callers to the AD9361 register table/sequence;
(b) **on-hardware SWD** capture of the live SPI during link bring-up. The emulator is
better used for *stimulus generation in co-simulation* (drive the recovered FPGA netlist),
per `fpga-emulation-plan.md`, than for booting the MCU to completion.

**Debug interfaces (evidence in code):** the `m2001` FPGA fabric exposes standard JTAG
(`TCK`/`TMS`/`TDI` nodes) — a Cyclone-V config/boundary-scan interface — but there is **no
evidence of a SignalTap / Virtual-JTAG runtime debug core** baked into the bitstream, and
the MCU firmware shows no JTAG/debug strings (though SWD service pads exist on the board).
So: hardware JTAG/SWD yes; an in-fabric logic-analyzer to tap, no evidence.

## Static AD9361 register-table search — result: no flat table (config is programmatic)

Scanned `m0900` (air STM32) and `m1400` (ground LPC1765) for an AD9361/AD9363 init table
(write-command / address words in `0x000-0x3FF`, and addr/value record windows). Result:
**no transceiver register table.** Zero runs of AD9361 write-command words; the structured
regions found are **zero-padded lookup/index tables** (e.g. `0001 0000 0001 0000 0002...`
small-integer LUT; `0013 0000 00b0 0001 0006 0002...` an indexed table), not register init.

Conclusion: the AD9363 is configured **programmatically (ADI-driver style), not from a
static table** — register values are computed at runtime from PLL/clock/bandwidth
parameters. This matches the emulation finding (config is code/command-driven, not a boot
blob). So static table extraction does not yield the RF config.

Remaining routes to the actual register values:
- **Disassemble the SPI-config driver** (located `~0x08001b70` in `m0900`) and trace the
  computed writes -> recovers the logic deriving registers from target frequency/bandwidth.
- **Live capture** (SWD, or a logic analyzer on the AD9363 SPI during link bring-up) ->
  reads the exact bytes written; cleanest.
- Check whether the **FPGA** mediates any of the AD9363 SPI rather than the MCU.

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

## External corroboration: FPGA = datastream encoder; scrambler is stock WiMAX

Independent teardown and standards material back the "FPGA is just the link datastream"
reading:

- The `o-gs/dji-firmware-tools` teardown of a DJI air OFDM board describes the FPGA as
  "a **digital data encoder for the Lightbridge protocol** [that] prepares the video data
  and telemetry to be sent through [the] radio channel, and supplies it to [the]
  transceiver" — i.e. framing + modulate an opaque payload, no application logic.
  <https://github.com/o-gs/dji-firmware-tools/wiki/IG800-Air-OFDM-Transceiver-board>
- The WiMAX (IEEE 802.16e) data randomizer is a **standard** 15-bit LFSR PRBS with
  polynomial `1 + x^14 + x^15` (= `x^15 + x^14 + 1`). If Lightbridge uses the stock WiMAX
  randomizer (the WiMAX-family evidence points that way), the scrambler is documented and
  only the **seed** could be DJI-specific — and the seed is recoverable from a capture.

Precision for the P3: its FPGA (Cyclone V) does the whole digital PHY (framing + OFDM
baseband + FEC + scramble); the AD9363 does D/A + RF. So it is "all PHY, no application
logic" — the sense in which it is "just the datastream".

Caveats (do not overclaim "stock"): no source directly confirms DJI's scrambler polynomial;
it is a strong inference from the WiMAX basis, not proof. One forum post calls Lightbridge
"full custom ASIC", but the chip evidence (AD9363 SDR + Cyclone V, not a bespoke baseband
ASIC) favours the WiMAX-family reading; "custom" more likely describes the system than a
novel PHY algorithm.

## `m0306` (A3 flight controller) — a second, separate control-plane MCU (issue #40)

Same reversing approach as `m0900` above, applied to the **flight controller** instead of
the radio MCU — a different chip, different firmware, different role (sensor fusion /
actuator control, not RF). Full writeup: `docs/code-provenance.md` (chip ID, debug-symbol
check, RTOS/library fingerprint) and `docs/dataflow.md` §7.10 (CAN1/CAN2). Summary:

- **Chip:** STM32F427 (Cortex-M4), confirmed `0x08020000`-base, 192 KB SRAM1 — same
  firmware-only SRAM-size method used for `m0900`'s STM32F103 ID, cross-checked against
  public FC-board pinout docs that name the part directly.
- **No debug symbols** — same empty result as `m0900`: no ELF/DWARF/`.symtab`/map-file
  remnants in the 885 KB image.
- **Stack, beyond "µC/OS confirmed":** µC/OS-**III** specifically (task-name strings), a
  CMSIS `SystemInit()`-pattern HSE/PLL/FLASH-latency bring-up at `0x0802258c`, and the same
  ST StdPeriph-shaped RCC-clock-enable dispatch table already identified in `m0900`'s SPI
  driver — three distinct library layers on one chip, not just the RTOS.
- **CAN bus angle:** both CAN1 and CAN2 are genuinely initialised (GPIO AF9, RCC enable,
  bit-timing register writes) — unlike `m0900`'s dead `SPI1`. CAN1 is plausibly this
  chip's end of the same DUML-relay CAN bus `m0900` already carries 0x412-0x415 on; what
  CAN2 carries is open (`dataflow.md` §7.10).
- **Full Ghidra pass:** 2745 functions / 122,341 instructions; project archived to
  `re/ghidra-projects/m0306_flight_controller.tar.gz` (not discarded, per this project's
  earlier Ghidra-project-loss lesson).

## `m1400` (ground/RC radio MCU, LPC1765) — SVD import, Ghidra pass, master-id/join/pairing decode (issue #39)

`m1400` was wrongly documented earlier as "same STM32F103 family" as `m0900` (fixed:
LPC1765, `docs/ground-upgrade-path.md` "Chip identity"). This closes out the first Ghidra
pass on the *correct* chip, with a real NXP SVD instead of guessed peripheral bases, and
decodes the RC master/slave-join and Connected-Master-Id command handling that
`docs/cpu-reversing-proof.md`'s radare2 pass had only partly isolated.

### SVD + peripheral-map corrections (`[spec]`, supersedes `[oss]`)

Added `awto-dan/docs/embedded/reversing/lpc17xx/svd/LPC176x5x.svd` (NXP's real CMSIS-SVD,
via the `cmsis-svd/cmsis-svd-data` public aggregation — same sourcing as the STM32 SVDs
already collected). Cross-checked against it, two of the earlier `[oss]` "prior art" guesses
in `scripts/re/lpc17xx_periph_scan.py` were wrong (now fixed, re-run, log unchanged in shape
but corrected bases — `tmp/logs/lpc17xx_periph_scan.log`):

- **USB was a completely wrong region.** The real USB controller is AHB peripheral
  `0x5000_8000` (0 word hits in `m1400` — USB is simply not used by this firmware). The old
  "USB @ `0x2008C000`, 12 hits" bucket was `0x2008xxxx` **AHB SRAM** (RAM, not MMIO) — those
  12 literal words are ordinary data/buffer pointers, not USB register accesses.
- **PWM1/I2C0 were both one slot low** (`0x40014000`/`0x40018000` guessed vs real
  `0x40018000`/`0x4001C000`) — a reserved gap in the real map was mistaken for PWM1.
- `GPIOINT`'s real base is `0x4002_8080` (+0x80 from the guess; the old window still
  happened to catch the real hits).
- Everything else in the original scan (WDT, TIMER1, UART0-3, legacy SPI, RTC, PINCONNECT,
  SSP0/1, ADC, DAC, TIMER2/3, SYSCON, fast GPIO, I2C1) matched the SVD exactly.
- Flattened the SVD into 511 `address -> PERIPH_REGISTER` labels
  (`scripts/re/svd_to_labels.py`, output `docs/data/lpc176x5x-register-map.tsv`) and applied
  all 511 inside Ghidra (`scripts/re/ghidra/DumpLPC17xx.java`) — 0 skipped, confirming
  Ghidra's flat address space accepts MMIO labels outside the loaded flash image with no
  extra memory-block setup needed.

### Ghidra pass (full)

`scripts/re/m1400_ghidra_disasm.py`: `ARM:LE:32:Cortex`, `BinaryLoader` base `0xA000` (LPC17xx
flash starts at `0x0`, unlike STM32's `0x08000000` — flash address = file offset + `0xA000`,
per `docs/ground-upgrade-path.md` "Addressing"). **789 functions, 38,426 instructions**, full
decompile of every function. Project archived (not discarded) to
`re/ghidra-projects/m1400_radio.tar.gz`.

### `duml_local_dispatch` (flash `0xF3C8`, = offset `0x53C8`) confirmed byte-for-byte

`ldrb r0,[frame,9]` (cmd_set); `cmp r0,#0xA; bcs <return>`; `tbb [pc,r0]` — a flat 10-entry
jump table **indexed directly by the cmd_set byte value** (0-9), settling the earlier
"set 6 vs set 9" confusion in `cpu-reversing-proof.md`: the RC/master-id dispatcher really is
reached for on-wire **cmd_set byte value 9**, not the Java `CmdSet.Rc` enum's declaration
position (6) — DJI's app-side `CmdSet` enum order and the wire byte are not the same number.
Case 0 (general/upgrade, flash `0xF3E2`) matches `docs/ground-upgrade-path.md`'s Q1 table
exactly (cmd 0x07 Enter Loader -> `0xF266`=offset `0x5266`, cmd 0x0A Update Finish ->
`0xF18A`=offset `0x518A`, etc. — same handlers, same addresses). **[fw], both tools agree.**

### cmd_set 9 sub-dispatch (flash `0xF6E4` = offset `0x56E4`) — full case table recovered

`ldrb r1,[frame,0xA]` (cmd_id); `cmp r1,#0xD; beq <cb10>`; `tbb` for id 0-0xC; explicit chain
for id 0x10/0x12/0x13/0x14/0x15/0x2C. Matched against the APK's real `CmdSet.Rc.CmdIdType`
numeric values (`tmp/apk/dynamic/decompiled/.../CmdSet.java`, extracted 2026-10-23):

| cmd_id | APK name | Handler (flash) | Role (Ghidra decompile, `[fw]`) |
|---|---|---|---|
| 0x0C (12) | SetConnectMaster | `0xCBCA` | **Reports** 6 stored RC-state fields (RAM `0x100005E8`+`0x62`/`0x63`(99)/`0x64`(100)/`0x70`/`0x71`-1/`0x79`) in a 15-byte reply. Despite the "Set" name, this handler only *reads* state and replies — it does not accept new values. |
| 0x0D (13) | GetConnectMaster | `0xCB10` | **Writes** state: parses the payload as a run of `(field_id, value)` byte pairs (count from the DUML 10-bit length field), stores each into the same `0x62`/0x63/0x64/0x70/0x71/0x79 offsets; field id 1 additionally sets a flag byte (RAM `0x100000C8`+0xc = 1) when the frame's receiver-type nibble (`frame[4]&0x1F`) == 9. Unknown field id -> status `0xE0`. Despite the "Get" name, this is the one that *writes* fields. |
| 0x10 (16) | GetSearchMode | `0xCADC` | Writes 1 byte (payload[0]) to RAM `0x100000C8`+`0xd`; 1-byte status reply. |
| 0x12 (18) | GetToggle | `0xCA6C` | Multi-field setter: calls 5 small helper setters (`0x17A94/178F0/17906/1791C/17978/17942`) from payload bytes 0xb-0xe (bit7 of byte 0xb selects a branch) — role of each helper not traced further this pass. |
| 0x13 (19) | RequestSlaveJoin | `0xC9B4` | **No RAM state write** — builds and sends an 8-byte status/capability reply: a flag bit (from helper `0x16848`), a 14-bit field (`0x179EC`), two bytes (`0x179FC`), one byte (`0x17980`), and RAM `0x1000000C` (a version/counter word) `* 10`. Reads as "can this RC accept a slave join" + capability snapshot, not a state mutation. |
| 0x14 (20) | GetSlaveList | `0xC8C2` | Dual-mode accessor on a mode byte at rc_state (`0x100005E8`)+`0xF`: mode 0 and mode 1 each read/write one byte between the payload and two RAM pointers (`0x10000311`/`0x10000310`) selected by the frame's receiver-type nibble (2 or 0xE), clamped against a third pointer (`0x10000272`). Mode-1 path also runs the same slave-id-match-and-decrement as `DeleteSlave` below. |
| 0x15 (21) | DeleteSlave | `0xC7C2` | If payload[0]==0 and the frame's slave-id field (`frame[6:8]`, u16) matches RAM `0x100000C8`+`0x9E`, decrements a slave-count byte at `+0x9C` (floored at 0). Matches the RC-to-RC "multi-controller" model in `docs/duml-protection.md` ("a second/subordinate RC joining the primary RC"), not aircraft binding. |
| 0x2C (44) | (not in `CmdIdType`; DJI-internal) | `0x15A1C` | Keyed sub-dispatch on u16 `frame+0xD` (0x901-0x914) — already documented in `docs/ground-upgrade-path.md` Q3 (chip-UID reply at key 0x904). |

**Correction to `cpu-reversing-proof.md`'s "ISOLATED" section:** that pass (radare2,
2026-10-24 earlier) got the handler addresses right (`0xCBCA`/`0xCB10`, i.e. offsets
`0x2BCA`/`0x2B10`) but mis-described the data direction of 0x0D ("GET... return stored
values from RAM state") — Ghidra's full decompile shows 0x0D is the one that *writes*
fields and 0x0C is the one that *reports* them, i.e. the Set/Get naming and the actual
read/write direction are swapped. `cpu-reversing-proof.md` should be read with this
correction; not re-edited line-by-line here to avoid duplicating the addresses in two
places.

### `SetFrequency` (RC `CmdIdType.SetFrequency` = 0x2F/47) — not implemented on this chip/build

Searched the full `m1400` disassembly for any `cmp`-style test against cmd_id `0x2F`
(the pattern every other case above uses): **zero hits.** The cmd_set-9 dispatcher's highest
handled id is `0x2C` (44); `0x2F` falls through to the default (no-op) path. So **this
firmware build (`04.10.0006`) has no DUML handler for "RC Pairing"/`SetFrequency` at all** —
it is not merely unlabelled, it is absent. The air/ground **frequency-hopping config is
therefore not DUML-command-driven on this MCU**; the likelier owner is the FPGA bring-up
record-script mechanism (`fpga_script_exec_record` / the undecoded scripts at offsets
`0x20310`/`0x1D1D4`/`0x23D68`, `docs/ground-upgrade-path.md` Q2) rather than a Set/Get DUML
pair. Open for a follow-up pass; not chased further here (scope: issue #39 asked for the
decode, and the decode's answer is "not present").

Reproduce: `python3 scripts/re/svd_to_labels.py --svd <path> --out docs/data/lpc176x5x-register-map.tsv`;
`python3 scripts/re/lpc17xx_periph_scan.py`; `python3 scripts/re/m1400_ghidra_disasm.py`
(full dump `tmp/m1400_ghidra/m1400_dump.txt`, log `tmp/logs/m1400_ghidra_disasm.log`).
