# Lightbridge PHY — measured from public IQ captures (awto-dji#71)

Receive-only measurement. No decode, no TX. Tags: **V** measured here, **I** inferred, **U** unknown.

## Inputs

- Zenodo DOI `10.5281/zenodo.4264467` (Tampere Univ., anechoic chamber): int16 IQ; 2.44 GHz @ 120 MS/s, 5.8 GHz @ 200 MS/s.
  - Local copy, MD5 table: `sources/lightbridge-iq/zenodo/PROVENANCE.md` (not in git).
  - SHA-256 `DJI_matrice_100_2G.bin` = `5a821fe296699fb0c03e81257236efca5d0d297fbb0ea73fc2e749d7bbc6f673`.
- First 280 ms (2^25 samples) of each file at 2.4 GHz; first 168 ms at 5.8 GHz.
- Measured 2026-10-26, script `scripts/re/lightbridge_ofdm_params.py` (commit with this doc).
- No Phantom 3 capture exists yet. **Matrice 100 = original Lightbridge, the closest proxy for the P3 link (I)**.
- GENESYS Lab (Northeastern Univ.) `UAV-M100-Hovering` dataset, `sources/lightbridge-iq/genesys/UAV-M100-Hovering.zip` (4.5 GB, 7 DJI M100s, anechoic chamber, USRP X310 + UBX 160, SigMF). The only dataset here labelled `"protocol": "Lightbridge"` by its own creators.
  - Cite: Soltani, Reus-Muns, Salehi, Dy, Ioannidis, Chowdhury, "RF Fingerprinting Unmanned Aerial Vehicles with Non-standard Transmitter Waveforms," IEEE Trans. Vehicular Technology, 2020.
  - Per-transmission `.sigmf-meta`-equivalent `.json`: `sample_rate: 10000000`, `datatype: cf16_le` (float16 I/Q), `center_frequency` 2406.5/2416.5/2426.5/2436.5/2476.5 MHz depending on UAV/burst. 13893 pre-cut single-transmission `.bin` files, ~98k samples (~9.8 ms) each, no idle gap within a file.
  - Measured 2026-10-27, 24 full-length (~9.8 ms) transmissions spanning all 7 UAVs x 4 distances, concatenated with synthetic 2 ms silence gaps (scratch-only prep, not committed — the burst-finder needs an on/off contrast and each file is pre-trimmed to just the burst) so the existing burst-finder works unmodified. Frame-to-frame timing is **not** measurable from this synthetic concatenation; only per-burst numerology is.
- KU Leuven Research Data Repository, "Drone RF Dataset", DOI `10.48804/HZRVNZ` (Basak, Pollin, Scheers, 2024), `sources/lightbridge-iq/kuleuven/*.zip` (44 GB). Semi-anechoic chamber at the Royal Military Academy (CISS dept.), USRP X310, 10 Gbit Ethernet, OmniLOG 70600 antenna, 7 m standoff. Per the dataset's own page (no README/`.m` helper ships inside these particular zips — checked, none present): **IQ at 100 MS/s, fixed tuned centre 2.44 GHz**, `.mat` v7.3 (`uhd_samps`, compound real/imag `float64`), ~20 M complex samples (200 ms) per file for most models, 100 M (1 s) per file for the Mavic archives.
  - `MavicVid1.zip`/`MavicVid2.zip` have padding that makes the classic `unzip` CLI report "zipfile corrupt" (central directory not found) — Python's `zipfile` module reads them fine; used that instead.
  - Measured 2026-10-27, one `.mat` file (200 ms or 1 s) per DJI model/link: `inspire2Vid_0`, `inspire2RC_0`, `matricevid_0`, `matriceRC_0`, `mini2vid_0`, `mini2RC_0`, `MavicVid1_0`, `MavicRC1_0`. The dataset's "Matrice" and "Mavic" archives don't specify the exact model variant.

## Reproduce

```
python3 -I scripts/re/lightbridge_ofdm_params.py sources/lightbridge-iq/zenodo/DJI_matrice_100_2G.bin \
    --fs 120e6 --max-bursts 20 --pilots --min-bw-mhz 5 --max-bw-mhz 30
```

- Log: `tmp/logs/lightbridge_ofdm_params_<stem>.log`; JSON + spectrogram/constellation PNGs in `tmp/`.
- 5.8 GHz files: `--fs 200e6`. Narrowband uplink: `--max-bw-mhz 3`.
- GENESYS M100 needs `--dtype f16` (float16, added for this run) and the synthetic-gap concatenation described above:
  `python3 -I scripts/re/lightbridge_ofdm_params.py <concatenated.bin> --fs 10e6 --dtype f16 --max-bursts 24 --min-burst-ms 1 --pilots`
