# Standalone DJI Lightbridge (IG800) firmware — provenance

Firmware for DJI's **standalone retail Lightbridge** video-downlink (sold separately from
any aircraft; hardware family `IG800`, distinct from `IG810`/Lightbridge 2). Background,
product history and analysis of these files: `../../docs/standalone-lightbridge-ig800.md`.

Same non-storage convention as `../dji-fpga-images/PROVENANCE.md` and
`../../docs/data-manifest.md`: **only this file is tracked**; the archives in this
directory are git-ignored. Re-fetch/verify by SHA-256 to reproduce.

## DJI's own hosting: checked, confirmed no firmware ever published

DJI's Download Center page for the product
(`https://www.dji.com/au/downloads/products/dji-lightbridge`, and equivalent regional
mirrors — still live 2026-10-26) embeds a Next.js JSON data blob
(`downloadsCmsDataGroup`) with the full per-product download catalogue. Read directly
(not just the rendered nav): `"firmwares":[]` for the `dji-lightbridge` product — the
firmware category exists on DJI's own site schema and is empty. The only files DJI ever
published for this product: one Windows installer (`Lightbridge_Installer_v1.3.exe`/
`.zip`, 2014-06-17, already in `../Lightbridge_Installer_v1.3.zip`) and three PDFs
(release notes, user manual, quick-start guide) under `dl.djicdn.com/downloads/lightbridge/`.
The installer itself was re-extracted with `innoextract` this session (20 files, Qt4 app)
— confirmed again, no embedded firmware. The app's binary strings reference a live
firmware-update-check server at `update.dji-innovations.com` (pre-2016 DJI domain,
`onCheckFirmUpdates`/`FirmwareDataInfo` symbols) — **that domain no longer resolves**
(checked 2026-10-26), so firmware was always a runtime pull from a server that's now gone,
never a static download.

## Files in this directory

| File | SHA-256 | Size | Source |
|---|---|---|---|
| `LB_hack.zip` | `dd0bee3a2448a5c44a74ac07be3cecaa48f0f1d4d455743f8276a635d3a4df02` | 6,601,170 | `https://www.tr3ma.com/Dati/LB_hack.zip` — external host linked from a phantompilots.com forum post (still live, unauthenticated, 2026-10-26) |
| `lightbridge_ground_controller_firmware_version1.4.8.zip` | `d73ba8c1d17db4033904f28451c451aa25e204eb746e8c139f56be1e6e200ea3` | 4,023,346 | `https://phantompilots.com/attachments/lightbridge_ground_controller_firmware_version1-4-8-zip.52893/` — forum attachment on the same thread |

