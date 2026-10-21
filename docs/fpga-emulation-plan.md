# FPGA emulation / co-simulation plan (reconcile netlist against firmware + chips)

> **Correction (see `m2001-decomp-findings.md`):** the "DSP/M10K internals are the
> undecodable wall" claim below is **wrong on re-run**. Mistral's `decomp` recovers LUT
> masks (17,144), FF modes, DSP mode+coefficients, and M10K config+contents. The real
> residual gap is **interconnect source resolution** (~53,889 unresolved active routes),
> not the logic blocks. Read the bullets below with that correction in mind.

Approach: once a bitstream is decompiled to a netlist, identify the pins, simulate the
fabric, and **reconcile simulated I/O against real captures and the surrounding firmware/
chips** to recover what the netlist alone can't (the DSP/M10K internals). This is the
standard golden-model method, and the reconciliation step is what gets past the one hard
gap.

## 1. Identify the pins

Raw material already recovered: Mistral gave **199 named package I/O pins** for `m2001`
(e.g. `Y3`, `W2`, `AA2`) plus the block/route map. Label them by function using:

- **AD9363 data port** (ADI UG-570) — recognise the ~12-bit I/Q sample bus + control.
- **FX2LP slave-FIFO** signals (`IFCLK`, `SLRD#`, `SLWR#`, `FLAGB#`, `FLAGC#`, `FD[..]`).
- **MCU config** — from reversing `m0900`/`m1400`: which FPGA config/reset/SPI lines the
  MCU drives.
- **Clocks/DLLs** — the 15 DLL + SCLK nodes map the sample-clock/timing pins.

Output: an FPGA pinout labelled by function (sample bus, USB-FIFO, MCU control, clocks).

## 2. Simulate the netlist

Export the Mistral fabric to a structural Verilog netlist of Cyclone-V primitives and run
it in **Verilator** or **Icarus**. LAB/LUT/FF simulate directly (LUT = truth table, FF =
register). **Blocker:** DSP and M10K **internal configuration is not decoded** (Mistral
gap) — exactly the modem's multiply/RAM datapath. Pure gate-sim therefore reproduces the
fabric around the datapath, not the datapath itself.

## 3. Co-simulate and reconcile (gets past the blocker)

Build a system testbench with the unknown blocks constrained by real observations:

- **FPGA** = recovered netlist; **DSP/M10K = black boxes** with unknown internal behavior.
- **Surrounding chips** = behavioral models: AD9363 (ADI sim models), FX2LP (trivial FIFO).
- **Stimulus from the real firmware**: run `m0900`/`m1400` in an MCU emulator
  (**QEMU / Unicorn / Qiling**, Cortex-M) to produce the exact SPI/GPIO config sequence;
  feed a **known payload** (all-0s — see `known-plaintext-plan.md`).
- **Reconcile**: compare simulated output against a real SDR or digital-tap capture.
  Known input + observed output **constrains/solves the black-box DSP/M10K behavior** by
  I/O matching. This is the reconciliation that recovers blocks the static tools can't
  read.

## 4. Hardware emulation (cleanest for the DSP/M10K gap)

Load the de-packed bitstream onto a **matching Cyclone-V dev board** (5CEBA4 / e50f die),
drive controlled inputs, capture outputs. Real silicon runs the DSP/M10K correctly, so it
sidesteps decoding them. Caveats: need the right die/package, and must present the correct
interface signals (use the step-1 pin map); device/package differences can misplace I/O.

**On the vendor "emulator".** Quartus ships a free logic simulator (ModelSim / Questa
**Intel Starter Edition**) plus device simulation libraries — but it simulates *your own*
design (RTL or a gate netlist), not a captured foreign bitstream. No vendor tool ingests an
arbitrary `.rbf` and runs it as silicon; that capability exists from nobody, because the
bitstream->fabric mapping is the undocumented part the vendor never published. So the
"vendor emulator" path is the *same* as Mistral->netlist->sim — the vendor just provides a
nicer back-half simulator once Mistral has decoded the front half. It is not a shortcut
around the decode step.

