# FPGA image inventory (extracted this session)

Every Lightbridge FPGA bitstream extracted from the unpacked firmwares, with measured
properties. (Images live in the analysis env, not in this repo.)

| Image | Role | Size | Used | Version | Entropy | SHA-256 (16) |
|---|---|---|---|---|---|---|
| P3 `m1900` | air FPGA (TX) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` |
| Inspire 1 `m1900` | air FPGA (TX) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` |
| LB2 `m2000` | ground FPGA rev 00 (RX) | 8 MiB | 4.65 MB | 01.00.2107 | 7.99 | `39a74d8d4a69ebaf` |
| LB2 `m2001` | ground FPGA rev 01 (RX) | 8 MiB | 2.12 MB | 01.01.2107 | **5.84** | `b6cc5e96f12446b1` |
| LB2 `m2002` | ground FPGA rev 02 (RX) | 8 MiB | 4.80 MB | 01.02.2109 | 7.99 | `30aa24c31e5180a7` |
| P3S `m1900` | air FPGA (TX) | 4 MiB | 2.01 MB | — | — | (independent sample, see below) |

## Observations

- **Air FPGA is one shared bitstream.** P3 and Inspire 1 `m1900` are **byte-identical**
  (same SHA, v01.00.2144) — a single 4 MiB compressed TX bitstream across the
  Lightbridge family. (Sources: `P3X_FW_V01.11.0020`, `WM610_FW_V01.11.01.50`.)
- **Ground FPGA has three board-revision variants** (`m2000/01/02`, 8 MiB each, versions
  2107/2107/2109) from `C1_FW_V01.06.0000` (Lightbridge 2). They differ ~55% from each
  other — genuinely different bitstreams, almost certainly the AD9363+Cyclone-V vs
  Artosyn-ASIC board revisions.
- **A second, independent air-FPGA sample corroborates the unidentified-die finding.**
  Phantom 3 Advanced (`P3S_FW_V01.01.0008`) carries its own `m1900`, not byte-identical
  to the P3X/Inspire1 image (different SHA-256, different firmware era: v01.01.0008 vs
  v01.11.0020), same header format. Probed against all 7 Mistral dies with the same
  result as the P3X image — no die resolves cleanly, resolved-route count climbs with
  device size rather than plateauing. Two independent builds failing identically rules
  out "artifact of one bad image" as an explanation; the air die really is unidentified
  from the bitstream. See GitHub issue #3 for the full probe data.
- **`m2001` is the standout and the best decompile candidate.** Entropy **5.84** vs ~7.99
  for the rest, with less "used" span — i.e. **much less compressed/packed**, closest to a
  plain bitstream. It is the easiest to feed to Project Mistral or to de-pack, far more
  tractable than the near-max-entropy air image.

## Mistral decompile of `m2001` (actually run)

De-packed `m2001` (strip leading/trailing `0xFF`; payload starts at `0x20`, first byte
`0x6a`) and loaded it into Project Mistral (built from source) against model
`5CEBA4U19C8` (same `e50f` die, idcode `2b05`, as the documented ground FPGA
`5CEFA4U19I7`). Result — a genuine fabric-level decompile:

- **56,337 fully-resolved routing connections** (real endpoints, e.g.
  `LAB.026.023.5:FFB1L -> LAB.026.023.9:C`, `DSP.008.001:RESULT.46 -> H6...`).
- Block inventory: **~1,795 LABs**, 6,174 MLAB + 2,588 M10K refs (memories/FIFOs/tables),
  **64 DSP blocks** (multipliers), 1,855 GPIO refs, 314 SCLK, 15 DLL.
- **199 named package I/O pins** (e.g. `Y3`, `W2`, `AA2`) — a recoverable pin map to
  correlate against the AD9363 data port / FX2LP on the board.

The 64 DSP multipliers + M10K RAMs + DLLs are exactly an OFDM modem datapath (FFT/filter/
FEC + buffers + sample-clock timing). This confirms `m2001` is a real, **unencrypted,
de-packable** Cyclone-V bitstream that decompiles to structure.

**Limit:** the full `decomp` to `.bt` came out empty — some global routing nodes
(`GOUT`) are unresolved and, per Mistral's README, **DSP/M10K internal configuration is
not decoded**. So we recover **connectivity + block placement + pin map**, not the
block-internal math (multiplier modes, RAM contents). Structure, not the modem's
arithmetic. (Reproducible: `mistral-cv routes 5CEBA4U19C8 m2001.depack.bin`.)

## What's missing

- The **Artosyn-ASIC** board revision has no FPGA bitstream (its logic is hardened into
  the AR8001 ASIC — see `control-plane-re.md`).
- Exact FPGA part per image is unconfirmed (ground board is documented as Cyclone V
  `5CEFA4`; the air part is unlabelled). `m2001`'s lower entropy may indicate a different
  device/encoding and is the one to identify first.