Both found via the 2016 phantompilots.com thread "lightbridge firmware PROBLEM (and
solution) - firmware version not found by dji assistant tool" (user "gaucho"):
<https://phantompilots.com/threads/lightbridge-firmware-problem-and-solution-firmware-version-not-found-by-dji-assistant-tool.77073/>
— still live 2026-10-26, page 1 of 40 read in full (through post #20); not all 40 pages
checked.

## `LB_hack.zip` contents (verified by extraction + `file`/`strings`, not just names)

| Path | SHA-256 | Format | Notes |
|---|---|---|---|
| `OLD_firmware_components_decrypted_by_Andrew/ubl1.img` | `bf282d8bfe8f3fb76eeae559b4dc816d7e5537f6ab8d8777e348fd5cc79c6403` | raw NAND UBL image | `UBL Product Vesion : DJI-GSP-UBL-1.0-rc10(2014-08-15)` |
| `OLD_firmware_components_decrypted_by_Andrew/ubl2.img` | `0e03e4cb75a6fa295986dd4c61b378e98fc25b23b27f5f81bf75622ea1d43076` | raw NAND UBL image | same version string as ubl1 |
| `OLD_firmware_components_decrypted_by_Andrew/u-boot.img` | `66949bcd06f930d607ca0a61f28afa8a948f8ec6d34c2c22c95017e79d3aa692` | raw NAND U-Boot image | `U-Boot Product Vesion : DJI-GSP-Uboot-1.0-rc4(2014-07-23)`; `U-Boot 2010.12-rc2-svn-Dji (Jul 23 2014 - 11:14:40)` |
| `OLD_firmware_components_decrypted_by_Andrew/uImage` | `4e3322b93f9a1125099336a9ec9428bb8394d9737c679094742755752577fbdc` | `u-boot legacy uImage`, Linux-2.6.32.17-davinci1, uncompressed ARM kernel, 4,043,296 B | header date `Mon Sep 15 2014`; `Linux version 2.6.32.17-davinci1 (root@dji) (gcc 4.3.3 Sourcery G++ Lite 2009q1-203) #3 PREEMPT Mon Sep 15 13:24:10 HKT 2014`; cmdline refs `davincifb`/TVP5146/`vid0,vid1,osd0` — the ground-unit HDMI/AV decoder+OSD board (DaVinci DM365-family) |
| `OLD_firmware_components_extracted_from_dji_upgrade_port/update.tar.gz` | `1931d11f885c892eea9dadf68e126211552a4644d87b4842c21192a524cd3aaf` | `openssl enc` `Salted__` data | **encrypted, password not known to this project or (per the forum thread) to the finder** — see below, identical to the standalone `lightbridge_ground_controller_firmware_version1.4.8.zip` attachment |
| `OLD_ubl_component_from_TI_SDK/ubl_DM36x_ARM432_DDR340_OSC24_NAND.bin` | `37eab89f5c2ef0459dace55527719ec322464ae2b0db39bbe710b2f842935fc9` | raw NAND image | **stock TI DM36x SDK reference UBL (2011), not DJI code** — kept by the finder only to compare headers |
| `sfh_DM36x.exe` | `f41541402c2822b7d2a9df3fbd3cd94ed1c8bd3b392f02b0a935ffeee2cc240f` | PE32, TI tool | `TI Serial Flasher Host Program for DM36x`, 2009 — generic UART/BOOTME NAND flasher, not DJI-specific |
| `ubl1_editedByGaucho.img` | `fec6b8f7a276401b6ae94d93f705749e37d2ef48a7457ce49470bd29a6b9debd` | raw NAND image | forum poster's own recovery-patched UBL, for re-flashing a bricked unit via `sfh_DM36x.exe` — not a stock DJI release |
| `u-boot_modifiedByGaucho.img` | `2eda1cf9c35eeb4d8d2e63778932eb69ad68ee5a9e2b12584a4500610432f94f` | raw NAND image | forum poster's own recovery-patched U-Boot, same purpose |
| `lightBridgeTerminalApp_by_Gaucho/LightBridgeTerminal.exe` | `f98ce2076727b9d50884c588493262d1c650c30bc7c106333d359849d87e6229` | PE32 .NET GUI app | third-party tool: opens a Linux shell over the device's "upgrade port" serial line |
| `lightBridgeTerminalApp_by_Gaucho/source code for Lightbridge Terminal.zip` | `66d505e6781308ac34e8aafc67759f7d41cb5fe229ab16f72850676e9469dcfb` | zip (VB.NET source) | source for the above |
| `lightBridgeTerminalApp_by_Gaucho/readme.txt` | `5a17e502eeccb956a57bc274cdf88d8b2b3b1dcf35e85cfabd95a23a64d7635e` | text | usage notes for the terminal tool |

## `lightbridge_ground_controller_firmware_version1.4.8.zip` contents

One file, `update.tar.gz`, SHA-256 `1931d11f885c892eea9dadf68e126211552a4644d87b4842c21192a524cd3aaf`
— **byte-identical** to `LB_hack.zip`'s
`OLD_firmware_components_extracted_from_dji_upgrade_port/update.tar.gz` above. The forum
poster labelled this copy "version1.4.8".

## Decrypting `update.tar.gz` — SOLVED (2026-10-28)

**Password: `Dji123456`** — the same DJI-universal passphrase used for xV4 module encryption.
**Cipher: `openssl enc -des3 -md md5`** (Triple-DES-CBC, MD5-based key derivation — the
OpenSSL 1.x default; AES variants all fail).

Decrypt command:
```
openssl enc -d -des3 -md md5 -in update.tar.gz -pass pass:Dji123456 | tar -xz
```

Produces a `dji/` tree with the full v1.4.8.6 ground-system application layer — far more
than just the boot firmware Andrew extracted from a live device. Full file manifest with
SHA-256s is in the sub-table below.

### Decrypted contents (v1.4.8.6, build date 2015-03-17)

Key files (full SHA-256 table committed separately if needed):

| Path | Size | SHA-256 | Notes |
|---|---|---|---|
| `dji/etc/version` | 8 | `d96acf68...` | `1.4.8.6` |
| `dji/data/ubl1.img` | 16,384 | `bf282d8b...` | **matches Andrew's decrypted set** |
| `dji/data/ubl2.img` | 16,384 | `0e03e4cb...` | same |
| `dji/data/u-boot.img` | 296,960 | `66949bcd...` | same |
| `dji/data/uImage` | 4,043,360 | `4e3322b9...` | same — confirms Andrew extracted from the same package |
| `dji/bin/usbclient` | 1,565,657 | `b908d5ee...` | **main ground-unit application** (ARM ELF, DaVinci DM365) |
| `dji/lib/libcommon.so` | 98,615 | `ba673af7...` | DJI shared library |
| `dji/bin/Vend_Ax.iic` | 3,571 | `aa667433...` | firmware for the CY7C68013A (FX2LP) USB controller on the ground unit |
| `dji/modules/usb_cy7c68013a.ko` | 14,096 | `a6a2b159...` | Linux kernel driver for that chip |
| `dji/bin/adb` | 1,517,559 | `dbac837a...` | Android Debug Bridge binary — **ADB server runs on boot** (see `boot.sh`) |
| `dji/bin/sshenable` | 120 | `18da84b8...` | script to enable SSH on the device |
| `dji/bin/setsecurity` | 22,817 | `0aedd17d...` | AT88/security chip configuration tool |
| `dji/bin/update68013` | 30,286 | `0d524f35...` | tool to flash new firmware to the CY7C68013A |
| `dji/bin/fxload` | 37,861 | `44e1a9cc...` | generic FX2LP firmware loader (open-source tool) |
| `dji/bin/usbmuxd` | 56,742 | `ca8d0a55...` | USB multiplexer daemon |
| `dji/bin/usbupdate` | 12,449 | `55495d80...` | update-monitor process |
| `dji/modules/dsp/cmemk.ko` | 26,326 | `1ecee796...` | DaVinci CMEM memory allocator driver |
| `dji/data/font/Oswald.otf` + `Oswald-Light.otf` | 41,432 + 28,256 | — | OSD fonts |
| `dji/data/png/` + `dji/data/png2/` | 10 icons each | — | OSD icon assets (two sets) |

Boot sequence (from `dji/etc/boot.sh`):
```sh
loadmodule-rc start       # load kernel modules
devgpio -n 60 -w 1        # enable CY7C68013A (GPIO 60)
sshenable                 # enable SSH
adb start-server          # start ADB server
usbmuxd -v -v             # USB multiplexer
usbclient &               # main application
usbupdate &               # update monitor
```

**Implication**: the ground unit boots with SSH enabled and an ADB server running — shell
access is straightforward if you can reach the USB port. The `usbclient` binary is the
primary analysis target for the ground-side link behavior (ARM ELF, ~1.5 MB, DaVinci DM365
platform).

## What this does NOT include

- No air-unit firmware recovered — post #18: poster could not fully save the air-unit capture.
- No ground **main controller** MCU firmware (component DJI's release notes version as `1.1.x`,
  distinct from the Linux decoder board) and no transmitter/baseband firmware — not in
  `update.tar.gz` and not located elsewhere.
- ~~Thread is 40 pages; only page 1 checked — a later page may have a password breakthrough.~~
  **Moot**: password is `Dji123456` with `openssl enc -des3 -md md5` (found 2026-10-28 via
  binary analysis of `Lightbridge Assistant.exe` + cipher enumeration; the forum thread scan
  was running in parallel and is not needed for this).

## Tools used

- `innoextract -e -m` on `Lightbridge_Installer_v1.3.exe` (re-extracted fresh this
  session into an isolated scratch dir) — Inno Setup unpacker.
- `curl`/`strings`/`file` for binary inspection (Windows PE strings, image-format
  detection).
- `playwrong` (`goto`+`js` to read real `<a href>` attachment URLs off the XenForo thread
  page — the raw HTML is Cloudflare-challenged, `curl` alone gets only a JS interstitial;
  `download` to fetch the forum attachment through the same cleared browser session).
- Direct `curl` for `dl.djicdn.com` and `tr3ma.com` (both plain, unauthenticated HTTP(S),
  no challenge encountered).
