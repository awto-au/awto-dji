# DJI FPGA firmware images — provenance

More Lightbridge-generation firmware containers, fetched to get more data points for the
FPGA config-flash writer gap (issue #18). Same non-storage convention as `docs/data-manifest.md`:
**only this file is tracked**; the binaries under this directory are git-ignored (see root
`.gitignore`). Re-fetch and verify by SHA-256 to reproduce.

Scope (CLAUDE.md): acquisition + cataloguing only. No decode/decrypt/analysis here — see
`docs/fpga-images.md` for the existing family/encryption verdicts on `m1900`/`m2000`-`m2002`.

Module-number convention: `docs/naming-map.md` does not exist in this repo; module roles
below are from the `dji-firmware-tools` wiki (`DJI-Firmwares` page) and this project's own
`docs/fpga-images.md` / `docs/data-manifest.md`.

## Headline correction: air-side `m1900` is NOT one shared bitstream

An earlier pass of this cataloguing (same session) concluded "air FPGA diversity is a dead
end" from only the 2016-04..2017-07 build window. That conclusion was wrong. Going back to
the Phantom 3 Professional's **launch window** (firmware from May 2015, found via the Wayback
Machine — see below) turns up a **second, different** `m1900` bitstream:

| Era | Containers | `m1900` SHA-256 | `m2000`/`m2001` | `m2002` |
|---|---|---|---|---|
| 2015-05-08 .. 2015-05-22 (launch) | `P3X_FW_V01.01.0008`, `P3X_FW_V01.01.0009` | `0ecafe1ab6583407976a561e53b6e62bfe109e12797a80735ef16c6ec4d369e4` | same as later (`39a74d8d...`/`b6cc5e96...`) | **absent** — module not present in container |
| 2015-06-15 (`P3X_FW_V01.02.0006`, v1.2.6) | `P3X_FW_V01.02.0006` | `f3a55dea4dc8c0d4...` — **already the later bitstream** | unchanged | `e6ba9914b74a75aef55fcdf4f47b9cebf97744436be60de515bfd76fdc116198` — **different from later** |
| 2015-08-04 onward (`P3X_FW_V01.03.0020` through `MATRICE100_FW_V01.03.01.00`/2017-07) | everything else in this file + `docs/fpga-images.md` | `f3a55dea4dc8c0d4...` | unchanged | `30aa24c31e5180a7...` — the known later revision |

So between **2015-05-22** and **2015-06-15** (3 weeks, not the 10-week window previously
stated) DJI replaced the air-side OFDM FPGA bitstream *and* added the third ground-FPGA board
revision (`m2002`) — a real hardware/bitstream generation boundary early in the Phantom 3 Pro's
life. `m2002` then changed again between 2015-06-15 and 2015-08-04. The ground FPGA
(`m2000`/`m2001`) did **not** change across either boundary.
This reopens the air side as a genuine comparison target for issue #18: the 2015-05 `m1900`
(`0ecafe1a...`) has never been compared against the later one (`f3a55dea...`) beyond a hash
diff — same next step as the ground-side pairs in `docs/fpga-images.md`.

## Containers fetched (new to this repo)

