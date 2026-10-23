# Aircraft front micro-USB port (flight controller, VID `fff0` PID `0008`)

Status of each claim: **V** verified here, **W** from the o-gs wiki / issues (not re-checked), **I** inferred, **?** unknown.

## What it is
- **V** The aircraft's front micro-USB ("Assistant" port) enumerates on Linux as `fff0:0008`, product `DJI CONTROLLER`, manufacturer `DJI`, serial `0001A0000000`.
- **V** Serial is a fixed string: same value reported on a Phantom 3 Standard in 2017 (o-gs/dji-firmware-tools#43).
- **V** Descriptor: full-speed, class 2 CDC-ACM, interface 0 comm (interrupt IN `0x82`, 8 B), interface 1 data (bulk OUT `0x01`, bulk IN `0x81`, 64 B), self-powered, 100 mA. Linux binds `cdc_acm` (`ttyACM*`).
- **W** Socket is on the P3X ESC/center board (WM320_ESC_CENT_v4, P01012.07/.09); a ribbon carries USB D+/D- to the flight-controller daughterboard (pads 3/4 on the 20-pin side).
- **W** Wiki describes it as USB-to-TTL to the flight controller carrying DUML, 9600 8N1.
- **V** The USB device is implemented in the flight-controller firmware itself (`m0306` carries the `DJI CONTROLLER` / `0001A0000000` strings), not a separate bridge chip.

## CPU behind it
- **W** Flight controller ("MC", P01006.05): STM32F427IIH6, Cortex-M4F, 180 MHz, 2 MB flash. Firmware modules `m0305` (loader), `m0306` (app).
- **W** Same board also carries MPU-6500 IMU, MS5607 barometer, ATSHA204 (component auth), micro-SD (flight logs).
- **W** Readout protection level 2 on the factory ROM bootloader; BOOT0 / SWD pads exist.
- Not the ESC MCUs: four TMS320F28027F ("IESC2000", `m1200`-`m1203`) sit on the center board.

## Firmware findings (`P3X_FW_V01.11.0020`, module `m0306`, ARM Thumb, base `0x8020000`)
- **V** Image is readable (strings and code), not encrypted.
- **V** USB stack is ST's USB device library: descriptor callbacks (device `0x12` bytes, langid 4 bytes, manufacturer, product, serial, config, interface strings via `USBD_GetString` at `0x8037b36`) at `0x80a4a00`-`0x80a4afa`.
- **V** Two class tags sit beside the descriptor strings: `VCOM` (`0x80a4ae0`) and `MSCM` (`0x80a4ae8`). A `DJI DATA LOG 2.00` SCSI inquiry string is present.
- **I** Firmware supports a CDC serial mode and a mass-storage mode; the log string `usb work in MSC mode or is valid` (LED status) suggests MSC is a state the port can enter. What switches modes is **?**.
- **V** Strings `Assistant protect!`, `assistant connect changed:last(%u) != current(%u)`, `assistant_timeout`: flight-protect logic keyed on an "assistant" link.
- **V** Simulator strings (`try to start simulator!`, `Have run simulator, please restart`, `Simulator: Agree to run ...`) reachable over DUML; relevant to what Assistant does.
- **?** The CDC receive handler to DUML parser hand-off was not located. CRC constants (seed `0x77` / `0x3692`) occur at `0x806f884`, `0x806f8d6`, `0x8072a7a`, `0x807f304` etc.; `0x806f850` is an outgoing flight-log packet builder (length+12, XOR-masked payload), not the receive parser.

## Probe results (2026-10-23, battery on, `scripts/probe_fc_usb.py`)
- **V** Passive listen 3 s: 0 bytes.
- **V** DTR and RTS asserted by Linux; bulk-OUT accepted (tty output queue drains to 0): the flight controller reads the bytes.
- **V** No reply to DUML Get-Version (set `0x00` id `0x01`) or set `0x00` id `0x0e` with any of:
  - sender `0x0A`, `0x2A`, `0x02`, `0x00`
  - receiver `0x03` (FC), `0x01`, `0x04`, `0x07`, `0x00`, `0x0A`
  - cmd type `0x00` and `0x40`
  - header version 0 and 1
- Matches the 2017 report: silent on Linux, even with `cat`.
- **?** Not tried: other baud rates / line coding, other command sets, MSC mode, a host-side init.

## DJI's own Windows driver (DJI Assistant 2 For Phantom 2.0.10, `dji_vcom_driver11.inf`)
- **V** Confirms the port is genuine CDC-ACM with no vendor protocol at the USB-class level:
  `NTMPDriver=usbser.sys` — DJI's "VCOM" driver is Microsoft's generic CDC-ACM serial
  driver (`usbser.sys`), wrapped only so Windows auto-selects it for DJI's VID/PID list
  instead of leaving the device unrecognized. Matches Linux binding `cdc_acm` with no
  special driver needed, on the same device.
- **V** VID:PID table across DJI's product line extracted to
  `docs/data/dji-vcom-vid-pid.tsv` (25 entries). `fff0:0008` (this port, confirmed above)
  and `2ca3:0008` are the only two entries at interface `MI_00`/whole-device level with
  the same PID — `2ca3` is DJI's own registered USB VID, `fff0` looks like an earlier
  unregistered/placeholder VID used before DJI got `2ca3`. A `2ca3:1020` debug VCOM
  variant exists at `MI_02` ("DJI USB VCOM For Debug") distinct from the normal `MI_00`
  interface at the same PID — worth checking if the aircraft also exposes this.
- Installer source: `https://dl.djicdn.com/downloads/dji_assistant/20200721/DJI+Assistant+2+For+Phantom+2.0.10.exe`,
  genuinely DJI-signed (Authenticode: both a standard and an EV GlobalSign cert name
  "SZ DJI Technology Co., Ltd."; chain verification fails only on now-expired 2017-2020
  certs against a modern trust store, not on a digest mismatch - file is unmodified).
  Installed and run under Wine (`tmp/wine-dji/`, git-ignored, not committed) on an
  isolated Xvfb virtual display, never the real desktop.

## Attempted: live capture of DJI Assistant 2 under Wine (2026-10-23)

**V.** `scripts/re/wine_serial_proxy.py` was built and tested working: a transparent
relay (real `/dev/ttyACM*` <-> a pty) with live DUML (SOF `0x55`) reframing on both
directions, logging every byte with timestamp/direction regardless of which side
initiates. Wine's `HKLM\Software\Wine\Ports\COM1` was pointed at the proxy's pty, and
DJI Assistant 2 For Phantom 2.0.10 was installed cleanly (`/VERYSILENT` — it is an
InnoSetup installer, not NSIS; `/S` is silently ignored by it) on an isolated Xvfb
virtual display (`:99`, never the operator's real desktop/`:0`).

**V.** Assistant's own driver (`dji_vcom_driver11.inf`, confirmed DJI-signed) installs
under Wine as a no-op (`pnputil` is a Wine stub) but is unneeded anyway: our COM1
registry mapping bypasses Windows driver matching entirely.

**Not achieved: a live capture.** `DJI Assistant 2.exe` launches, runs its startup
sequence (WLAN/network-interface enumeration, `toolhelp32` snapshots - typical
Electron/CEF diagnostics), then exits silently with no window ever drawn and no
Windows exception/crash dialog, reproducibly, with or without `WINEDEBUG=+seh`
tracing (which showed only normal SEH unwinds, not a crash). No OOM-kill or SIGSEGV
in `dmesg`/`journalctl`. Likely cause (not confirmed): an Electron/CEF startup
network/update check against DJI's own servers failing in a way the app doesn't
handle gracefully under Wine's network/TLS stack - not chased further.

**V, found instead - static analysis of the installed app:**
- The UI is Electron (`DJIApp/app.asar`, extracted cleanly - unencrypted, standard
  asar format, `npx @electron/asar extract`); its 1.2 MB main JS bundle has no
  serial/DUML/VID-PID logic in it (only a couple of generic `WebSocket` feature-
  detection strings, from a bundled polyfill library, not DJI's own code).
- The real device layer is native: `DJIEngine/DJIService.exe` (Qt-based; exports
  `DJIWebSocketHandler` for local IPC to the Electron UI) plus `DJIEngine/
  Qt5SerialPort.dll` - the actual COM-port access uses Qt's generic serial-port
  framework, not a custom driver or protocol at the transport level. Consistent
  with the `usbser.sys` finding above: no vendor USB class anywhere in this stack.
  `DJIEngine/DJIDevice.dll` (363 KB) is almost certainly the DUML/device-protocol
  layer by name, but a `strings` pass found no readable VID/PID/cmd-set literals
  (expected: those compile to numeric immediates, not text, in native code) -
  reading it would need real x86 disassembly, not attempted this session.
- `DJIApp/SimTest/` (inside the asar) contains simulator test data/JS, not checked
  in detail - worth a look before any further live-capture attempt.

All Wine/Xvfb/proxy processes and the virtual display were torn down cleanly; the
real device was free (`fuser`/`lsof` empty) before and after. Installer and
extracted app files live under `tmp/` (git-ignored), not committed, per the
no-DJI-derivative-code convention already used for the Android APK work.

## Reference tooling (upstream)
- `comm_serialtalk.py` / `comm_og_service_tool.py` (o-gs/dji-firmware-tools): serial port, default 9600, sender type PC (`0`), receiver `ANY`, packet type Request, ack `No_ACK_Needed`. Phantom 3 listed as supported, so the same framing is expected.

## What is needed next
1. Find the VCOM data-out handler in `m0306` and read what gates DUML replies - the m0306 USB-OTG dead-ISR finding (`docs/fc-usb-duml.md`) may mean Assistant would get no reply either, independent of the Wine issues above.
2. If a live Assistant capture is still wanted: debug why it exits silently under Wine (try a newer DJI Assistant build with a possibly-different installer/runtime, or run on real Windows/a VM instead of Wine), or statically disassemble `DJIDevice.dll`/`DJIService.exe` for the protocol constants (x86 PE, different toolchain from the ARM firmware work elsewhere in this repo).
3. Rule out line-coding/baud dependence with a CDC SET_LINE_CODING sweep.

Scope: owned aircraft, interoperability only (see `../CLAUDE.md`). No key extraction, no geofence or flight-restriction work.

Tools: `scripts/probe_fc_usb.py`, `scripts/re/fc_usb_xrefs.py`. Wiki: https://github.com/o-gs/dji-firmware-tools/wiki/P3X-ESC-center-board , https://github.com/o-gs/dji-firmware-tools/wiki/P3-Flight-Controller-aka-MC
