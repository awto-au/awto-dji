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

## Bottom line

Mistral decodes the **logic** of `m2001` (LUTs, FFs, DSP, M10K) far more completely than our
docs claimed. What is genuinely incomplete is **interconnect source resolution** (~54k
unresolved routes). The path to a simulatable netlist / LFSR extraction runs through closing
those interconnect gaps locally, not through any DSP/M10K wall.