| Container (as downloaded) | Product | Source URL | Fetched | SHA-256 (download) |
|---|---|---|---|---|
| `Phantom_3_Professional_Firmware_v1.2.6_en.zip` | Phantom 3 Pro (2015-06-15 build — fills the boundary window) | Wayback Machine: `https://web.archive.org/web/20160114113028id_/http://download.dji-innovations.com/downloads/phantom_3/en/Phantom_3_Professional_Firmware_v1.2.6_en.zip` (CDX verified, same WARC digest as 2026-02-15 recrawl; live URL is 404) | 2026-10-28 | `b547f3e066bf419df4770d7e3166c29501db7bdeee241cfd33a3262005e78cf6` |
| `C1_FW_V01.00.0004.bin` | Lightbridge 2 ground controller, 2015-09-22 — earliest `m2000` revision | `https://dl.djicdn.com/downloads/lightbridge2/C1_FW_V01.00.0004.bin` (AWS S3/CloudFront, still live 2026-10-28) | 2026-10-28 | `76e7b56e4c3be02f83ff35b2ac7318b3e7448539226b92104169e5bda998bc45` |
| `C1_FW_V01.00.0010.bin` | Lightbridge 2 ground controller, 2015-11-19 — second `m2000` revision | `https://dl.djicdn.com/downloads/lightbridge2/C1_FW_V01.00.0010.bin` (AWS S3/CloudFront, still live 2026-10-28) | 2026-10-28 | `8be4ecf85a59edd7a7779d94c58944114778b3a652c7343ceccc061451fcc81a` |
| `P3A_FW_V01.11.0020.bin.zip` | Phantom 3 Advanced (DJI download-center internal name: P3S) | `https://dl.djicdn.com/downloads/phantom_3/20170706/P3A_FW_V01.11.0020.bin.zip` | 2026-10-26 | `0f24ac1341056522918da64961fe01115e5145a5a74478ee1050f31317384986` |
| `P3C_FW_V01.09.0200.bin.zip` | Phantom 3 Standard | `https://dl.djicdn.com/downloads/phantom_3_standard/20170629/P3C_FW_V01.09.0200.bin.zip` | 2026-10-26 | `d5d2a36070fa408ea98f9c5baa38a4af1d1e8418beed799b02a5363948a1d298` |
| `MATRICE100_FW_V01.03.01.00.zip` | Matrice 100 | `https://dl.djicdn.com/downloads/dev/Matrice/MATRICE100_FW_V01.03.01.00.zip` | 2026-10-26 | `c92e04ff8a083f5b07875ef7a1d7e1b0ed899bba762610f7c0a1514d8db7415b` |
| `MATRICE100_FLIR_FW_V01.31.00.60.bin` | Matrice 100 + FLIR camera payload | `https://terra-1-g.djicdn.com/b20074248eff4b7f957d0f1a5ab29253/MATRICE100_FLIR_FW_V01.31.00.60.bin` | 2026-10-26 | `1f9e78a4d4a0876c5d52aedcaf3150752c11f4a3cb56accf616973ff29062570` |
| `Phantom_3_Professional_Firmware_v1.3.20__en.zip` | Phantom 3 Pro, "last combined aircraft+RC package" | `https://dl.djicdn.com/downloads/phantom_3/en/Phantom_3_Professional_Firmware_v1.3.20__en.zip` (already recorded in `docs/data-manifest.md`, not previously opened for its `m1900`) | 2026-10-26 | `1e2e587daf55ce46f54872b6caadbc330a2402cb59e71c330d3f1a635ebbfc64` (matches `docs/data-manifest.md`) |
| `Phantom_3_Professional_Firmware_v1.1.8_en.zip` | Phantom 3 Pro, launch-window firmware (built 2015-05-08) | `http://download.dji-innovations.com/downloads/phantom_3/en/Phantom_3_Professional_Firmware_v1.1.8_en.zip` — live URL is gone (old pre-2016 DJI CDN domain); fetched via Wayback Machine: `https://web.archive.org/web/20160307134924id_/<that URL>` (found via Wayback CDX API query, not a guess — see below) | 2026-10-26 | `d1cb1e775bd08fb63a28786eae34b47ef1337bf98410111578c2c3afa0ea796e` |
| `Phantom_3_Professional_Firmware_v1.1.9_en.zip` | Phantom 3 Pro, launch-window firmware (built 2015-05-22) | `http://download.dji-innovations.com/downloads/phantom_3/en/Phantom_3_Professional_Firmware_v1.1.9_en.zip` via Wayback: `https://web.archive.org/web/20160305185109id_/<that URL>` | 2026-10-26 | `6cb53a652689108d09c09fa9b1911167f5c21c3e3b08f8cf1c71683b2b319fcd` |

