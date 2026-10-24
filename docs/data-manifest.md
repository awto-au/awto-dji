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

## App (DJI GO) — DJI copyright, not stored

v4.3.64 (2026-10-23): official DJI download page (dji.com Download Center -> service-adhoc.dji.com) embeds a signed, short-lived CDN link (terra-2-g.djicdn.com, `..._official_sec.apk`); fetch it from that page, the link expires in a day. Saved under `firmware/apk/` (git-ignored). The older `go4.apk` below has no recorded source.


| File | SHA-256 | Size |
|---|---|---|
| `go4.apk` | `0a2a6b6a79ad2b3e8b6346e37d76da4d9f61c62f997556983576f2bd64d8c612` | 107,504,443 |
| `dji-go-4_v4.3.64.apk` | `01ab1f16e824c4eecec8dc4637cb5721d44efdd5ff62ae6abd59f83101381e25` | 270,454,045 |

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
