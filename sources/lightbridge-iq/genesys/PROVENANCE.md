# GENESYS Hovering UAVs RF Fingerprinting Dataset — provenance

**Dataset:** "Non-standard Waveforms from Hovering Unmanned Aerial Vehicles (UAVs) Dataset"
(internally named `UAV-M100-Hovering`), GENESYS Lab, Northeastern University. Soltani, Nasim;
Reus-Muns, Guillem; Salehi, Batool; Dy, Jennifer; Ioannidis, Stratis; Chowdhury, Kaushik, "RF
Fingerprinting Unmanned Aerial Vehicles with Non-standard Transmitter Waveforms," IEEE
Transactions on Vehicular Technology, Nov. 2020.

Landing/description page: https://genesys-lab.org/hovering-uavs — links to the Northeastern
DRS (Digital Repository Service) item `UAV DJI M100 transmissions`
(permanent URL `http://hdl.handle.net/2047/D20381767`,
https://repository.library.northeastern.edu/files/neu:gm80mh71q).

7 real DJI Matrice 100 UAVs, flown one at a time in an RF anechoic chamber at {6, 9, 12, 15} ft
from an **Ettus USRP X310 + UBX-160** receiver, **10 MS/s, center frequency 2406.5 MHz**. Per
the dataset's own per-transmission JSON metadata, `"core:protocol": "Lightbridge"` —
**this is the one dataset of the three fetched here that the source itself labels
Lightbridge.** ~13,893 transmissions (`.bin` + `.json` pairs in SigMF-derived format,
`float16`/`cf16_le` interleaved I/Q, NOT the raw USRP native sample format — already
converted/typed by the dataset authors).

## File fetched

| File | Size | SHA-256 |
|---|---|---|
| `UAV-M100-Hovering.zip` | 4,738,043,740 bytes (4.41 GiB, matches the 4.4GB listed in the DRS item metadata) | `974e41e34cf3f811ca8d7a3966a6d26451d123b3241a63fe539155a388a1991c` |

Verified: zip entry count 27,787 files, `zipfile.testzip()` clean (no CRC errors) — confirms
the archive is complete and not truncated, since exact byte-for-byte MD5/SHA-256 wasn't
published by the source to check against.

## How it was found and fetched (worth recording — this one has no static download link)

The DRS item page only exposes a "Zip File / Add to download queue" UI control, not a plain
`<a href>` — the real download endpoint
(`https://repository.library.northeastern.edu/downloads/neu:m046p309d?datastream_id=content`)
is a **different internal object id** (`neu:m046p309d`) than the item's own id
(`neu:gm80mh71q`), only discoverable by reading the rendered page's DOM
(`document.querySelectorAll('a')` in a real browser — a plain `curl`/`WebFetch` GET of the page
HTML does not contain it, and the endpoint itself 403s without a live DRS session cookie).

Fetched via `playwrong`'s browser-mediated `download` (not plain curl — curl got 403 with no
session). **The transfer was very flaky**: repeated attempts aborted mid-stream at random
points from 0 bytes up to ~4.4 GB (various `TypeError: Failed to fetch` / idle-timeout / abort
errors — looked like server- or proxy-side connection drops on this specific host, not a
client-side problem), with each retry restarting from 0 rather than resuming. It took roughly a
dozen retries over ~1.5 hours before one attempt completed to the exact expected byte count.
Re-fetching this one may need the same persistence.

## Caveat on "Lightbridge" label

The per-file JSON metadata's `"core:protocol": "Lightbridge"` field is the dataset authors'
own characterization, not independently re-verified here (no decode attempted — out of scope
per CLAUDE.md, "acquisition + cataloguing only"). Still the strongest lead of the three
datasets in `sources/lightbridge-iq/` for awto-dji#71's actual PHY question.
