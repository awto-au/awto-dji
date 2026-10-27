# DJI Assistant 2 For Phantom native layer — static analysis of the Windows binaries

Status tags: **V** verified here (seen in the binary) · **I** inferred · **U** unknown/not
obtained. Source: DJI Assistant 2 For Phantom 2.0.10 installer (see `docs/fc-usb-port.md`
"DJI's own Windows driver" / "Attempted: live capture ... under Wine" sections for
provenance/signing). Installed tree under `tmp/wine-dji/` (git-ignored, not committed, not
executed — static analysis only, per `../CLAUDE.md`). Tools: `objdump -d -M intel` /
`objdump -p` / `objdump -h`, a small hand-rolled PE export-table parser (no `pefile`/`rizin`
available in this environment — see "Tooling note" below).

Reproduce: re-run the installer under Wine as in `fc-usb-port.md`, then re-derive every
offset below from the files listed in "Files analysed, with hashes".

## Headline result: DJI's own CRC8/CRC16 constants, confirmed byte-for-byte (V)

`scripts/probe_fc_usb.py` / `scripts/re/wine_serial_proxy.py` use CRC8 seed `0x77` (poly
`0x8C` reflected) for the 4-byte DUML header and CRC16 seed `0x3692` (poly `0x8408`
reflected) for the whole frame. Both are now confirmed directly from DJI's shipped code,
not just from public dissectors:

- **V** `dataManager.dll` (`.rdata`, file offset `0x34610`/VA `0x10035210`) contains the
  **exact 256-byte CRC8 lookup table** for poly `0x8C`, immediately followed (file offset
  `0x34710`/VA `0x10035310`) by the **exact 512-byte CRC16 lookup table** for poly `0x8408`
  — both tables computed independently here and matched byte-for-byte against the file.
- **V** The CRC8 table is indexed in a function at VA `0x100099c0`-`0x100099d1` (inside a
  larger routine starting `0x10009989`) that: checks `cmp BYTE PTR [edi],0x55` at
  `0x100099a8` — **the DUML SOF byte** — then runs a 3-byte header CRC8 loop seeded from a
  byte global at VA `0x10046066`, and compares the result against the 4th header byte. This
  is DJI's own DUML header-validate routine.
- **V** The CRC16 table is indexed in a sibling routine (starts `0x100098d0`) seeded from a
  2-byte global at VA `0x10046064`.
- **V** Static initial values of those globals, read directly from `.data` (file offset
  `0x44c64`/`0x44c66`): `0x10046064` = `0x3692` (LE bytes `92 36`), `0x10046066` = `0x77`.
  **Exact match to the seeds already hard-coded in `scripts/probe_fc_usb.py` and
  `scripts/re/wine_serial_proxy.py`.**
- **V** Exported setters write exactly those two globals: `?set_crc8_init@data_codec@@QAEXE@Z`
  (VA `0x10009b80`: `mov ds:0x10046066,al`) and `?set_crc16_init@data_codec@@QAEXG@Z` (VA
  `0x10009b90`: `mov ds:0x10046064,ax`) — so the seeds are a per-instance `data_codec`
  parameter, defaulting at static-init time to DJI's standard values above.
- **V** The identical 256+512-byte table pair (full match, not just the seed) is also present,
  byte-for-byte, in all four `DJIServices/*.dll` service modules (`DJIRcService.dll`,
  `DJIRc2Service.dll`, `DJIUavService.dll`, `DJIBsService.dll`) — same codec statically
  linked into each product-line service.
- **I** `dataManager.dll`'s own callers are `Viewer.exe` (the standalone 3D/log-viewer tool,
  not the live device engine) — its exports (`DataManager`, `DataLoader::ParsePacket`,
  `CCodec`, `data_codec`, `FieldArray`, `data2_config`) read like a generic declarative
  binary-record codec (field-array / config-driven), used here for DUML-framed flight-log
  playback rather than the live USB link. The codec and its CRC constants are DJI's DUML
  implementation either way.

