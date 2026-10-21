# Methodology: FPGA bitstream → structural netlist → (toward) Verilog

How to reverse the P3's Lightbridge FPGA from its bitstream, honestly scoped. The target
is Cyclone V (ground FPGA `5CEFA4`; air FPGA `m1900`, part not yet identified). This is
interoperability RE of an owned device; it is analysis only.

## The pipeline

```
 .rbf (de-packed)  ──►  decode via a fabric model  ──►  structural netlist  ──►  behavioral recovery
   (vendor format)        (bit ↔ LUT/FF/route map)       (LUTs, FFs, routes)      (FFT? FEC? LFSR?)
        │                         │                             │                        │
   strip DJI/flash          Project Mistral               mistral-cv routes/bels    manual / research
   header, de-RLE           (already fuzzed CV)            dumps active fabric       (not automated)
```

## 1. De-pack to a plain `.rbf`

The firmware module (`m1900`) is a packed/compressed config image (structured header +
high-entropy, gzip-incompressible body; **compressed, not encrypted** — chi-square on the
bulk is far from uniform, ruling out AES). Strip the DJI container/flash header and
resolve any compression to Altera's plain `.rbf` frame layout. Altera's *on-chip*
config compression is a nibble-RLE scheme (documented in Mistral's `rbf_load`), not LZMA.

## 2. Get / extend the fabric model by fuzzing

The bit↔fabric map is built by **differential fuzzing** of the vendor tool — the standard
technique behind Project X-Ray (Xilinx), IceStorm (Lattice) and **Project Mistral**
(Cyclone V):

1. In **Quartus**, generate a minimal design exercising one feature (one LUT mask bit,
   one routing mux selection, one FF mode).
2. Compile to a bitstream; change exactly one feature; compile again.
3. **Diff** the two bitstreams — the bits that moved are that feature's encoding.
4. Repeat across LUTs, routing muxes, IO, clocking to tabulate the whole fabric.

Mistral's `generator/` already does this for Cyclone V (`routes`, `nodes`, `p2p`, `p2r`,
`inv`, `drivers`, `iob`, …), compiling probe designs with Quartus and decompiling with
`mistral-cv`. So you **reuse Mistral's model** and only fuzz gaps.

**Requirements:** Quartus (vendor tool, multi-GB, licensed) for the **exact device**, and
the correct device entry in Mistral. Mistral ships `5CEBA4`/`5CSEBA6`; `5CEFA4` is the
same family (feasible); the air FPGA part must be identified first.

## 3. Decode the bitstream to a structural netlist

With the model and a plain `.rbf`, `mistral-cv` yields the fabric state:

```
mistral-cv decompile <model> <file.rbf>     # bitstream -> configuration RAM
mistral-cv routes    <model> <file.rbf>     # active routing (interconnect)
mistral-cv bels      <model>                # logic blocks available
```

From active routes + occupied LABs/LUTs/FFs you reconstruct a **structural netlist**:
LUT init masks, flip-flop modes, and the wires between them. This is emittable as
gate-level Verilog (a flattened mesh of LUT/FF primitives).

## 4. Behavioral recovery — assisted by dedicated netlist-RE tools

Turning the structural netlist into readable logic means recognising *word-level*
structure in a LUT sea: grouping bit-slices into buses, LUT clusters into
adders/multipliers, FF chains into registers/FSMs. There are **dedicated tools** for this
(not just manual work):

- **HAL** (`emsec/hal`) — open-source gate-level netlist RE framework (graph model,
  Python/C++ API, plugin system).
- **DANA** (HAL plugin) — recovers high-level registers/words from flip-flop dataflow
  (no tuned thresholds; evaluated on OpenTitan).
- **HAL module identification** — detects adders, subtractors, constant multipliers,
  counters; recovers bit order within registers.
- **RELIC** (UT Austin) — classifies registers as control vs data.
- Reference pipeline: *"Stealing Maggie's Secrets — IP Theft Through FPGA Reverse
  Engineering"* (arXiv 2312.06195), and *"Reverse Engineering Word-Level Models from
  Look-Up Table Netlists"* (arXiv 2303.02762).

Scope is still **assisted and partial**: these recover register banks, arithmetic blocks
and FSM-ish structure to guide a human, not regenerate DJI's RTL. They consume a
gate-level netlist (LUTs + FFs + connectivity), so the pipeline is **Mistral (bitstream
-> LUT/FF/routing netlist) -> HAL/DANA/module-id/RELIC (word-level recovery) -> human**.
The remaining gap for a modem is the DSP/M10K internal config (not decoded by current
Cyclone-V tooling), which holds the multiplier/RAM datapath.

## Why this is especially limited for a radio modem

- **Mistral's README states DSPs and M10K block-RAMs are not decoded** ("neither the mux
  usage nor the configuration"). An OFDM modem is built from exactly those — DSP
  multipliers (FFT, filters, FEC) and M10K RAMs (FIFOs, twiddle/interleaver tables). So
  the decode recovers the LUT/routing scaffolding but **misses the modem's core math**.
- The scrambler/descrambler (likely an LFSR + control) might be visible in LUT/FF fabric,
  but reading it out as the actual polynomial/seed is manual.

## Realistic outcome

| Goal | Feasible? |
|---|---|
| De-pack to plain `.rbf` | Yes |
| Decode LUT/FF/routing fabric (Mistral) | Yes, on a supported/identified device |
| Emit gate-level structural Verilog | Yes (a LUT/FF mesh) |
| Recover DSP/M10K-based datapath (FFT/FEC) | **No** — not decoded by current CV tooling |
| Recover readable behavioral RTL of the modem | **No** — manual/partial research at best |
| Clone the bitstream onto the identical part | Plausible (not key-locked) |

## Tooling summary

- **Project Mistral** (`Ravenslofty/mistral`) — Cyclone V model + `mistral-cv`
  decompile/routes/bels; `generator/` is the Quartus-driven fuzzer.
- **Quartus** — vendor tool, required for fuzzing the exact device.
- **yosys / nextpnr-mistral** — forward flow (Verilog → bitstream); useful to validate the
  model and for round-tripping, not for lifting an unknown design to RTL.
- Not runnable in this analysis env (no Quartus; P3 part not in Mistral's DB) — this is
  the method, to be executed where those are available.
