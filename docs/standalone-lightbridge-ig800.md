# Standalone DJI Lightbridge (IG800) — product history and firmware provenance

The retail "DJI Lightbridge" video-downlink product (sold separately from any aircraft),
not the Phantom-3-integrated Lightbridge module. Researched to find (1) DJI's own product
history/specs and (2) any actual firmware image, since the only locally-held artifact
(`sources/Lightbridge_Installer_v1.3.zip`) is the PC app only, not firmware — see
"Firmware: what DJI itself hosts" below for why.

## Product identity

- **Hardware family name**: `IG800` (community naming, `o-gs/dji-firmware-tools` wiki).
  Air-side boards documented there: **IG800 Air OFDM Transceiver board** (AD9363 RF
  transceiver + Altera Cyclone FPGA; same WiMAX-family OFDM link as the Phantom 3's
  integrated Lightbridge) and **IG800 Video Encoder board**.
  <https://github.com/o-gs/dji-firmware-tools/wiki/IG800-Air-OFDM-Transceiver-board>,
  <https://github.com/o-gs/dji-firmware-tools/wiki/IG800-Video-Encoder-board>
- **Lightbridge 2** (sold as a separate retail product too) is hardware family `IG810` —
  a distinct, later generation (`IG810 Air OFDM Transceiver board` wiki page exists
  separately). Do not conflate the two when searching for firmware/support material.
- This project already cites the IG800 Air OFDM wiki page in `control-plane-re.md` for
  the "FPGA is just a WiMAX datastream encoder" argument — same chip family, reused inside
  the Phantom 3 Professional's airframe.

## What it was (from DJI's own hosted docs)

Source: DJI's **own** Download Center page (still live, both global and regional mirrors,
e.g. `https://www.dji.com/au/downloads/products/dji-lightbridge`) — confirmed by reading
the page's embedded JSON data (not just the rendered nav). From there: the official
release-notes PDF, user manual, and quick-start guide (all still hosted on `dl.djicdn.com`
as of 2026-10-26).

- **What it is** (DJI's own summary): "A revolutionary 2.4G Full HD digital video
  downlink." Two-box system: **air system** (mounts on aircraft, encodes camera video +
  flight-controller OSD) and **ground system** (receives, decodes, outputs to
  monitor/smart device via the DJI Lightbridge App).
- **Link**: 2.4 GHz, OFDM + MIMO, FHSS/DSSS; 32-channel auto/manual selection; ~150 ms
  latency; 100 mW, up to 1.05 mi / 1.7 km (per the v1.0 release notes, 2014-04-30 spec
  sheet — later releases didn't restate range).
- **I/O**: AV in, HDMI in, HDMI out, USB 2.0 full-HD video out (to phone/tablet or HDMI
  monitor), dual video-source select (DJI HD gimbal vs HDMI/AV).
- **RC passthrough**: ground unit relays an RC signal over its "training port" (PPM) to
  reduce interference; works with DJI NAZA V2 / WKM / A2 flight controllers (DBUS
  receiver). Master/slave: one air unit can feed multiple ground units — master gets
  video+RC, slaves get video only.
- **Battery**: 4000 mAh in the ground unit.
- **Manual metadata**: `DJI LIGHTBRIDGE User Manual V1.04`, dated `2015.01`, copyright
  "©2014 DJI" — consistent with a 2014 launch, ~1-year-old product by the final manual
  revision.
- **Release-note history found** (DJI's own PDF, `Lightbridge_release_note_en.pdf`, 10
  pages, dates/versions as printed — `Ground decoder / Ground main ctrl / Air encoder /
  Air main ctrl / Ground Tx / Air Tx / Assistant`):

  | Date | Ground decoder | Ground main ctrl | Air encoder | Air main ctrl | Assistant |
  |---|---|---|---|---|---|
  | 2014-04-30 | 1.3.0 | 1.1.4 | 1.0.4 | 1.0.1 | 1.0 |
  | 2014-05-26 | 1.3.0 | 1.1.5 | 1.0.4 | 1.0.1 | 1.1 |
  | 2014-06-13 | 1.4.4 | 1.1.6 | 1.1.4 | 1.0.3 | 1.2 |
  | 2014-07-04 | 1.4.5 | 1.1.7 | 1.1.5 | 1.0.3 | 1.3 |
  | 2014-08-11 | 1.4.6 | 1.1.8 | 1.1.7 | 1.0.5 | 1.3 |
  | 2014-10-13 | 1.4.7 | 1.1.9 | 1.1.9 | 1.0.6 | 1.3 |
  | 2014-12-30 | 1.4.7 | 1.1.9 | 1.1.10 | 1.0.6 | 1.3 |
  | **2015-05-11 (final)** | **1.4.8** | **1.1.9** | **1.1.10** | **1.0.6** | 1.3 |

  Confirms the task's cited "final advertised versions" exactly (ground decoder 1.4.8,
  ground main controller 1.1.9, air encoder 1.1.10, air main controller 1.0.6). Full text:
  `/tmp/.../scratchpad/lb-docs/release_note.txt` (not committed — re-fetch from the URL
  above; it's DJI's own public PDF).