## CmdSet 0x00 (COMMON) numeric command IDs — cross-confirmation (V)

**Correction (2026-10-23):** this section originally labelled 0x0b/0x0c "new". They are not — both are already in the public o-gs/dji-firmware-tools Wireshark dissector (`dji-dumlv1-general.lua`, already cloned on this machine and used elsewhere in this repo's docs), which was not checked before writing that label. What the DLL analysis genuinely adds for 0x0b/0x0c: DJI's own compiled string literals (`reboot_device`, `ActionDoQueryStatus`) corroborate the dissector's names from DJI's own binary, rather than from third-party behavioural inference — a real but smaller claim than "new".

`DJIUavService.dll` and `DJIRcService.dll` (identical in both; `DJIRc2Service.dll` and
`DJIBsService.dll` share the CRC tables but were not grepped for these specific strings)
contain literal debug-log strings of the form `ActionName (<cmdset>_0x<cmdid>)` inside a
`DJIModuleUpgrader` / `DJIFirmUpgrader{1,2,3}` class family (firmware-upgrade state
machine). These are **plaintext, not reconstructed from disassembly**:

**Note:** the whole 0x00-0x0a range in this table is also already in the public o-gs/dji-firmware-tools dissector (`dji-dumlv1-general.lua`, local `dji-firmware-tools` checkout) - Ping/Version Inquiry/.../Update Finish are all pre-existing public names. Nothing in this table is new protocol knowledge; what's new is only that DJI's own shipped binary now corroborates those names directly, rather than via third-party behavioural reverse engineering.

| cmdset | cmdid | name (string, verbatim) | cross-check |
|---|---|---|---|
| 0x00 | 0x01 | `[ActionDoQueryVersion] 0_0x01` / `getversion(0_0x01)` | **confirms app**: matches `apk-duml-commands.tsv` row "Get Version / device info", id inferred there from `catalog.dart` |
| 0x00 | 0x07 | `[ActionDoEnterUpgradeMode]0x07` | **confirms firmware**: exact match to m0900 "Enter Loader", `docs/fpga-upgrade-path.md` |
| 0x00 | 0x08 | tag `(0_0x08)` beside string `upgrade_request_receive` | **confirms firmware**: matches m0900 "Update Confirm" (`docs/fpga-upgrade-path.md`) |
| 0x00 | 0x09 | string `re-data transmission %1` beside `(0x09`, class `ActionDoDataTransmission` | **confirms firmware naming** ("Update Transmit"); m0900 itself has **no handler** for 0x09 (per `docs/fpga-upgrade-path.md`) — this DLL still names/uses the id, so the handler lives elsewhere (another firmware module, or host-side only) |
| 0x00 | 0x0a | tag `(0_0x0a)` beside string `firmware_upgrade_finish`, class `ActionDoUpgradeVerify` | **confirms firmware**: matches m0900 "Update Finish" |
| 0x00 | 0x0b | tag `(0_0xb)` beside string `reboot_device`, class `ActionDoReboot` | **confirms public dissector**: matches o-gs/dji-firmware-tools `dji-dumlv1-general.lua` `[0x0b] = 'Reboot Chip'` (already on disk at local `dji-firmware-tools` checkout, not previously cross-checked against this DLL work) |
| 0x00 | 0x0c | `[ActionDoQueryStatus] 0_0x0c`, class `ActionDoQueryStatus` | **confirms public dissector**: matches o-gs/dji-firmware-tools `dji-dumlv1-general.lua` `[0x0c] = 'Get Device State'` |

Evidence form: these are Qt debug-log literal strings (e.g. `"[ActionDoQueryStatus] "` and
`"0_0x0c"` stored as adjacent/concatenated literals), paired with class method names
`DJIModuleUpgrader::ActionDoX` / `DJIFirmUpgrader{1,2,3}::ActionDoX` from the C++ mangled
export names and literal `operator()` lambda strings in the same region of `.rdata`.
Offsets: cluster sits at file-relative string offsets `~0x7d1f00`-`0x7d3400` in
`DJIUavService.dll` (VA = file offset + image base/section delta; not individually resolved
per string here — reproduce with the grep commands in "Reproduce" below).

**No cmdset-byte switch/jump-table dispatch was located** for CmdSet or DeviceType (0-20ish)
in the time-boxed pass — these large service DLLs (5-10 MB each) were not fully
disassembled; the command IDs above came from literal debug strings, which is a more direct
source than reconstructing a switch table would have been anyway.

## What was searched and came back negative

- **`DJIDevice.dll`** (363 KB, the file named as primary target): confirmed by export table to be a thin **WebSocket-IPC + app-settings singleton wrapper** (`DJIWebSocketHandler`, `DJIAppModel` get/save-setting, `DJIDeviceDll`).
  - "Device" here means the Electron-UI-facing device-list/session object, not the serial transport.
  - Its only imports are `Qt5Core`, `Qt5WebSockets`, `DJILog`, MSVC runtime, `KERNEL32`: **no** `Qt5SerialPort.dll`, **no** `dataManager.dll`.
  - Contains **no** CRC table, **no** DUML/SOF constant, **no** cmdset/cmdid literal strings.
  - The name is misleading for this build; the live device/serial layer is elsewhere (see below). (V, supersedes the "almost certainly" guess in `fc-usb-port.md`.)
- **`Qt5SerialPort.dll`** is present on disk but **not imported (statically) by any binary in the installed tree**.
  - Grepped every file under `tmp/wine-dji/.../DJI Assistant 2 For Phantom/` for the literal string `Qt5SerialPort.dll`; the only hits are the file itself and the uninstaller's file-list log (`unins000.dat`).
  - Could still be `LoadLibrary`'d dynamically by a component not inspected here, or be vestigial. (V negative result; **?** whether anything loads it dynamically.)
- **`DJI_guidance.dll`**: no CRC table, no cmdset/duml/flyc/gimbal strings — vision/obstacle
  avoidance library, not product-relevant to P3 Pro (no guidance sensor) and not part of the
  protocol stack. (V negative.)
- **`DJIService.exe`** (4.9 MB): imports `DJIDevice.dll`, `DJIDevice.dll`'s IPC layer, plus `SETUPAPI.dll`/`WTSAPI32.dll`/`WS2_32.dll` (device enumeration + networking).
  - **Not** `Qt5SerialPort.dll` and **not** `dataManager.dll`; no CRC table found in the executable itself either.
- Connected-Master-Id handshake (RC cmdset 0x06, ids 0x0c/0x0d per `docs/id-entry-point.md`): **not found** in any binary searched.
  - No `ConnectMaster`, `MasterId`, or RC-cmdset-6 literal strings anywhere in `DJIDevice.dll`, `dataManager.dll`, or the two services grepped in detail.
  - The 0x0c found here is an unrelated cmdset-0 firmware-upgrade id (`ActionDoQueryStatus`), not RC's master-id field: **coincidental numeric overlap across different cmdsets, not a find**.
- No readable `CmdSet`/`DeviceType`/`Flyc`/`Gimbal`/`OSD` enum-name strings anywhere (matches the "expected: numeric immediates in native code" note already in `fc-usb-port.md`).
  - No Qt MOC method-name tables beyond the already-known `DJIDevice`/`DJIWebSocketHandler` signal/slot names (these carry no protocol content).
- No external XML/JSON/cfg file defining DUML fields was found anywhere under the installed tree (`find ... -iname '*.xml' -o -iname '*.json' -o -iname '*.cfg'`); only 3D-viewer/Ogre assets and Electron `package.json`.
  - Any such schema is fetched from DJI's servers at runtime (consistent with `apk-analysis.md` "Needs DJI servers").

## Tooling note

`rizin`/`rz-bin` and Python `pefile` are **not installed** in this environment (the `rz`
binary present on `$PATH` is an unrelated remote-protocol tool, not rizin). Worked around
with `objdump -d -M intel` / `objdump -p` / `objdump -h` (binutils, already available) plus a
~60-line hand-written PE export-directory parser (reads `IMAGE_EXPORT_DIRECTORY` by hand;
not committed, scratch-only) to recover demangled-adjacent export name -> VA mappings that
`objdump -T` cannot produce for PE files (`objdump -T` reports "not a dynamic object" for PE
DLLs). capstone was not needed — `objdump` disassembly was sufficient for the hits found.

## Files analysed, with hashes (not committed — DJI copyright, per `../CLAUDE.md`/`data-manifest.md` convention)

| File | Size | SHA-256 |
|---|---|---|
| `DJIEngine/DJIDevice.dll` | 371,248 | `2a3699bdb5bcb909b80bee4c831daaf5309e5f795699938d6cc0171c6cf5d5d7` |
| `DJIEngine/dataManager.dll` | 317,488 | `9f0404163ff06490844c86de007c28970fc14f0524abc5450d33d537d94bbc00` |
| `DJIEngine/DJI_guidance.dll` | 143,872 | `447f0ab23b8b839d383c4925566b9e11fb591b9630947946a3e9645ac63f3b70` |
| `DJIEngine/Qt5SerialPort.dll` | 60,416 | `ece3373972bc4e59a90fc9bee62b8922cf11cfca7d5c08ec7dd434f741bf9888` |
| `DJIEngine/DJIServices/DJIRcService.dll` | 6,635,056 | `42011440c725e6804567661954da1a6a4a8cd669accec6f28219da43b1dfa1c4` |
| `DJIEngine/DJIServices/DJIRc2Service.dll` | 5,255,216 | `9d127641b04e823ee4fabcc08e66b52f1b3d0f0b6929554888dce790547e4e04` |
| `DJIEngine/DJIServices/DJIUavService.dll` | 10,425,392 | `d0eee76db5589685cb0ab77698a919b361392d5c6e4c424e526e5f3a2ea213eb` |
| `DJIEngine/DJIServices/DJIBsService.dll` | 5,366,320 | `1f21ec216093defc8f3fcfb00e39ef1ce70fa9a7588b8caa7036c0a414c57b21` |
| `DJIEngine/DJIService.exe` | 5,051,440 | not re-hashed (import table checked only) |

## What's needed next

1. **`DJIRcService.dll` is the right next target for a live-protocol trace**: it's the
   RC-mediated service (matches P3 Pro's actual AOA-via-RC transport per `apk-analysis.md`
   section 1), it carries the same CRC tables and firmware-upgrade action IDs confirmed
   above, and at 6.6 MB (vs `DJIUavService.dll`'s 10.4 MB for direct-Wi-Fi-UAV products) it's
   the smaller of the two to disassemble fully for a cmdset/devicetype switch table.
2. Resolve whether `Qt5SerialPort.dll` is dynamically loaded (`LoadLibraryA`/`GetProcAddress`
   string pairs) by `DJIRcService.dll`/`DJIUavService.dll` — would settle where the live COM
   port actually gets opened, independent of the Wine startup-crash blocker in
   `fc-usb-port.md`.
3. RC cmdset-6 Connected-Master-Id (0x0c/0x0d) was not found here; worth a targeted string
   search of `DJIRcService.dll`/`DJIRc2Service.dll` for `ConnectMaster`/`MasterId`-style debug
   tags using the same `(<set>_0x<id>)` pattern that worked for cmdset 0 above.

Scope: owned aircraft, interoperability only (see `../CLAUDE.md`). No key extraction, no
geofence/flight-restriction work, no execution of DJI binaries (static analysis only).
