# Windows USB tooling test, 2026-10-23

Goal: find a Windows tool that talks to a Phantom 3 Professional over USB, and capture what a
DJI tool says on the wire. Hardware: P3 Pro (owner-confirmed) controller + aircraft on USB.
Host: Windows 11 VM (virtio PCI; USB passed through).

## Result in one paragraph

DJI ships **no PC tool for the Phantom 3**. DJI's own compatibility page lists *DJI Assistant 2
For Phantom* for the Phantom 4 family only, and lists the Phantom 3 Series under *DJI GO*
(phone app). The Assistant refused the device ("not supported", exact wording not captured).
The third-party `o-gs/dji-firmware-tools` does work: its serial tool got byte-identical
replies to the Assistant's. DUMLdore (flasher) was **not** run.

## Environment set up

| Item | Version | Notes |
|---|---|---|
| DJI Assistant 2 For Phantom | 2.0.10.4 (installer 2.0.10, 2020-07-21) | Authenticode valid, SZ DJI Technology; Inno Setup; Qt5 app |
| Wireshark / USBPcap / Npcap | 4.6.9 / 1.5.4.0 / 1.88 | one USBPcap interface (`USBPcap1`, root hub) |
| dji-firmware-tools | o-gs master, GPL-3.0 | cloned to `C:\git\dji-firmware-tools`, venv with pyserial + crcmod |

Files fetched with `scripts/fetch_dji_tools.ps1` into `source/` (untracked, do not commit):
Assistant installer (.exe and .zip, identical SHA-256 `A13613DD…3138`), release notes, P3P
firmware `P3P_FW_V01.11.0020.bin.zip` (inner `P3X_FW_V01.11.0020.bin`, 66,233,768 bytes,
header magic `0x12345678`, tags "DJI" / "P3X", build 2017-07-05 03:29 UTC, entropy 6.26 b/B),
user manual v1.8, firmware update guide v1.4. The firmware module table was **not** parsed.

## Problems hit

