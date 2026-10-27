# Zenodo drone RF recordings — provenance

**Dataset:** "Radio-Frequency Control and Video Signal Recordings of Drones", Vuorenmaa,
Marin, Heino, Turunen, Riihonen (Tampere University), contributor Pärlin (Rantelon).
Published 2020-11-05, version 1.0.1. DOI `10.5281/zenodo.4264467`.
Landing page: https://zenodo.org/records/4264467

IQ-baseband recordings of 10 consumer/prosumer drones' RC and video links, interleaved
`I1 Q1 I2 Q2 ...` 16-bit signed integer little-endian. Recorded at 2.44 GHz (120 MS/s, 1 s /
120e6 samples) and 5.8 GHz (200 MS/s, 0.5 s / 100e6 samples) in Tampere University's anechoic
chamber. **Not labelled "Lightbridge" by the source** — see caveat in the parent
`sources/lightbridge-iq/PROVENANCE.md`.

Fetched 2026-10-26. Direct per-file HTTPS GET from `zenodo.org/records/4264467/files/<name>?download=1`
worked with plain `curl` — no browser/JS wall on this host.

## Scope: DJI-only subset fetched

Only the `DJI_*` files were fetched (per awto-dji#71's "DJI RF recordings" framing) plus the
small helper scripts. **Not fetched** (non-DJI, out of scope): `Parrot_disco_2G.bin`,
`Parrot_mambo_control_2G.bin`, `Parrot_mambo_video_2G.bin`, `Yuneec_typhoon_h_2G_1of2.bin`,
`Yuneec_typhoon_h_2G_2of2.bin`, `Yuneec_typhoon_h_5G.bin` — re-fetch from the landing page above
if ever needed.

## Files fetched (13 data files + 4 helper scripts, 5.4 GB total)

All verified by MD5 against the values published on the Zenodo record page.

| File | Size | MD5 |
|---|---|---|
| `DJI_inspire_2_2G.bin` | 480.0 MB | `d586a4e636b5cfe6a835d92244d9925e` |
| `DJI_inspire_2_5G_1of2.bin` | 400.0 MB | `6806bffcb38d5af875dd5a35057289cd` |
| `DJI_inspire_2_5G_2of2.bin` | 400.0 MB | `c70d16b1923a571b8af558aca67ff603` |
| `DJI_matrice_100_2G.bin` | 480.0 MB | `3ce47fcb11ff2631961190b5a7b47824` |
| `DJI_matrice_210_2G.bin` | 480.0 MB | `064dc1c4b9cb7a33c67b42faa3687906` |
| `DJI_matrice_210_5G_1of2.bin` | 400.0 MB | `d1814a61cc44bde770f47d0d933ca364` |
| `DJI_matrice_210_5G_2of2.bin` | 400.0 MB | `8a95594363d81a64a9355a748f2b2675` |
| `DJI_mavic_mini_2G.bin` | 480.0 MB | `5d958277d2fbafe9ee4dcdce3b4636e1` |
| `DJI_mavic_pro_2G.bin` | 480.0 MB | `607de5f2fc6327a3e7b11b7185e0fcc8` |
| `DJI_phantom_4_2G.bin` | 480.0 MB | `2afe41e9da4624eb9ed71f901cfa3d78` |
| `DJI_phantom_4_pro_plus_2G.bin` | 480.0 MB | `be8aaf95af313b612964958594d85bae` |
| `DJI_phantom_4_pro_plus_5G_1of2.bin` | 400.0 MB | `d6b8cddbb87344385b1f8118a295ee5b` |
| `DJI_phantom_4_pro_plus_5G_2of2.bin` | 400.0 MB | `609480608b5e3140a89b8f6523ab1209` |
| `example.m` | 834 B | `937a41f1bf74947fbe9057bc32116932` |
| `example.py` | 1.0 kB | `14259ce71abfa799fffd6b792735a669` |
| `load_bin.m` | 1.0 kB | `7be757ed0e2211cd1c55e561a2cbb9e0` |
| `load_bin.py` | 641 B | `ad0066ba5022943d62572493a86d889d` |

`*_1of2`/`*_2of2` pairs are split halves of one continuous recording (per the dataset
description) — concatenate in order to reconstruct the full capture.

## How to verify a good copy

`md5sum -c` against the table above, or re-derive from the Zenodo page
(https://zenodo.org/records/4264467 lists the same MD5s per file). `example.py`/`load_bin.py`
(from the dataset) parse the interleaved int16 I/Q format.