- **Marketing/product page status**: the non-download product page
  (`dji.com/lightbridge`, `dji.com/<region>/lightbridge`) now 302-redirects through to
  DJI's generic 404 ("Page not found") — checked 2026-10-26. Only the **Download Center**
  page survives, under `sub_category: tuning_params`, `stop_updating: true` on the
  Assistant-software entry.

## Firmware: what DJI itself hosts (confirmed absent)

Checked directly against the Download Center page's own embedded JSON (not just the
rendered nav — the page is Next.js and ships a `downloadsCmsDataGroup` JSON blob with the
full per-product download catalogue):

- `"firmwares":[]` for the `dji-lightbridge` product — DJI's own site has a firmware
  category slot for this product and it is **empty**. Confirmed structurally, not just by
  an absent link.
- The `assistant-dji-lightbridge` software entry's only files, ever: **one** Windows
  installer, `Lightbridge_Installer_v1.3.exe`/`.zip` (2014-06-17), `stop_updating: true`,
  no Mac/Linux links. Matches what's already in `sources/Lightbridge_Installer_v1.3.zip`
  — re-extracted here with `innoextract` (Qt4 app, "DJI Lightbridge Assistant" v5.4.2
  Inno Setup payload, 20 files) — **confirms no embedded firmware in the installer**,
  same finding as the prior session.
  - Binary strings in `Lightbridge Assistant.exe` show it calls out to
    `update.dji-innovations.com` (old pre-2016 DJI domain, has `onCheckFirmUpdates`/
    `checkFirmwareUpdates`/`FirmwareDataInfo` symbols — i.e. firmware really was
    downloaded live, on-demand, from a server, not bundled) — **that domain no longer
    resolves** (`curl`: could not resolve host, checked 2026-10-26). The live
    update-check path is gone; no API to query for a direct firmware URL.
  - `dl.djicdn.com/downloads/lightbridge/` only ever held the installer + 3 PDFs (release
    notes, user manual, quick-start guide) — enumerated exhaustively from the JSON above,
    not guessed.