- KU Leuven needs `--dtype f64` (float64, added for this run) on a raw interleaved-double file converted from the `.mat`'s `uhd_samps` (`h5py`, not `scipy.io` — these are v7.3/HDF5):
  `python3 -I scripts/re/lightbridge_ofdm_params.py <converted.f64> --fs 100e6 --dtype f64 --max-bursts 15 --min-bw-mhz 0.3 --max-bw-mhz 30`

## Method

- Spectrogram (117 kHz x 20 us cells, floor + 10 dB) -> bursts, centre, -20 dB width.
- Per burst: mix + low-pass -> CP lag correlation, fractional peak -> useful length Tu.
- Cyclic spectrum of the lag-Tu product -> symbol period T; CP = T - Tu; cross-checked by folding at T (plateau width).
- Resample to 1024 samples per Tu, strip CP, FFT -> occupied bins (> p90 - 10 dB), integer-offset re-centring.
- Pilots: BPSK^2 coherence of X[m,k] X*[m+lag,k] per residue k mod 9.

## Matrice 100 (original Lightbridge), 2.4 GHz — V

| Parameter | Value | n / spread |
|---|---|---|
| Subcarrier spacing | 10937.50 Hz = 11.2 MS/s / 1024 | 20 bursts, std 0.04 Hz |
| CP | 1/8 Tu (1372 of 10971 samples @ 120 MS/s; fold plateau 1369-1372) | std < 0.0001 |
| Symbol time | 102.859 us (1152 samples @ 11.2 MS/s) | std 0.002 us |
| Used carriers | 864, k = -432..+432, DC null (-12 to -13 dB) | all 20 bursts |
| Guard bins (1024 grid) | 80 low, 79 high | |
| Pilots | 96/symbol, one per 9 carriers; residue (k+432) mod 9 = 5,5,8,8,2,2 repeating (6-symbol period, each position held 2 symbols); no power boost (+0.5 dB) | BPSK^2 coherence 0.87-0.92 vs 0.13-0.20 off-pilot |
| First symbols of burst | power split ~1/3 per k mod 3 | no 802.16e-style 1-in-3 preamble |
| Video burst | 9.98 ms, ~97 symbols, fixed centre (+16.5 MHz from capture centre = 2456.5 MHz if centre is 2440 MHz) | 20 bursts |
| Frame | burst starts every 14.000 ms | 20 bursts |
| Lead-in | narrow CW tone ~0.16 ms before each video burst, same centre | spectrogram |
| Second link | 2.2 ms, ~1.4 MHz bursts in the gap between video bursts, a new centre each frame on a 2 MHz grid within +-36 MHz; ~1 ms CW tone at the same centre first | 20 bursts |
| Second link spacing | 10938-10944 Hz; CP 0.13-0.14 Tu, T-line only 3-4x median | CP **U** (weak) |

- 864 used / 80+79 guard / DC null = the IEEE 802.16e 1024-FFT AMC carrier set (768 data + 96 pilots). **I** (layout match; WiMAX AMC pilot placement differs in detail).
- Data constellation: not resolved. Data / nearest same-symbol pilot gives |E r^4|/E|r|^4 = 0.17 (Gaussian 0, QPSK 1.0) — square-QAM present but smeared. Paired pilot positions fit 2-TX STC on symbol pairs. **U**.

## GENESYS M100 (the one dataset actually labelled "Lightbridge"), 2.4 GHz — V

24 full-length transmissions (7 UAVs x 4 distances), synthetic concatenation (see Inputs). 14/24 passed the z>8 and T-line-SNR>8 gate used for the summary stats below.

