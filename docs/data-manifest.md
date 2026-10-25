# Data manifest — the downloaded inputs (NOT stored in this repo)

The reverse-engineering in this repo was done against DJI firmware/app binaries and some
third-party tools. **None of those bytes are committed here** — they are DJI's copyright
(firmware, APK) or other projects with their own git/licences (Mistral, Flutter, the kernel,
dji-firmware-tools), and several individual files exceed GitHub's 100 MB limit (the scratch
set was ~4.7 GB). This manifest lets anyone re-fetch the **exact** inputs and verify them by
hash, so the analysis is fully reproducible without redistributing proprietary data. See also
`code-provenance.md` and `license-compliance.md`.

## Firmware (DJI xV4 containers) — obtain from DJI / community mirrors, verify by SHA-256

| File | SHA-256 | Size | What |
|---|---|---|---|
| `P3X_FW_V01.11.0020.bin` | `cecc3acdb09bb416f15feeff409220493b3b1b74344b736aa566ce3e197e7149` | 66,233,768 | Phantom 3 Pro firmware container (aircraft side) |
| `WM610_FW_V01.11.01.50.bin` | `bc2d8e1d2a110c4573d7d3b9af935ad3b61c48db8e5f9d3745fdf2c51310540e` | 73,350,122 | Inspire 1 / WM610 (same LB family; cross-ref) |
| `c1.bin` | `38de9e3fe0664fb43b85c11eabeed0c026dd15f80d402091ac68a0364f23d942` | 30,046,440 | C1 ground RC firmware container |
| `Phantom_3_Professional_Firmware_v1.3.20__en.zip` (official, `dl.djicdn.com/downloads/phantom_3/en/`) | `1e2e587daf55ce46f54872b6caadbc330a2402cb59e71c330d3f1a635ebbfc64` | 55,965,540 | contains `P3X_FW_V01.03.0020.bin` (`788a14cb...f69c15`, 95,876,112): last combined aircraft + RC package, so the RC modules are publicly downloadable. `m1601` 02.00.0002 = `4eb9d11374336047542ece7ace7a4be050fc03d87a2810aed281b6c1cda0a114` (184,036 B); `m2001` = same SHA as `c1_m2001.bin` |

Unpack with dji-firmware-tools `dji_xv4_fwcon.py` → per-module `.bin`. Key modules analysed
(verify after unpack):

| Module | SHA-256 | Size | Role |
|---|---|---|---|
| `P3X_FW_V01.11.0020_m0900.bin` | `72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d` | 75,796 | air radio MCU (STM32F103) |
| `c1_m1400.bin` | `43bc7d6cb9f9c916dcfee0146378a3a6c823d0c65ac9613ca5adecae25f9d93f` | 155,304 | ground radio MCU (LPC1765) — all MCU proofs are against this |
| `c1_m2001.bin` | `b6cc5e96f12446b12d7d384a6b873cf29653fb0ac34353442124b8480f9a73ca` | 8,388,608 | ground Lightbridge FPGA container (Cyclone III/IV-format payload; best match EP4CGX150) |

## Apps - DJI copyright, not stored

v4.3.64 (2026-10-23): official DJI download page (dji.com Download Center -> service-adhoc.dji.com) embeds a signed, short-lived CDN link (terra-2-g.djicdn.com, `..._official_sec.apk`); fetch it from that page, the link expires in a day. Saved under `firmware/apk/` (git-ignored). The older `go4.apk` below has no recorded source.


| File | SHA-256 | Size |
|---|---|---|
| `go4.apk` | `0a2a6b6a79ad2b3e8b6346e37d76da4d9f61c62f997556983576f2bd64d8c612` | 107,504,443 |
| `dji-go-4_v4.3.64.apk` | `01ab1f16e824c4eecec8dc4637cb5721d44efdd5ff62ae6abd59f83101381e25` | 270,454,045 |

### Classic consumer DJI GO (`dji.pilot`), verified 2026-10-25