- This matches and confirms the existing dead-end note already in
  `sources/dji-fpga-images/PROVENANCE.md` ("DJI Lightbridge (gen 1) ... download-center
  pages: no firmware `.bin` link ... fetched by that Windows tool at runtime, not hosted
  as a static file").

**Conclusion: DJI never hosted standalone Lightbridge firmware as a static download, on
its CDN or otherwise** — it was always a live Assistant-app pull from a now-dead update
server. The only way to obtain the actual firmware bytes is a community
dump/decrypt, below.

## Firmware: what was actually recovered (community source)

`phantompilots.com` thread (2016, user "gaucho"), **still live** as of 2026-10-26:
<https://phantompilots.com/threads/lightbridge-firmware-problem-and-solution-firmware-version-not-found-by-dji-assistant-tool.77073/>
— a NAND-bad-block recovery writeup for both ground and air units (DaVinci DM36x-based
Linux boards). Post #1 links an external archive, and a later post (#18) attaches a
second, differently-named copy. Both obtained; see `sources/lightbridge-ig800-firmware/`.

- **`LB_hack.zip`** (external host `tr3ma.com`, still live, unauthenticated HTTP):
  TI `sfh_DM36x.exe` serial-flasher host tool, gaucho's own recovery-patched
  `ubl1_editedByGaucho.img`/`u-boot_modifiedByGaucho.img`, a reference UBL from the TI
  DM36x SDK (for comparison, not DJI's), gaucho's `LightBridgeTerminal` tool (exe + VB.NET
  source) for shelling into the device's Linux over the "upgrade port" serial, **and a
  `OLD_firmware_components_decrypted_by_Andrew/` folder containing genuinely decrypted DJI
  firmware**: `ubl1.img`, `ubl2.img`, `u-boot.img`, `uImage` (Linux kernel).
- **`lightbridge_ground_controller_firmware_version1.4.8.zip`** (forum attachment,
  post #18): contains one file, `update.tar.gz`. **Byte-identical** (same SHA-256) to
  `LB_hack.zip`'s `OLD_firmware_components_extracted_from_dji_upgrade_port/update.tar.gz`
  — i.e. the same raw capture the forum poster made of the live upgrade-port transfer, the
  one labelled "v1.4.8" (the final release). It is **OpenSSL `Salted__`-encrypted**
  (`openssl enc`), and the thread says outright the password was never recovered ("we miss
  the password to decrypt the annexed file") — confirmed unreadable by `file`. **Not
  usable as-is.**

### What the decrypted files actually are (verified, not just file names)

The `OLD_firmware_components_decrypted_by_Andrew/` set is **real, working ground-unit
Linux boot firmware**, verified by direct inspection (not the final 1.4.8, an intermediate
build from the version table above — see dating):

| File | Format (verified) | Embedded version string |
|---|---|---|
| `ubl1.img`/`ubl2.img` | raw NAND UBL image | `UBL Product Vesion : DJI-GSP-UBL-1.0-rc10(2014-08-15)` |
| `u-boot.img` | raw NAND U-Boot image | `U-Boot Product Vesion : DJI-GSP-Uboot-1.0-rc4(2014-07-23)`, `U-Boot 2010.12-rc2-svn-Dji (Jul 23 2014 - 11:14:40)` |
| `uImage` | `u-boot legacy uImage`, uncompressed ARM Linux kernel, 4,043,296 B, header date `Mon Sep 15 2014` | `Linux version 2.6.32.17-davinci1 (root@dji) ... #3 PREEMPT Mon Sep 15 13:24:10 HKT 2014` |

- `DJI-GSP` = **D**JI **G**round **S**ystem **P**latform (inferred from context: this is
  the ground unit's Linux/DaVinci-DM365 board — matches "Ground system decoder" in the
  release-note table above; kernel cmdline carries `davincifb`/TVP5146 SD-video-input/
  `vid0`/`vid1`/`osd0` framebuffer args, i.e. the HDMI/AV decoder+OSD path, not the main
  controller MCU).
  - Build date (2014-09-15 kernel / 2014-08-15 UBL / 2014-07-23 U-Boot) places this
    firmware set between the **2014-08-11 (decoder 1.4.6)** and **2014-10-13 (decoder
    1.4.7)** releases in the official table above — i.e. an intermediate ~1.4.6/1.4.7-era
    ground-decoder build, not the final 1.4.8.
  - A full separate boot-log capture pasted in the same thread (different session, same
    hardware) shows version strings `UBL ... rc10(2014-08-15)` / kernel
    `#8 PREEMPT Fri May 30 14:44:25 HKT 2014` and `Kernel Product Vesion:
    DJI-GSPv2-Kernel-1.0-rc3(2014-05-30 14:45)` — note **"GSPv2"**, i.e. there are at
    least two distinct ground-platform kernel builds in circulation from this one thread;
    the archived `uImage` (Sept 2014, no "v2" string visible in the header strings grepped
    here) was not cross-checked byte-for-byte against that pasted log — worth a follow-up
    diff if the ground decoder's exact command set matters.
- `sfh_DM36x.exe` is **TI's own** tool (`TI Serial Flasher Host Program for DM36x`, 2009),
  not DJI code — generic UART/BOOTME NAND-flasher for any DM36x part.
- The `OLD_ubl_component_from_TI_SDK/ubl_DM36x_ARM432_DDR340_OSC24_NAND.bin` is likewise a
  **stock TI SDK reference file** (2011), kept by gaucho only for comparison when
  reverse-engineering DJI's UBL header — not DJI firmware.

### Open items

- **No air-unit firmware recovered** — only ground-unit (decoder board) UBL/U-Boot/kernel
  were successfully decrypted by "Andrew" per the thread; the air-unit capture in the same
  thread was reported as failing to save completely (post #18: "for the other two
  firmware, I was not able to save them").
- **The final v1.4.8 update package exists but is encrypted and unopened** — openssl
  `Salted__`, password not published anywhere found in this thread (40 pages total, only
  pages 1 checked in depth this session — a scan of later pages for a password/decrypt
  breakthrough is a cheap follow-up, not yet done).
- **"Andrew"'s decryption method is not documented in this thread** — post #1 speculates
  he used `o-gs/dji-firmware-tools`, but that's the poster's guess, not confirmed by
  Andrew himself. If the DM36x update-package encryption scheme is ever needed (e.g. to
  open the 1.4.8 package), check that tool's `dji_xv4_fwcon.py`/wiki first.
- `KyokushinPL/phantom-firmware-tools` (GitHub, fork of `o-gs/dji-firmware-tools`) was
  checked in full (137-file tree) — contains only `lightbridge_stm32_hardcoder.py`, a
  firmware **parameter-patcher** script (no firmware binaries, no additional download
  links). Dead end for firmware acquisition, confirms the task's lead was worth checking
  but doesn't add anything.
- Ground **main controller** (the MCU reporting version 1.1.x, distinct from the Linux
  decoder board above) and both **transmitter**/baseband firmware components were not
  located in cleartext anywhere this session — only the Linux decoder-board trio above.
