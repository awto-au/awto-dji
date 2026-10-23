# Methodology: FPGA bitstream → structural netlist → (toward) Verilog

How to reverse the P3's Lightbridge FPGA from its bitstream, honestly scoped. The target
is Cyclone V for the air `m1900` (e50f-family by header/PRAM CRC) and ground `m2000`/`m2002`; ground `m2001` is Cyclone III/IV-format (best match EP4CGX150). All of these except m2001 appear ENCRYPTED, so no bitstream has been lifted (see `fpga-images.md`, `m2001-decomp-findings.md`). This is
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

The firmware module (`m1900`) is a structured header + PRAM (cleartext, valid CRCs) + CRAM. The CRAM is indistinguishable from uniform random (entropy 7.9999, chi-square ~255 +-23): ENCRYPTED, strong circumstantial; option-bit meaning inferred; may be a producer-side keyed scramble rather than Altera AES. The earlier "compressed, not encrypted" call used a chi-square (113,468) computed over the whole container (header, PRAM, 0xFF padding), and is withdrawn. Strip the DJI container/flash header to reach the `.rbf` frame layout; the CRAM cannot be decoded without the key or an oracle. Altera's *on-chip* config compression is a nibble-RLE scheme (documented in Mistral's `rbf_load`), not LZMA.

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

## Forward-fuzz / "Rosetta stone" — compile known RTL/IP and match patterns

A powerful complement to decoding gates: **compile known Verilog/IP in the same vendor
tool (Quartus) and device, then recognise those patterns in DJI's bitstream/netlist.**
Two uses:

1. **Fabric-bit mapping** (what Mistral already did): toggle one RTL feature, diff the two
   bitstreams, tabulate bit <-> fabric feature. Decodes the bitstream to a netlist.
2. **Functional-block templating (the high-value one):** compile a known block (FFT, FIR,
   LFSR scrambler, CP insert, symbol mapper, FEC) and capture its *structural signature* —
   DSP mode/count, M10K count + init, local routing topology, LUT clusters — then
   graph-match that signature against a decoded DJI netlist (none exists today: the images are encrypted or undecoded). This would **get past
   the DSP/M10K decode gap**: you don't decode DJI's DSP internals, you match the *shape*
   of a known IP whose internals you already have, and transfer them.

Why it is likely to work here: the modem is almost certainly built from **Altera's own
OFDM/WiMAX MegaCores**, not hand-rolled gates. Evidence and templates:

- Altera shipped a **WiMAX OFDM kernel reference design** (clear-text VHDL) using the
  **FFT MegaCore**, FFT sizes 128-2K for 1.25-20 MHz bandwidths, plus OFDMA symbol-level
  blocks (subchannelization, cyclic-prefix insert) and bit-level blocks (symbol mapping,
  FEC MegaCore). It targeted older families but **recompiles to Cyclone V**.
- (Withdrawn: the earlier "`m2001` shows 64 DSP blocks + M10K + DLLs" was decode noise, pluribus #114.) The LB2 MCU strings (`mcs`, `harq`, `bw`)
  confirm a WiMAX/LTE-family design that would use these IP cores.

So the template library is small and known: **FFT II, FIR II, symbol-mapping + FEC
MegaCores, and the WiMAX OFDM reference design**, compiled in era-matching **Quartus
(~13.x-15.x)** for the `5CEBA4`/`e50f` device.

Caveats: placement/routing vary with Quartus version/seed/settings, so match *structural
signatures* (DSP mode, M10K init, local topology), not absolute bit positions; you need
the right Quartus version + device; and today's DSP Builder drops Cyclone V, but the
Quartus 13-15 IP catalog MegaCores (FFT II, FIR II) support it. HAL's module
identification plus a compiled-IP fingerprint library is the matching engine.

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
| De-pack to plain `.rbf` | Container only; CRAM appears encrypted |
| Decode LUT/FF/routing fabric (Mistral) | Only on an unencrypted Cyclone V stream; the DJI Cyclone V images appear encrypted |
| Emit gate-level structural Verilog | Yes (a LUT/FF mesh) |
| Recover DSP/M10K-based datapath (FFT/FEC) | **No** — not decoded by current CV tooling |
| Recover readable behavioral RTL of the modem | **No** — manual/partial research at best |
| Clone the bitstream onto the identical part | Unknown: encryption (key-locked?) unresolved |

## Tooling summary

- **Project Mistral** (`Ravenslofty/mistral`) — Cyclone V model + `mistral-cv`
  decompile/routes/bels; `generator/` is the Quartus-driven fuzzer.
- **Quartus** — vendor tool, required for fuzzing the exact device.
- **yosys / nextpnr-mistral** — forward flow (Verilog → bitstream); useful to validate the
  model and for round-tripping, not for lifting an unknown design to RTL.
- Not runnable in this analysis env (no Quartus; P3 part not in Mistral's DB) — this is
  the method, to be executed where those are available.
