# FPGA emulation / co-simulation plan (reconcile netlist against firmware + chips)

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

## Honest assessment

Valid method, and the proper one. Steps **1, 3, 4** are what actually pass the DSP/M10K
wall — reconciliation against real I/O, or running the real bitstream on silicon. Pure
simulation (step 2) stalls on that gap. Substantial effort, but no dead end.

Tooling: Mistral (bitstream->netlist), Verilator/Icarus (sim), yosys + nextpnr-mistral
(round-trip/validation), QEMU/Unicorn/Qiling (MCU-firmware stimulus), ADI AD9361/3 sim
models, a 5CEBA4/e50f dev board (hardware emulation). None of this runs in the current
analysis env (no Quartus, no board); it is the method to execute where those exist.
