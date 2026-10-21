# m2001 decompile findings (corrects the "DSP/M10K wall" claim)

Reproducible result from running Project Mistral's `decomp` on the de-packed `m2001`
ground-FPGA bitstream. **This corrects earlier docs** that said Mistral's `decomp` came out
empty and that the DSP/M10K internals are the one undecodable wall. Neither holds on re-run.

## How to reproduce

```
mistral-cv decomp   5CEBA4U19C8 m2001.depack.bin m2001.bt   # logic + routes -> text
mistral-cv routes   5CEBA4U19C8 m2001.depack.bin            # resolved active routes
mistral-cv routes2  5CEBA4U19C8 m2001.depack.bin            # UNRESOLVED active routes
```

(`m2001.depack.bin` is the de-packed/decompressed bitstream; model `5CEBA4U19C8` shares the
`e50f` die with the P3 part `5CEBA4U19I7`.)

## What `decomp` actually recovers (it is NOT empty)

`m2001.bt` = 359,954 lines. Record types:

| Record | Count | Meaning |
|---|---|---|
| `s …:LUT_MASK.*` | 17,144 (16,145 distinct) | **ALM 64-bit LUT truth tables** — the combinational logic itself |
| `s …` FF config | ~tens of thousands | DFF modes, `*_FEEDBACK_SEL`, `BMODE/TMODE`, `ARITH_SEL`, clock/clear selects |
| `s RAM.*` | 72,499 | MLAB / M10K **contents** |
| `s DSP.*` | 2,061 | DSP **config**: `MODE`, `COEF_A/B`, input-register controls |
| `s M10K.*` | (full) | M10K config: data widths, clock/clear selects, timing |
| `r …` | 70,007 | resolved routing edges |

So the **logic cells are fully decoded**: LUT masks, FF modes, DSP operating mode +
coefficients, M10K config + contents. A gate/block-level model of the LAB fabric is
buildable directly from `m2001.bt`.

### DSP operating modes (the 64 DSP blocks are legible)

```
 31  M9X9            (9x9 multipliers)
 10  M18X18P36
  6  M27X27
  6  M18X19_COMBINED
  7  BMNONE          (unused)
```

A multiplier-heavy datapath — consistent with an OFDM modem (FFT butterflies, FIR/equaliser
taps). The point: DSP **operations are visible**, not a black box.

## The real residual gap: interconnect source resolution (not DSP/M10K)

The honest limitation is the **routing graph**, not the logic:

- `routes2` (unresolved active routes): **53,889**
- `Source unknown on rnode …` warnings during decomp: **386,648**
- Resolved routes in `m2001.bt`: **70,007**

So roughly **~40%+ of active route sources are unresolved** — Mistral sees a routing node is
active but can't always decode which mux source drives it (global/local interconnect:
`GOUT`, `H6`, `H3`, `TD`). The cells are known; the wiring *between* them is partial.

## Implications

1. **The earlier "DSP/M10K is the one hard wall" framing is wrong.** Those blocks are
   decoded (config + contents + DSP mode/coef). Correct the dependent reasoning in
   `fpga-emulation-plan.md` and `minimal-recovery.md`.
2. **The limiting factor for netlist tracing is interconnect completeness.** Following a
   signal FF -> interconnect -> LUT input -> FF can hit unresolved-source breaks (~40%).
   This — not the DSP — is what a "write one" effort should target: improve mux-source
   decode for the unresolved rnode classes, or bridge gaps using the `p2r`/`p2p`/`cmux`
   connectivity tables Mistral already exposes.
3. **LFSR extraction is now better posed:** we have LUT masks (can recognise XOR/parity
   masks = linear feedback) and FF modes. A scrambler = a small set of FFs whose feedback
   LUT masks are linear (parity of a few inputs), wired in a cycle. The obstacle is only the
   unresolved interconnect on the specific cycle, which is a bounded, local problem to
   resolve per-candidate rather than the whole fabric.

## Follow-up: the LUT masks are present but not directly interpretable

Attempted the LFSR hunt directly on the masks (find affine/XOR LUTs = scrambler feedback).
Result: **0 affine LUTs**, and every one of the 17,144 masks reads as ANF **degree 4-6**,
with min degree 4 even for unused `BMNONE/BMNONE` ALMs. That is diagnostic, not real:

- ANF degree is invariant under input-variable permutation, so uniform high degree **cannot**
  be a mere input reordering.
- It means the 64 mask bits are in Mistral's **raw CRAM physical layout** (the order
  `bmux_val_read` assembles from `bmux_cram_bpos`), not logical truth-table-address order,
  **and** fractured ALMs interleave two independent sub-LUT truth tables in the 64 bits.
- Splitting into two 32-bit halves gives only 952/34,288 "affine" halves — and those are
  just all-0/all-1 unused halves (degree 0), not XOR taps.

So to read the logic as Boolean functions you need the **Cyclone-V ALM model**: the
CRAM-bit -> logical-LUT-address map plus the `TMODE/BMODE/*EF_SEL/ARITH_SEL` fracturing
rules that say which bits/inputs form which sub-LUT. That model lives in **nextpnr-mistral**
(its architecture/bel code), not in the raw `.bt`. Mistral's `.bt` faithfully dumps the
*bits*; turning bits into *gates* is the ALM-decode layer on top.

## Status of both tracks (LFSR extraction + interconnect resolver)

| Track | State | Blocker |
|---|---|---|
| (1) LFSR / logic extraction | masks dumped; affine-detector written and correct | need ALM model (CRAM->address map + fracturing) to interpret masks as gates |
| (2) interconnect resolver | ~54k routes unresolved; `p2r/p2p/cmux` tables available | unresolved mux-source decode is itself incomplete Cyclone-V model coverage |

Both bottom out on the **same root**: completeness of the open Cyclone-V model (Mistral +
nextpnr-mistral), not on anything DJI-specific. Pushing them further means contributing to
that model (reuse nextpnr-mistral's ALM bel decode for masks; extend mux-source tables for
routing) — a real, reusable effort, but an open-FPGA-tooling project, not a quick script.

## Bottom line

Mistral decodes the **logic bits** of `m2001` (LUT masks, FF modes, DSP mode+coef, M10K
config+contents) far more completely than our docs claimed — the DSP/M10K "wall" was wrong.
The genuine remaining layers are (a) the ALM-decode model to read masks as gates and (b)
interconnect source resolution; both are open Cyclone-V tooling gaps, not DJI secrets. This
re-confirms `alternative-approaches.md`: the **cheapest path to the whitening is not netlist
extraction but recognising the standard WiMAX scrambler (`x^15+x^14+1`) and solving only the
seed from an all-0s / repetitive capture** — which needs none of this FPGA-model work. Keep
the netlist route as the fallback that only becomes attractive if the ALM model gets wired in.
