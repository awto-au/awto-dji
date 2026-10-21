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

## Observations

- **Air FPGA is one shared bitstream.** P3 and Inspire 1 `m1900` are **byte-identical**
  (same SHA, v01.00.2144) — a single 4 MiB compressed TX bitstream across the
  Lightbridge family. (Sources: `P3X_FW_V01.11.0020`, `WM610_FW_V01.11.01.50`.)
- **Ground FPGA has three board-revision variants** (`m2000/01/02`, 8 MiB each, versions
  2107/2107/2109) from `C1_FW_V01.06.0000` (Lightbridge 2). They differ ~55% from each
  other — genuinely different bitstreams, almost certainly the AD9363+Cyclone-V vs
  Artosyn-ASIC board revisions.
- **`m2001` is the standout and the best decompile candidate.** Entropy **5.84** vs ~7.99
  for the rest, with less "used" span — i.e. **much less compressed/packed**, closest to a
  plain bitstream. It is the easiest to feed to Project Mistral or to de-pack, far more
  tractable than the near-max-entropy air image.

## What's missing

- The **Artosyn-ASIC** board revision has no FPGA bitstream (its logic is hardened into
  the AR8001 ASIC — see `control-plane-re.md`).
- Exact FPGA part per image is unconfirmed (ground board is documented as Cyclone V
  `5CEFA4`; the air part is unlabelled). `m2001`'s lower entropy may indicate a different
  device/encoding and is the one to identify first.
