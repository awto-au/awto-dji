# Lightbridge/drone RF IQ capture datasets — provenance

Public SDR IQ captures of DJI (and other-vendor) drone RF links, gathered to actually feed
`analyze_iq.py` (issue #71 / PR #62 — the Intel WiMAX 6250 PHY-diagnostics comparison) instead
of just cataloguing where such data exists. Same non-storage convention as
`sources/dji-fpga-images/PROVENANCE.md`: **only this file and the per-dataset PROVENANCE.md
files are tracked**; the binaries under this directory are git-ignored (root `.gitignore`).
Re-fetch and verify by MD5/SHA-256 to reproduce — see each dataset's own PROVENANCE.md for its
checksums.

Scope: acquisition + cataloguing only, per CLAUDE.md. No decode/decrypt/analysis here.

## Important caveat — none of this is an actual DJI Lightbridge OFDM-modem capture

Re-reading what each dataset actually recorded, **only the GENESYS set is labelled
"Lightbridge" by its own creators**, and even that label needs a caveat (below). The Zenodo
and KU Leuven sets are RC/video-link captures, not confirmed Lightbridge-protocol OFDM
captures:

- **`genesys/`** — labelled `"protocol": "Lightbridge"` in the dataset's own per-file metadata,
  captured from 7 real DJI Matrice 100 UAVs at 10 MS/s centered on 2406.5 MHz. This is the one
  directly relevant to awto-dji#71's Lightbridge-PHY question. Caveat: SigMF `float16`
  (`cf16_le`), not the raw USRP native format — already processed/typed by the dataset authors,
  not a bit-exact raw front-end dump.
- **`zenodo/`** — Tampere University's drone **RC/video link** recordings (DJI Matrice 100,
  Phantom 4, Phantom 4 Pro+, Inspire 2, etc.) at 2.44/5.8 GHz, 120/200 MS/s, 16-bit signed
  interleaved I/Q. The dataset description does not use the word "Lightbridge" anywhere — it's
  framed generically as "radio-control and video signal recordings." Whether these DJI models'
  control/video link at these frequencies **is** Lightbridge (vs. OcuSync, which supersedes it
  on Mavic/Phantom4-class aircraft) is unconfirmed by the source; flagged here, not resolved.
- **`kuleuven/`** — Royal Military Academy / KU Leuven's drone RF dataset (DJI Mini 2, Inspire
  2, Matrice 300, SJRC F11 Pro, plus several non-DJI RC-only captures), 100 MS/s at 2.44 GHz,
  raw USRP binary → `.mat` (v7.3). Same caveat: no "Lightbridge" label from the source; DJI
  Matrice 300 and Mini 2 may use OcuSync, not Lightbridge.

**Next step for whoever picks this up (issue #71/PR #62):** confirm which of these actually
carry Lightbridge's OFDM waveform (vs. OcuSync or plain WiFi) before feeding them to
`analyze_iq.py` expecting Lightbridge PHY parameters — likely by eye on a spectrogram/constellation
(Lightbridge is COFDM; compare against the FPGA-side PHY notes already in `docs/fpga-images.md`).

## Datasets

| Subdir | Dataset | Size on disk (git-ignored) | Status |
|---|---|---|---|
| `genesys/` | GENESYS Hovering UAVs RF Fingerprinting Dataset (Soltani et al., IEEE TVT 2020) | 4.4 GB (1 zip, 27,787 entries) | Complete, zip-integrity-verified (see `genesys/PROVENANCE.md`) |
| `zenodo/` | Tampere University RF Control/Video Signal Recordings of Drones (Zenodo 10.5281/zenodo.4264467), DJI-labelled files only | 5.4 GB | Complete, MD5-verified |
| `kuleuven/` | KU Leuven RDR Drone RF Dataset (Basak/Pollin/Scheers, doi:10.48804/HZRVNZ) — full 19-file collection | 44 GB | Complete, MD5-verified |

Full per-file source URLs, checksums and "how to verify a good copy" are in each subdirectory's
own `PROVENANCE.md`.

## Disk footprint

All three together: ~54 GB. Verify free space before re-fetching — see each PROVENANCE.md for
exact sizes to plan around.