- **Redistributable install failed** (VC++ 14.51, error `0x80070660` = MSI 1632). Cause:
  `C:\Windows\Installer` did not exist (MSI log note `1336 … C:\WINDOWS\Installer\`). Fix: recreate
  it (hidden+system; SYSTEM/Admins full, Users read) from an *elevated* shell, restart
  `msiserver`. Exit 3010 afterwards = success, reboot pending. Why it vanished: unknown.
- Serial port opened by `DJIService` (left running by the Assistant) blocks other tools:
  `PermissionError 13`. Kill `DJI*` processes first.

## USB enumeration

| VID:PID | Windows | USB | Notes |
|---|---|---|---|
| `2CA3:0008` | COM3, "DJI CONTROLLER", inbox `usbser` | 1.1 | controller; answers DUML |
| `FFF0:0008` | COM4, inbox `usbser` | 2.0 | aircraft-side; matches `docs/fc-usb-port.md`. COM4 went absent when the device re-enumerated and returned later |

The Assistant's bundled driver INFs (`dji_vcom_driver11.inf`, libusb0 "Vision") were not used:
Windows bound `usbser`. The device dropped off the bus once during the session (cause unknown:
cable, power, or VM passthrough); it came back by itself.

## Capture

`captures/2026-10-23_assistant2-phantom_p3-controller.pcapng` (604 packets, 427 s), decoded to
`….duml.txt` / `….cdc-ctrl.txt` by `scripts/pcap_decode.py` (90 DUML frames, 0 bad CRCs). Findings:

- Controller (`2CA3`): host sends set `00`, id `0c` (ping), `01` (version), `ff` (build string).
  - `01` reply: `hw_version = GL300C` plus version words.
  - `ff` reply: ASCII `WM320 A7_LPC1 20170828/00`.
- Aircraft (`FFF0`): host pings set `00` id `0c` about every 0.5 s with **no reply**; the device
  sends sender-`03` set `00` id `0e` ASCII log lines ~1 Hz (`gimbal pitch 0.00, roll 0.00, yaw
  158.90`, `>>sending limit areas:[0]`). The Assistant never got past a login dialog, so this is
  start-up traffic only, not a real session.

## What is inferred, not proven

- That the Assistant rejects the device because the build tag `WM320` is not in its Phantom 4
  list. The Assistant's own message and logic were not inspected.
- `WM320` = Phantom 3 family and `20170828` = build date: both plausible, unverified.
- Web results claimed `GL300C` is a Phantom 4 controller. Those were retail listings and a forum
  thread, contradicted by the owner's confirmation that this is a P3 Pro. Treat as unreliable.

## Third-party tools

| Tool | Status |
|---|---|
| `o-gs/dji-firmware-tools` (Python) | **Tested, works.** See below |
| `jezzab/DUMLdore` v3.20 | **Not run.** Firmware flasher, Windows `.exe` only (no source), repo archived 2024-08-06, no P3 statement found. Can brick the aircraft |
| `hdnes/pyduml` | Not examined (assistant-less firmware push; flasher) |
| Search hits named "DJI-Assistant-2-…" on GitHub | Look like fake download pages. Not opened |

### Test (read-only)

```
cd C:\git\dji-firmware-tools
.venv\Scripts\python comm_serialtalk.py --port COM3 -b 115200 -t 1000 -r 1400 -a 2 -s 0 -i 1   -w 2000 -vv
.venv\Scripts\python comm_serialtalk.py --port COM3 -b 115200 -t 1000 -r 1400 -a 2 -s 0 -i 255 -w 2000 -vv
```

`-t/-r` are decimal TTII (type+index): sender 10/0 (PC, wire byte `0a`), receiver 14/0 (wire
`0e`). Gotcha: hex `0a00` is rejected ("No 4-byte module ident").

Request `55 0d 04 33 0a 0e 00 00 40 00 01 e8 03` (header CRC8 `0x33` equals the Assistant's)
returned `GL300C` with the version words. Request id `ff` returned `WM320 A7_LPC1 20170828/00`.
Same bytes as the Assistant's capture. Only commands 00/01 and 00/ff were sent; nothing that writes.

## Real hidden debug mode found in the Assistant's own code (2026-10-23)

Checked whether DJI technicians/repair centers have a documented way to access more than the
public consumer UI. Found a real, concrete mechanism in this exact installed app
(`tmp/dji_app_asar/extracted/main.js`, from `DJIApp/app.asar` in the install under
`tmp/wine-dji/`), not inference from public forum posts (though the general pattern - editing a
`debug` flag in `main.js` for older Assistant versions - is independently documented publicly:
`dji.retroroms.info/howto/assistanddebug`, various forum threads from 2017-2018 for v1.1.x/1.2.x).

- **V, from the file itself.** `var debug = process.argv[2]=='debug'?true:false` - debug mode in
  this build (2.0.10) is a **plain runtime command-line argument**, not a compiled-in build
  flag (contrast with the DJI GO 4 Android app's `isFactoryMode()`, hardcoded `false` in the
  public APK - see `apk-vs-dissector-gap-report-2026-10-23.md`/`apk-analysis.md`). Any copy of
  this installer can be put into debug mode.
- **V.** When `debug=true`: the main window loads `index.html#/debug/1` instead of
  `index.html#/debug/0` - a distinct frontend route built into the app, not just a devtools
  toggle. Separately, the menu switches to a `template_dev` template whose items are all
  `visible: false` (so no menu bar appears) **except** the "dev tools" entry keeps
  `accelerator: "Shift+CmdOrCtrl+I"` and `enabled: true` - in Electron, a registered accelerator
  still fires even when its menu item is hidden, so Ctrl+Shift+I should open real DevTools
  (full JS console + network inspector into the running app) with no visible menu ever showing
  it.
- **Launch:** `"DJI Assistant 2.exe" debug` (one extra argument). A ready-made
  `run_assistant_debug.bat` sits next to the existing launcher in the wine prefix.
- **U, not yet tested against real hardware:** whether `#/debug/1` actually renders something
  useful for a Phantom 3 (operator's hypothesis: even though Assistant 2 doesn't support P3 for
  the normal "connect as a product" flow - confirmed earlier, DJI support says Assistant 2 is
  Phantom-4-era-only - the debug/diagnostic route might work anyway, being a lower-level view
  than product-specific UI), and whether debug mode changes anything about the earlier
  "silent exit, never gets past login" problem. Handed to the parallel session (real Windows VM,
  both devices reattached via `vm_usb.py`) to test live - not yet answered as of this commit.

## Not done / next

- Wireshark DUML dissector (`dji-firmware-tools/comm_dissector/wireshark`) not installed.
- Linux not tested. The Python tools should run there (`--port /dev/ttyACM0`); needs USB
  passthrough to the VM. Unverified.
- Firmware container module table not parsed; no firmware was flashed to anything.
- Aircraft-side (`FFF0`/COM4) commands not tried.
- Local commit only; nothing pushed.