**On JTAG probing (the dev-board route).** JTAG on a Cyclone-V gives **configuration +
boundary-scan**: you can read/toggle the device-boundary **I/O pins** — exactly what the
input/output reconciliation needs. It does **not** expose internal nodes; that requires a
**SignalTap** logic-analyzer core compiled *into* the design, and `m2001` has no SignalTap
instance (DJI would not ship one, and we can't add one without recompiling). So the clean
hardware path is: matching 5CEBA4/e50f board -> load the de-packed bitstream -> drive known
inputs and capture outputs at the boundary using the 199-pin map (step 1) -> reconcile.
Internal visibility, where needed, comes from the Mistral netlist sim, not from JTAG.

## Can the minimal recovery be done purely in an FPGA emulator? Yes

The minimal strategy (`minimal-recovery.md`) makes emulation viable, because the small
DJI-specific logic lives in **LAB/LUT/FF** fabric — which Mistral decodes and a simulator
(Verilator/Icarus) runs — while the **DSP/M10K** (undecodable) hold only the FFT/FEC
datapath you re-implement. So the one thing that blocks full FPGA emulation is in the part
you don't need.

- **Whitening LFSR — near-trivial.** It is ~a dozen flip-flops + XOR taps, a small isolated
  subcircuit of LABs/LUTs/FFs. Find it in the Mistral `routes` output (FF outputs fed back
  through LUTs), transcribe those cells to Verilog, simulate -> the scrambler sequence
  comes straight out, no hardware/capture. (Berlekamp-Massey on the sim output is a free
  cross-check.)
- **FPGA-side framing/control** — extract the LAB/LUT/FF subnetlist (DSP/M10K as black
  boxes), export to Verilog, run in Verilator.
- **ID / MAC** — emulate in the MCU emulator (Unicorn/QEMU on `m0900`/`m1400`) if the MCU
  inserts it; if any is in the FPGA it is LAB logic and emulatable too.

Full picture: a two-part **co-sim** — FPGA emulator (LFSR + framing) + MCU emulator (ID) —
entirely in software, no board. The one tooling gate is **exporting a simulatable Verilog
netlist from Mistral** (transform `routes` + LUT config into structural Verilog; the full
`decomp`/`.bt` came out empty, so isolate the needed subcircuits rather than dump
everything). Trivial for the LFSR; bounded for broader logic. The DSP/M10K wall does not
apply because those blocks are re-implemented, not emulated.

## Which emulators actually exist for these ICs

Per chip (corrects the earlier raw-Unicorn attempt, which was CPU-only and therefore
diverged):

- **MCUs `m0900` (STM32F103) / `m1400` (LPC1765): a full emulator exists — Renode.**
  Renode (Antmicro) models MCU **peripherals** (SPI/GPIO/timers/IRQ), runs unmodified
  firmware, supports the STM32 and LPC families, and co-simulates **Verilator HDL
  peripherals**, SystemC TLM, and multiple nodes. QEMU also has some STM32 board models.
  With peripherals modeled, the firmware should boot and reach the AD9363 SPI config +
  ID/framing — unlike the raw-Unicorn run. Caveat: the exact `STM32F103CB`/`LPC1765` board
  is not pre-canned; write a `.repl` platform description and model the custom FPGA-bus
  peripheral (attach the Verilated subnetlist). Real setup, but the right tool.
- **FPGA (Cyclone V): the bitstream->sim path exists per-family via the RE projects, and
  for Cyclone-V that project is Mistral — which we already use.** Important correction: for
  FPGA families whose bitstream format has been reverse-engineered, a bitstream *can* be
  taken straight into simulation — **iCE40** (Project IceStorm), **ECP5** (Project Trellis),
  **Xilinx 7-series** (Project X-Ray/prjxray). Those map the fabric so completely that
  `bitstream -> unpack -> netlist -> simulate` feels direct. The Altera **Cyclone-V** member
  of that same family of projects is **Project Mistral**, and it is the tool already run
  here (it unpacked `m2001` to a 56,337-route netlist). So this is **not** "no tool exists":
  a CPU emulator interprets a known ISA, but an FPGA bitstream is a device-specific fabric
  config that must be *decoded* by the matching RE project first — and for our silicon that
  decoder (Mistral) exists and works. The one difference from ECP5/Trellis is **coverage,
  not existence**: Trellis maps the ECP5 fabric essentially completely, while Mistral maps
  Cyclone-V **LAB/LUT/FF/routing but not the DSP/M10K internals yet** — exactly the gap the
  minimal-recovery plan routes around (re-implement the standard WiMAX datapath; pull only
  the small DJI-specific LFSR/ID out of what Mistral *does* decode). What still does not
  exist for any vendor is a tool that runs a *foreign* `.rbf` as opaque silicon without that
  decode step. The two ways to execute DJI's bitstream:
  - **Decode -> netlist -> simulate (software):** Mistral -> Verilog -> Verilator/Icarus.
    The real "FPGA emulator" (same pattern as ECP5/Trellis -> nextpnr/sim); limited by the
    DSP/M10K decode gap (black-box those).
    Mistral also carries a fabric timing/SPICE model (`tnet`/`trun`/`timing`), so it is
    more than functional, but it is a de/compile tool, not plug-and-play.
  - **Real silicon (full fidelity):** load the de-packed bitstream on a matching Cyclone-V
    (same die/package, e.g. 5CEBA4/e50f); the chip runs DSP/M10K and all. Not an emulator,
    but the only full-fidelity run. Needs the exact part + correct interface signals.
  - **Not applicable:** vendor simulators (ModelSim/Questa/Quartus) need the design
    RTL/netlist, not a bitstream; commercial emulators (Palladium/Veloce/ZeBu/HAPS) map
    your own RTL, not a foreign bitstream; openFPGALoader/Quartus programmer program real
    hardware, they do not emulate.
- **Ambarella A9SE / DaVinci DM368/DM365: no full emulator.** QEMU has no machine model
  for these proprietary SoCs (only generic Cortex-A9 boards); userland can run under QEMU
  user-mode (CPU only). Not needed for the ID/whitening (they are the payload path).
- **AD9363 / FX2LP:** behavioral models (ADI AD9361 sim model; trivial FX2LP), attachable
  to Renode as peripherals.

So the minimal recovery can run as **one Renode + Verilator co-emulation, no hardware**:
`m0900`/`m1400` firmware in Renode + the FPGA LFSR/framing subnetlist as a Verilated
peripheral + a behavioral AD9363. Redo the MCU emulation in Renode, not Unicorn.

## Honest assessment

Valid method, and the proper one. Steps **1, 3, 4** are what actually pass the DSP/M10K
wall — reconciliation against real I/O, or running the real bitstream on silicon. Pure
simulation (step 2) stalls on that gap. Substantial effort, but no dead end.

Tooling: Mistral (bitstream->netlist), Verilator/Icarus (sim), yosys + nextpnr-mistral
(round-trip/validation), QEMU/Unicorn/Qiling (MCU-firmware stimulus), ADI AD9361/3 sim
models, a 5CEBA4/e50f dev board (hardware emulation). None of this runs in the current
analysis env (no Quartus, no board); it is the method to execute where those exist.
