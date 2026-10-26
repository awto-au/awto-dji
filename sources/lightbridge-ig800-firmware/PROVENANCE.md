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
poster labelled this copy "version1.4.8" (matching DJI's own final release-note version
for the ground decoder — see the doc's version table) and stated explicitly that the
OpenSSL password to decrypt it was never recovered. **Not usable as firmware without that
password.**

## What this does NOT include

- No air-unit firmware was successfully decrypted in this thread (post #18: the poster
  could not fully save the air-unit capture).
- No ground **main controller** MCU firmware (the component DJI's release notes version
  as `1.1.x`, distinct from the Linux decoder board above) and no transmitter/baseband
  firmware — not located in cleartext anywhere this session.
- Thread is 40 pages; only page 1 (posts #1–#20) was read in full. A later page may have a
  password breakthrough for the encrypted `update.tar.gz` — not checked.

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