| Parameter | Value | n / spread |
|---|---|---|
| Subcarrier spacing | 10939.32 Hz | 14 bursts, std 0.11 Hz |
| CP | 0.1253 Tu (~1/8) | std 0.0002 |
| Symbol time | 102.87 us | std 0.02 us |
| Burst bandwidth (-20 dB) | 9.47 MHz | matches Zenodo M100's 9.45 MHz |
| Occupied bins (1024-bin grid) | mean 923 (vs Zenodo M100's 864) | see caveat below |
| Burst duration | up to 9.78 ms (full transmissions); dataset's own capture already trims to the burst, so frame period (14 ms) is not observable here | 24 bursts |
| First symbols | power split ~1/3 per k mod 3 | no 1-in-3 preamble, same as Zenodo |

- Core numerology (df, CP ratio, Tsym) matches the Zenodo-derived Matrice 100 numbers to within 0.02%, from a completely independent capture setup (different lab, receiver, year, sample rate, 7 different physical M100 units). The ~1.8 Hz df offset from 10937.50 Hz is consistent with ordinary USRP clock ppm error, not a protocol difference. **V — strongest confirmation in this doc that Lightbridge-labelled traffic is this numerology.**
- Occupied-bins-1024 (923 vs Zenodo's 864) is **not** read as a carrier-count difference: GENESYS's 10 MS/s capture rate is barely above the channel's own ~9.45-9.6 MHz occupied bandwidth, so `channelise()`'s anti-alias filter cutoff pins near Nyquist (near-zero margin) and FFT-edge artifacts inflate the "occupied" count; the actual RF bandwidth (-20 dB spectrogram measurement, independent of the 1024-bin resampling) agrees with Zenodo to within 0.2 MHz. **U** for the bin-count metric specifically on this dataset; **V** for bandwidth.
- Constellation/pilot search on this dataset was unreliable (per-transmission SNR varies hugely with the 6-15ft distance sweep; E|r|^4/E|r|^2^2 came out 6-12, above even the Gaussian reference of 2.0) — not included as a finding, data modulation stays **U** per the open items below.

## KU Leuven Drone RF Dataset, 2.44 GHz fixed-tuned — V (Lightbridge family) / V (divergence)

One 100 MS/s `.mat` segment (200 ms, or 1 s for Mavic) per DJI model/link, no concatenation needed (each segment already spans several real frame periods).

**Inspire 2 — matches Lightbridge, cross-validates the Zenodo numbers from an unrelated capture:**

| Parameter | KU Leuven (video) | Zenodo "Inspire 2 2G" (existing row) |
|---|---|---|
| df | 10937.56 Hz (std 0.13, n=15) | 10937.53 Hz |
| CP | 0.1249 Tu (std 0.0001) | 1/8 |
| Tsym | 102.85 us (std 0.009) | 102.86 us |
| Occupied bins | 866 (std 0, n=15) | 865 |
| Video burst | 9.76-9.78 ms | 9.78 ms |
| Frame | 14.000 ms start-to-start | 14 ms |

- Independent receiver, dataset, year, and physical aircraft from the Zenodo capture — agreement to 4 significant figures on df is strong corroboration, not coincidence. **V**.
- Fixed video centre at tuned-centre -33.5 MHz = 2406.5 MHz — the same 2406.5 MHz GENESYS logged for several M100 transmissions above, consistent with both being inside DJI's low channels. **I**.
- **Second-link cross-validation**: the Inspire 2 RC/control capture shows the same hopping-narrowband signature as the Zenodo M100 "second link" row above, on a different model and dataset: 7 candidate bursts, ~2.2 ms duration, 1.27-1.37 MHz bandwidth, hopping centre in ~1.4-1.7 MHz steps across +-39 MHz, df 10938-10942 Hz, CP ratio 0.122-0.131, T-line SNR only 3-4x median (same "weak CP" signature noted for Zenodo). None individually cleared the z>8/T>8 gate (too short for a stable average) but the per-burst numbers line up with the existing row to within noise. **V** for existence/timing/hop-step match, CP stays **U** (weak) as before.
- A weak (~20 dB below the video burst), short (<1 ms), ~1 MHz signal was also seen hopping at +-47..50 MHz in the Inspire 2 video capture — too weak to extract numerology from this file; not pursued further.

**Matrice (unspecified variant) and Mavic (unspecified variant) — do NOT match Lightbridge, match the existing "Mavic Pro" OcuSync-family row instead:**

| Parameter | Matrice (KU Leuven, video) | Mavic (KU Leuven, video) | Existing "Mavic Pro 2G" row |
|---|---|---|---|
| df | 15000.25 Hz (std 0.30, n=15) | 15000.12 Hz (std 0.22, n=15) | 15000.0 Hz |
| CP | 0.0717 Tu (~1/14) | 0.0713 Tu (~1/14) | 1/14 |
| Tsym | 71.44 us | 71.42 us | 71.43 us |
| Occupied bins | 1024 (full span, no guard/null) | 1024 (full span) | >1024-grid, ~18 MHz |
| -20 dB bandwidth | 18.07 MHz | 18.16 MHz | ~18 MHz |
| Fixed centre | +10 MHz (2.45 GHz) | varies | — |

- Both match the LTE-normal-CP / OcuSync numerology already in the Fleet table for Mavic Pro, **not** the 10937.5 Hz / CP-1/8 Lightbridge family. **V**.
- This is a genuine surprise for "Matrice": the existing assumption (Matrice 100/210 = Lightbridge) does not hold for whatever Matrice variant this unlabelled KU Leuven sample is. The dataset's zip only says "matrice", no model/XML sidecar. Most likely explanation: a newer, OcuSync-equipped Matrice (e.g. M300 RTK) rather than the M100/M210 captured by Zenodo — the 2022 recording date fits a newer platform being on hand. **I**.
- Matrice RC and Mavic RC captures show short (<1.2 ms), narrowband (~0.1-1.2 MHz) frequency-hopping bursts at fixed or widely-spread offsets; none cleared the OFDM-measurement gate (too short for the CP-correlation method here). Inconclusive on numerology, consistent with either an OcuSync uplink or a weak Lightbridge-style second link. **U**.

**Mini 2 — neither a sustained Lightbridge video burst nor the Mavic-style numerology; FHSS-like:**

- Both the video and RC captures show many (43-84) short (0.1-1.1 ms) narrowband bursts hopping across +-50 MHz, concentrated at a couple of favoured offsets (e.g. -27 MHz, -40 MHz) but spread widely — no ~9.5-10 ms continuous wideband OFDM video burst of the kind every Lightbridge-family capture shows. No burst cleared the OFDM-measurement gate. **V** for "not Lightbridge's sustained-burst behaviour"; exact protocol stays **U**.
- Consistent with the existing Fleet row for "Mavic Mini 2G" (also narrowband/hopping, not OFDM-measured) — Mini 2 behaves the same way as Mavic Mini here, both outside the Lightbridge family. **I**.

## Fleet comparison (wideband bursts, 6 per file) — V

| Capture | df (Hz) | CP | Tsym (us) | Used bins | DC null | 9-grid pilots | Frame |
|---|---|---|---|---|---|---|---|
| Matrice 100 2G | 10937.50 | 1/8 | 102.86 | 864 | yes | yes | 14 ms, 9.98 ms video |
| Phantom 4 2G | 10937.44 | 1/8 | 102.86 | 866 | no | no | 14 ms, 9.78 ms |
| Phantom 4 Pro+ 2G | 10937.41 | 1/8 | 102.86 | 866 | no | no | 14 ms |
| Phantom 4 Pro+ 5.8G | 10937.52 | 1/8 | 102.86 | 865 | no | no | 14 ms |
| Inspire 2 2G | 10937.53 | 1/8 | 102.86 | 865 | no | no | 14 ms, 10.2 ms |
| Inspire 2 5.8G | 10937.45 | 1/8 | 102.87 | 865 | no | no | 14 ms |
| Matrice 210 2G | 10937.34 | 1/8 | 102.86 | 866 | no | no | 14 ms |
| Matrice 210 5.8G | 10937.32 | 1/8 | 102.87 | 866 | no | no | 14 ms |
| Mavic Pro 2G | 15000.0 | 0.0714 (1/14) | 71.43 | > 1024-grid (18 MHz wide) | — | — | ~5 ms bursts |
| Mavic Mini 2G | — | — | — | 4.3 MHz, 0.2 ms bursts | — | — | not OFDM-measured |
| GENESYS M100 2.4G | 10939.32 | 0.1253 (~1/8) | 102.87 | 923 (edge-filter caveat, see above) | — | not tested | timing not observable (pre-cut bursts) |
| KU Leuven Inspire 2 2.44G | 10937.56 | 0.1249 (1/8) | 102.85 | 866 | not tested | not tested | 14 ms, 9.76-9.78 ms video |
| KU Leuven Matrice (variant unspecified) 2.44G | 15000.25 | 0.0717 (~1/14) | 71.44 | 1024 (full span) | — | — | not OFDM-measured (RC); 18.07 MHz video |
| KU Leuven Mavic (variant unspecified) 2.44G | 15000.12 | 0.0713 (~1/14) | 71.42 | 1024 (full span) | — | — | not OFDM-measured (RC); 18.16 MHz video |
| KU Leuven Mini 2 2.44G | — | — | — | not OFDM-measured, 0.1-1.1 ms hopping bursts | — | — | not OFDM-measured |

- Lightbridge-family numerology (10937.5 Hz, CP 1/8, 14 ms frame, hopping ~1.4 MHz second link) is shared by M100, P4, P4P+, Inspire 2, M210, on both bands — and now cross-validated from two more independent datasets/receivers: GENESYS M100 and KU Leuven Inspire 2 (see above). **V**.
- Only the M100 has the DC null and the 9-carrier pilot grid; later models change the carrier map. **P3 is expected to match the M100 generation (I)**.
- Mavic Pro (OcuSync 1): 15 kHz spacing, Tsym = 1 ms / 14 = LTE normal-CP numerology, ~18 MHz occupied (= LTE 20 MHz, 1200 x 15 kHz). **V** for spacing/Tsym; LTE frame not tested. The KU Leuven "Matrice" (variant unspecified) and "Mavic" (variant unspecified) captures both land in this same OcuSync-family bucket, not the Lightbridge one — so "Matrice = Lightbridge" does not hold across the whole Matrice line, only the M100/M210 generation tested here. **V/I**, see KU Leuven section above.

## Against the P3 firmware (`docs/phy-params.md`)

- P3 `m0900` AD9363 config: 11.2 MS/s RX/TX, ~10 MHz channel. M100 air numerology: 1024 x 10937.5 Hz = 11.2 MS/s, 864 x 10937.5 Hz = 9.45 MHz occupied. Consistent. **I** (P3 not captured; Fref 40 MHz still inferred, now supported).
- P3 channel table: 39 ch, 2404-2480 MHz, 2 MHz step. M100 second-link hops: 2 MHz grid, 2404-2476 MHz if the capture centre is 2440 MHz. Consistent. **I**.
- Patent CN110046591B simulation (9.3 kHz, CP 128): rejected for every Lightbridge-family capture here (no correlation at the 9.3 kHz lag; CP 1/8 not 128/1024).
  - **Correction (2026-10-27):** the patent itself is real and granted (Guilin University of Electronic Technology; verified via Google Patents) — but its subject is a signal-classification algorithm (a fractional-wavelet-transform method for distinguishing drone video/control signals from other RF in a noisy environment), not DJI protocol reverse-engineering. Its OFDM numbers were simulation inputs for testing that unrelated classifier, never claimed as measured Phantom-3 values. That's exactly why they don't match any real capture here — not evidence the patent is fake, just irrelevant to this measurement. No further investigation of the patent's authenticity needed.

## WiMAX (Intel 6250) implications

- Numerology = 802.16e 10 MHz profile exactly (1024 FFT, 11.2 MS/s, CP 1/8, 102.857 us). **V**.
- Not 802.16e framing: 14 ms frame vs 5 ms; no 1-in-3 preamble in the first burst symbols; CW lead-in tone instead. **V** (preamble test covers the first 3 FFT symbols after the spectrogram burst edge, +-20 us).
- So a stock WiMAX receiver would not acquire L1 sync from the preamble. **I**. Only raw post-FFT capture modes (if the 6250 firmware exposes them) could help.

## Open

- P3's own link: needs an SDR capture of the owned aircraft (2.4 GHz, >= 20 MS/s around the active channel).
- Dead end (U, one session, not re-run): equalising from a static channel estimate built from all pilots scored a 4th-power coherence of 0.007 on the Zenodo M100 burst, worse than the nearest-pilot reference's 0.17. The script keeps the nearest-pilot version.
- Data modulation / STC: decode the pilot sequence, test Alamouti on symbol pairs. Still unresolved on GENESYS and KU Leuven too — constellation search was unreliable (GENESYS: highly SNR-variable per-transmission distance sweep) or not attempted (KU Leuven: not yet run with `--pilots` on these captures).
- Second link CP and carrier map: needs a narrowband-specific pass (decimate first). Now cross-validated present on two models/datasets (Zenodo M100, KU Leuven Inspire 2) but CP still weak/unresolved on both.
- Absolute frequencies: capture centre assumed 2440 MHz from the Zenodo dataset description; KU Leuven's is confirmed 2.44 GHz from its own metadata page.
- KU Leuven "Matrice" and "Mavic" exact model variants are unknown (zip/filename only, no XML/model sidecar in these DJI archives) — confirmed OcuSync-family numerology either way, but which specific Matrice/Mavic SKU is unconfirmed.
- KU Leuven Mini 2, and the Matrice/Mavic RC links: bursts too short (<1.2 ms) for this script's CP-correlation method to extract numerology — would need a method tuned for very short frequency-hopping bursts.
- GENESYS M100 and KU Leuven (Inspire 2 / Matrice / Mavic / Mini 2) — run 2026-10-27, see sections above.