**Identity correction:** `dji.go.v4` is GO 4; `dji.pilot` is the original consumer
DJI GO, not evidence of the later enterprise Pilot app. Earlier classic GO 3.1.83
acquisition/analysis was already recorded in `sources/README.md` and issue #16.
The newly downloaded files below are hash-pinned; the earlier runtime tree was
not, so its exact byte identity is not retrospectively asserted.

| File | Version / code | SHA-256 | Size | Source / role |
|---|---|---|---|---|
| `sources/apk/dji.pilot-3.1.8.apk` | 3.1.8 / 31018968 | `f7a4eaaf0adf6bee86d1cd50c4a221824b17e97132807f0f4172f9b68b9f1965` | 101,595,742 | [Softpedia historical build](https://mobile.softpedia.com/apk/dji-go/3.1.8/); matches APKMirror's published hash; contemporary with P3X 1.11.20 per DJI's 2017-07-06 release notes |
| `sources/apk/dji.pilot-3.1.83.apk` | 3.1.83 / 36020963 | `880b67803c60ea35b488882727936b4fa885f37b014aa9495411298224513109` | 187,813,358 | [DJI official service page](https://service-adhoc.dji.com/download/app/android/be36a032-050d-4184-92cc-ac5aa1eb2eef); current supported-product comparison |

Both APKs pass Google apksig 8.7.3 v1 signature verification, zero errors, with
signer certificate SHA-256
`01a42c94aa87020f41e8c252598df98b86a0acf6c05ff61c75f18fa29cad1dd4`.
Unsigned `META-INF` metadata warnings are recorded, not suppressed. Full manifest,
DEX hashes and signature results: [3.1.8](data/dji-go-3.1.8-provenance.json),
[3.1.83](data/dji-go-3.1.83-provenance.json). Reproduce with
`scripts/re/apk_provenance.py`; acquisition/decompilation and evidence limits are in
[the P3 audit](dji-go-p3-evidence-audit-2026-10-25.md).

3.1.8 decompiled statically with jadx 1.5.3 under
`tmp/apk/go_3.1.8/static/`. 3.1.83's static tree under
`tmp/apk/go_3.1.83/static/` is AppGuard/third-party code only, not recovered DJI
implementation. Existing `dynamic` is GO 4; `pilot_dynamic`/`pilot_static` names
are historical labels for classic GO 3.1.83. Neither runtime tree exists in this
new checkout. Never infer application identity from those directory names.

## Third-party tools (clone + build; pinned commits used here)

| Tool | Source | Commit used |
|---|---|---|
| Project Mistral (Cyclone-V bitstream RE; not applicable to m2001) | github.com/Ravenslofty/mistral | `d509238a203aadbb76291ab06543a401df91cf54` |
| dji-firmware-tools (unpack + DUML dissector) | github.com/o-gs/dji-firmware-tools | `195692263c2684cf1ddc4995f2736be6c0fb135e` |
| Flutter SDK | flutter.dev (install, don't vendor) | bundled Dart used for `dart test` |
| Renode | github.com/renode/renode | build **from source** — see `renode-task.md` |

## Derived artifacts (also not stored — reproducible)

No FPGA-derived artifacts are kept: the earlier `m2001.bt` / `routes.txt` came from a void decode (pluribus #114). Do not regenerate them.

Scripts in `scripts/fpga/` that consumed them are void. Every doc cites exact offsets
so results can be re-derived against your own verified unpack.

## Reverse-engineering reference inputs (not stored)

- **STM32F427 SVD** (peripheral/register map for m0306 Ghidra MMIO labels): `raw.githubusercontent.com/cmsis-svd/cmsis-svd-data/main/data/STMicro/STM32F427.svd` (2,222,473 B). 1574 registers flattened to address labels by `scripts/re/ghidra/fc_setup.py`.
- **Ghidra 11.4 PUBLIC** headless, JDK 21. m0306 imported as Raw Binary, `ARM:LE:32:Cortex`, base `0x08020000` (decrypt first with `scripts/re/xv4_decrypt.py`).
- **DJI module AES key** for `encrypt_type=1`: from o-gs/dji-firmware-tools `dji_xv4_fwcon.py` (public).
