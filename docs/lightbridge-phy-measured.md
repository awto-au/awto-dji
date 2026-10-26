# Lightbridge PHY — measured from public IQ captures (awto-dji#71)

Receive-only measurement. No decode, no TX. Tags: **V** measured here, **I** inferred, **U** unknown.

## Inputs

- Zenodo DOI `10.5281/zenodo.4264467` (Tampere Univ., anechoic chamber): int16 IQ; 2.44 GHz @ 120 MS/s, 5.8 GHz @ 200 MS/s.
  - Local copy, MD5 table: `sources/lightbridge-iq/zenodo/PROVENANCE.md` (not in git).
  - SHA-256 `DJI_matrice_100_2G.bin` = `5a821fe296699fb0c03e81257236efca5d0d297fbb0ea73fc2e749d7bbc6f673`.
- First 280 ms (2^25 samples) of each file at 2.4 GHz; first 168 ms at 5.8 GHz.
- Measured 2026-10-26, script `scripts/re/lightbridge_ofdm_params.py` (commit with this doc).
- No Phantom 3 capture exists yet. **Matrice 100 = original Lightbridge, the closest proxy for the P3 link (I)**.

## Reproduce

```
python3 -I scripts/re/lightbridge_ofdm_params.py sources/lightbridge-iq/zenodo/DJI_matrice_100_2G.bin \
    --fs 120e6 --max-bursts 20 --pilots --min-bw-mhz 5 --max-bw-mhz 30
```

- Log: `tmp/logs/lightbridge_ofdm_params_<stem>.log`; JSON + spectrogram/constellation PNGs in `tmp/`.
- 5.8 GHz files: `--fs 200e6`. Narrowband uplink: `--max-bw-mhz 3`.

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

- Lightbridge-family numerology (10937.5 Hz, CP 1/8, 14 ms frame, hopping ~1.4 MHz second link) is shared by M100, P4, P4P+, Inspire 2, M210, on both bands.
- Only the M100 has the DC null and the 9-carrier pilot grid; later models change the carrier map. **P3 is expected to match the M100 generation (I)**.
- Mavic Pro (OcuSync 1): 15 kHz spacing, Tsym = 1 ms / 14 = LTE normal-CP numerology, ~18 MHz occupied (= LTE 20 MHz, 1200 x 15 kHz). **V** for spacing/Tsym; LTE frame not tested.

## Against the P3 firmware (`docs/phy-params.md`)

- P3 `m0900` AD9363 config: 11.2 MS/s RX/TX, ~10 MHz channel. M100 air numerology: 1024 x 10937.5 Hz = 11.2 MS/s, 864 x 10937.5 Hz = 9.45 MHz occupied. Consistent. **I** (P3 not captured; Fref 40 MHz still inferred, now supported).
- P3 channel table: 39 ch, 2404-2480 MHz, 2 MHz step. M100 second-link hops: 2 MHz grid, 2404-2476 MHz if the capture centre is 2440 MHz. Consistent. **I**.
- Patent CN110046591B simulation (9.3 kHz, CP 128): rejected for every Lightbridge-family capture here (no correlation at the 9.3 kHz lag; CP 1/8 not 128/1024).

## WiMAX (Intel 6250) implications

- Numerology = 802.16e 10 MHz profile exactly (1024 FFT, 11.2 MS/s, CP 1/8, 102.857 us). **V**.
- Not 802.16e framing: 14 ms frame vs 5 ms; no 1-in-3 preamble in the first burst symbols; CW lead-in tone instead. **V** (preamble test covers the first 3 FFT symbols after the spectrogram burst edge, +-20 us).
- So a stock WiMAX receiver would not acquire L1 sync from the preamble. **I**. Only raw post-FFT capture modes (if the 6250 firmware exposes them) could help.

## Open

- P3's own link: needs an SDR capture of the owned aircraft (2.4 GHz, >= 20 MS/s around the active channel).
- Data modulation / STC: decode the pilot sequence, test Alamouti on symbol pairs.
- Second link CP and carrier map: needs a narrowband-specific pass (decimate first).
- Absolute frequencies: capture centre assumed 2440 MHz from the dataset description.
- Genesys M100 (10 MS/s float16) and KU Leuven (100 MS/s, Inspire 2 / M300 / Mini 2) not yet run.