The first four were found by rendering the DJI download-center product pages for Phantom 3
Advanced/Standard and Matrice 100 (`dji.com/au/downloads/products/<slug>`) in a real browser
and reading the `<a href>` list (the pages are JS-rendered; a plain GET/curl of the page HTML
does not contain these links). Each URL was then verified to resolve with a direct `curl -sI`
(200, matching `Content-Length`) before fetching.

The two 2015 launch-window packages were found differently: the live DJI download-center pages
only ever link the *current* firmware, so the original 2015 URLs (on DJI's pre-2016
`download.dji-innovations.com` domain) are 404 today. They were located with the Internet
Archive's Wayback Machine CDX API — a plain JSON HTTP GET, no browser needed —
`http://web.archive.org/cdx/search/cdx?url=download.dji-innovations.com/downloads/phantom_3*&output=json&limit=5000&from=2014&to=2016`,
which lists every URL under that path the Wayback crawler ever captured, with its snapshot
timestamp and HTTP status. That listing is how `Phantom_3_Professional_Firmware_v1.1.8_en.zip`
and `_v1.1.9_en.zip` (both status 200, real sizes) were identified as real, previously-hosted
files — not guessed. The archived bytes were then fetched with the `id_` Wayback modifier
(returns the raw original response body, not a replay page with injected toolbar/links) and
checked to start with a real ZIP header (`PK\x03\x04`) containing the expected internal
filename before trusting them.

The first six are zips; unzipped they each contain one xV4 container (`dji_xv4_fwcon.py`/
`scripts/re/xv4_extract.py` format, magic `0x12345678`). The FLIR file is itself an unzipped
xV4 container (magic `xV4` visible at offset 0).

| Extracted xV4 container | SHA-256 | Size | Build date (zip mtime) |
|---|---|---|---|
| `P3X_FW_V01.02.0006.bin` (from `Phantom_3_Professional_Firmware_v1.2.6_en.zip`) | `17e11b3704fda77fd717c74baa4b97a7a0b08bb49569ab48c794210a2528bf9d` | 95,931,148 | 2015-06-15 |
| `C1_FW_V01.00.0004.bin` (downloaded directly, not zipped) | `76e7b56e4c3be02f83ff35b2ac7318b3e7448539226b92104169e5bda998bc45` | 14,013,108 | — |
| `C1_FW_V01.00.0010.bin` (downloaded directly, not zipped) | `8be4ecf85a59edd7a7779d94c58944114778b3a652c7343ceccc061451fcc81a` | 14,029,380 | — |
| `P3S_FW_V01.11.0020.bin` (from `P3A_FW...zip`) | `d93a09a6f68caa43d62329a84d936bb030533a7e02484f211d1b72ee0961b51e` | 62,939,344 | 2017-07-05 |
| `P3C_FW_V01.09.0200.bin` | `a6e37ce67795838504be90c952325fd6cb14f5812c09da4c5e3780d6e01e8e67` | 108,961,908 | 2017-06-19 |
| `MATRICE100_FW_V01.03.01.00.bin` | `0217a9d2402321dbc907b22422b5d1fc855ac7be4ffdeadfa05cd375d480b2b0` | 77,398,942 | 2016-04-13 |
| `MATRICE100_FLIR_FW_V01.31.00.60.bin` | (same as download, not zipped) | 4,292,162 | — |
| `P3X_FW_V01.03.0020.bin` | not re-hashed here (already in `docs/data-manifest.md`) | 95,876,112 | 2015-08-04 |
| `P3X_FW_V01.01.0008.bin` | (container not kept; module hashes below) | 86,974,312 | 2015-05-08 |
| `P3X_FW_V01.01.0009.bin` | (container not kept; module hashes below) | 86,976,104 | 2015-05-22 |

## FPGA modules identified and extracted

Identified by module number against the `dji-firmware-tools` wiki's `DJI-Firmwares` table
(`m1900` = "OFDM FPGA bitstream", `m2000`-`m2003` = "RC FPGA bitstream") and by size/position
matching this repo's own `docs/fpga-images.md` entries (FPGA images are multi-MB, distinct
from the surrounding sub-100KB-to-low-MB MCU modules in the same container's module list).

| Stored at | From container | Module | Size | SHA-256 |
|---|---|---|---|---|
| `P3A_FW_V01.11.0020/P3S_FW_V01.11.0020_m1900.bin` | `P3S_FW_V01.11.0020.bin` | `m1900` (air OFDM FPGA) | 4,194,304 | `f3a55dea4dc8c0d4d76a12650dc130b01a256913951270c7dc5c18c694666def` |
| `MATRICE100_FW_V01.03.01.00/MATRICE100_FW_V01.03.01.00_m1900.bin` | `MATRICE100_FW_V01.03.01.00.bin` | `m1900` (air OFDM FPGA) | 4,194,304 | `f3a55dea4dc8c0d4d76a12650dc130b01a256913951270c7dc5c18c694666def` |
| `P3X_FW_V01.03.0020/P3X_FW_V01.03.0020_m1900.bin` | `P3X_FW_V01.03.0020.bin` (2015-08-04, "last combined aircraft+RC package") | `m1900` (air OFDM FPGA) | 4,194,304 | `f3a55dea4dc8c0d4d76a12650dc130b01a256913951270c7dc5c18c694666def` |
| `P3X_FW_V01.03.0020/P3X_FW_V01.03.0020_m2000.bin`, `_m2001.bin`, `_m2002.bin` | same container | `m2000`/`m2001`/`m2002` (ground FPGA) | 8,388,608 each | `39a74d8d4a69ebaf...` / `b6cc5e96f12446b1...` / `30aa24c31e5180a7...` — all three already catalogued in `docs/fpga-images.md`, confirmed identical here |
| `P3X_FW_V01.01.0008/P3X_FW_V01.01.0008_m1900.bin` | `P3X_FW_V01.01.0008.bin` (2015-05-08, launch window) | `m1900` (air OFDM FPGA) | 4,194,304 | **`0ecafe1ab6583407976a561e53b6e62bfe109e12797a80735ef16c6ec4d369e4` — DIFFERENT from every other `m1900` in this repo** |
| `P3X_FW_V01.01.0008/P3X_FW_V01.01.0008_m2000.bin`, `_m2001.bin` | same container | `m2000`/`m2001` (ground FPGA) | 8,388,608 each | `39a74d8d4a69ebaf...` / `b6cc5e96f12446b1...` — identical to the later/known samples. **No `m2002` module exists in this container at all** (not present, not just absent-but-zero — the module table has no entry for it; the third ground-FPGA board revision didn't exist yet in this build) |
| `P3X_FW_V01.01.0009/P3X_FW_V01.01.0009_m1900.bin` | `P3X_FW_V01.01.0009.bin` (2015-05-22, launch window) | `m1900` (air OFDM FPGA) | 4,194,304 | `0ecafe1ab6583407976a561e53b6e62bfe109e12797a80735ef16c6ec4d369e4` — same as `V01.01.0008`, same "different" bitstream |
| `P3X_FW_V01.01.0009/P3X_FW_V01.01.0009_m2000.bin`, `_m2001.bin` | same container | `m2000`/`m2001` (ground FPGA) | 8,388,608 each | same as `V01.01.0008`; no `m2002` here either |
| `P3X_FW_V01.02.0006/P3X_FW_V01.02.0006_m1900.bin` | `P3X_FW_V01.02.0006.bin` (2015-06-15, v1.2.6) | `m1900` (air OFDM FPGA) | 4,194,304 | `f3a55dea4dc8c0d4d76a12650dc130b01a256913951270c7dc5c18c694666def` — **already the later bitstream**: swap happened in the 3-week window 2015-05-22 .. 2015-06-15 |
| `P3X_FW_V01.02.0006/P3X_FW_V01.02.0006_m2000.bin`, `_m2001.bin` | same container | `m2000`/`m2001` | 8,388,608 each | `39a74d8d...` / `b6cc5e96...` — unchanged |
| `P3X_FW_V01.02.0006/P3X_FW_V01.02.0006_m2002.bin` | same container | `m2002` (ground FPGA, 3rd board rev) | 8,388,608 | **`e6ba9914b74a75aef55fcdf4f47b9cebf97744436be60de515bfd76fdc116198` — DIFFERENT from the `30aa24c3...` revision in `V01.03.0020`+**: this is the `01.02.2107`-marked revision, the intermediate between "module absent" and the final known revision |
| `C1_FW_V01.00.0004/C1_FW_V01.00.0004_m2000.bin` | `C1_FW_V01.00.0004.bin` (2015-09-22, LB2 ground controller) | `m2000` (ground FPGA) | 8,388,608 | **`bf1539b8239d31d7d398ef29c24d7ecc63226229825a2a0be8baaf3f79c8ba01` — DIFFERENT from all `P3X_FW`-sourced `m2000` samples**: this is the `01.00.2321`-marked revision. Only `m2000` present — no `m2001`, no `m1900` in this container |
| `C1_FW_V01.00.0010/C1_FW_V01.00.0010_m2000.bin` | `C1_FW_V01.00.0010.bin` (2015-11-19, LB2 ground controller) | `m2000` (ground FPGA) | 8,388,608 | **`3592a53b40bf2f56aab72cd55d3336790ff5c79ff497397f0056523c1511d3ce` — DIFFERENT again**: `01.00.2322`-marked revision. Again only `m2000` in this container |

**Updated finding: the air-side swap (`m1900`) is now narrowed to the 3-week window 2015-05-22 .. 2015-06-15.** `P3X_FW_V01.02.0006` (2015-06-15, v1.2.6) already has the later bitstream (`f3a55dea...`), and `m2002` was added in the same window. `m2002` then changed again (`e6ba9914...` → `30aa24c3...`) between 2015-06-15 and 2015-08-04. The ground FPGA (`m2000`/`m2001`) is unchanged across all `P3X_FW` releases all the way back to launch — but the early `C1_FW` packages now show two earlier `m2000` revisions that predate the known `P3X_FW`-sourced samples.

## Negative results (containers fetched, no FPGA module present)

| Container | Modules present | Why no FPGA |
|---|---|---|
| `P3C_FW_V01.09.0200.bin` (Phantom 3 Standard) | `m0400 m1100 m1101 m0100 m0101 m0305 m0306 m0700 m0900 m1200-1203 m1400 m2700 m2900 m2901` | No `m19xx`/`m2000`-`m2003`. Phantom 3 Standard uses Wi-Fi (`m0700` Wi-Fi host) instead of Lightbridge — matches `dji-firmware-tools` wiki (`P3C_FW` is absent from every `m1900`/`m2000`-`m2002` package list). `m2700`/`m2900`/`m2901` (3.9 MB / 42 MB / 60 KB) are new module numbers not in this repo's naming convention — likely the Wi-Fi SoC firmware, not analysed (out of scope here). |
| `MATRICE100_FLIR_FW_V01.31.00.60.bin` | `m0100 m0400 m0807` | FLIR-payload-only update package (camera + gimbal + `m0807`); no transmission module at all. |

## Dead ends (checked, no usable public download found)

- **Phantom 3 SE** (`dji.com/.../products/phantom-3-se`) and **Phantom 3 4K**
  (`dji.com/.../products/phantom3-4k`): download-center pages rendered, no firmware `.bin`/`.zip`
  link present (only manuals/release notes). Per the wiki's `m1900` package list neither P3SE
  nor P3XW ever carried the Lightbridge FPGA module anyway (Wi-Fi variants) — low-value target
  even if a link existed.
- **Inspire 1** current download page: no firmware link (DJI only keeps the latest version
  linked; the `WM610_FW_V01.11.01.50` already in `docs/data-manifest.md` came from elsewhere).
- **DJI Lightbridge (gen 1)** and **DJI Lightbridge 2** download-center pages: no firmware
  `.bin` link on either — DJI only publishes the "DJI Assistant"/"DJI Assistant 2" installer
  for these; the ground-unit firmware is fetched by that Windows tool at runtime, not hosted as
  a static file. Gen-1 Lightbridge is also a different hardware generation (DM36x-based ground
  unit per `phantompilots.com` repair threads) — likely not Cyclone-family at all; not pursued
  further.
- **Standalone `LB2_GND` package** (Lightbridge 2 ground unit sold alone, board `GL658C`/`GL858A`):
  confirmed to exist and to carry `m2003` — a **different** ground FPGA module number than the
  `m2000/m2001/m2002` already in this repo — per `o-gs/dji-firmware-tools` issue #435 (maintainer
  comment: "C1: modules=m1300 m1400 m1600 m1601 m2000 m2001 m2002" vs "LB2: modules=m0605 m1300
  m1301 m1400 m1600 m2003"). No public download URL found by search; worth another pass.
- **Early Lightbridge firmware with different FPGA markings** — per the wiki's per-module
  version tables (`Firmware-m2000`, `Firmware-m2002`, `Firmware-m2003`), the ground FPGA was
  revised at least twice before the `01.00.2107`/`01.02.2109` marking already in this repo's
  `c1_m2001.bin`/`c1.bin` sample (from `C1_FW_V01.06.0000`):
  - `m2000` marking `01.00.2321` in `C1_FW_V01.00.0004` (2015-09-22) and `01.00.2322` in
    `C1_FW_V01.00.0010` (2015-11-19): **found** — both live on `dl.djicdn.com/downloads/lightbridge2/`,
    fetched and extracted 2026-10-28. See module table above.
  - `m2002` marking `01.02.2107` — **found** in `P3X_FW_V01.02.0006` (v1.2.6, 2015-06-15),
    fetched from Wayback 2026-10-28, hash `e6ba9914...`. See module table above. The CDX listing
    also showed v1.1.1007/v1.2.0007/v1.2.0008 not captured by the Wayback crawler; whether those
    releases have yet another `m2002` intermediate revision is unknown.
  - `m2003` only ever seen in early `C1_FW_V01.01.00xx` releases (2016, per the wiki) in addition
    to the standalone `LB2_GND` package below. Still not found.
- **Standalone `LB2_GND` package** carrying `m2003` (see above): no public download URL found.
- `P3P_FW_V01.11.0020.bin.zip` (`dl.djicdn.com/downloads/phantom_3/20170706/`) resolves fine but
  is the same firmware version already analysed in this repo as `P3X_FW_V01.11.0020` — not
  fetched, to avoid downloading a known-duplicate `m1900`.
- The Wayback CDX query also turned up early **Phantom 3 Advanced** zips
  (`Phantom_3_Advanced_Firmware_v1.1.8_en.zip`, `v1.1.9_en.zip`, `v1.2.8_en.zip`, `v1.3.20_en.zip`,
  `v1.4.0010_en.zip`) and one **Phantom 3 Standard** zip
  (`Phantom_3_Standard_Firmware_v1.1.0030.zip`) under the same `download.dji-innovations.com`
  path — not fetched this session (the Professional-line question was the priority), but the
  Advanced v1.1.8/v1.1.9 pair would cheaply confirm whether the early/late `m1900` split found
  on the Professional line also applies to the Advanced (`P3S_FW`) line at the same date
  boundary.

## Tools used

- `scripts/re/xv4_extract.py CONTAINER.bin [OUTDIR [m0900 ...]]` — lists/extracts xV4 modules
  (this repo; magic `0x12345678`, module table at `0x40`).
- Downloads: direct HTTPS GET to the `dl.djicdn.com`/`terra-1-g.djicdn.com` URLs for current
  firmware (plain static-file CDN, no auth/challenge encountered).
- Wayback Machine CDX API (`web.archive.org/cdx/search/cdx?url=...&output=json`) to find real,
  previously-hosted URLs for discontinued firmware no longer linked anywhere live; archived
  bytes fetched with the `.../web/<timestamp>id_/<url>` raw-replay form and verified by zip
  magic + internal filename before trusting them.
