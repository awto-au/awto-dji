# Aircraft front micro-USB port (flight controller, VID `fff0` PID `0008`)

Status of each claim: **V** verified here, **W** from the o-gs wiki / issues (not re-checked), **I** inferred, **?** unknown.

## What it is
- **V** The aircraft's front micro-USB ("Assistant" port) enumerates on Linux as `fff0:0008`, product `DJI CONTROLLER`, manufacturer `DJI`, serial `0001A0000000`.
- **V** Serial is a fixed string: same value reported on a Phantom 3 Standard in 2017 (o-gs/dji-firmware-tools#43).
- **V** Descriptor: full-speed, class 2 CDC-ACM, interface 0 comm (interrupt IN `0x82`, 8 B), interface 1 data (bulk OUT `0x01`, bulk IN `0x81`, 64 B), self-powered, 100 mA. Linux binds `cdc_acm` (`ttyACM*`).
- **W** Socket is on the P3X ESC/center board (WM320_ESC_CENT_v4, P01012.07/.09); a ribbon carries USB D+/D- to the flight-controller daughterboard (pads 3/4 on the 20-pin side).
- **W** Wiki describes it as USB-to-TTL to the flight controller carrying DUML, 9600 8N1.
- **V** `m0306` carries the `DJI CONTROLLER` / `0001A0000000` descriptor strings. **I** that the flight controller is therefore the device answering on this port: its USB interrupts are dead in the vector table, and which MCU actually answers is unresolved (#21).

## CPU behind it
- **W** Flight controller ("MC", P01006.05), `air_fc_stm32f427`: STM32F427IIH6, Cortex-M4F, 180 MHz, 2 MB flash. Firmware modules `m0305` (loader), `m0306` (app).
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

## Wine debugging, attempt 2 (2026-10-23)

Same prefix (`tmp/wine-dji/`, wow64, `wine-11.0 (Staging)`), new Xvfb `:99`. Real FC
at `/dev/ttyACM11` was present but idle (`fuser`/`lsof` empty) throughout - never
opened, this session was diagnosis-only, no proxy/capture attempt made.

**V. Original "network/update check fails" hypothesis is REFUTED.** Traced with
`WINEDEBUG=+winsock,+wininet`: the app resolves `mydjiflight.dji.com` (AWS-hosted,
`13.32.45.x`), connects over TLS on port 443 using the standard nonblocking-connect
two-call idiom (first call returns "in progress", second confirms), and the
exchange **succeeds**. Confirmed independently with `curl -v` from the host to the
same IPv4 address (IPv6 route is unreachable here, but IPv4 completes a full
TLS 1.3 handshake).

**V. DJIService.exe's own log file proves the login round-trip completes.**
Electron/Qt-side logging writes to
`%APPDATA%\DJI Assistant 2\Phantom\log\<timestamp>.log` inside the prefix
(not found/mentioned in attempt 1). Two independent runs produced byte-identical
sequences:
```
[DJIWebFileGetter] [OnFinish]reply statusCode=201
[DJIWebFileGetter] [OnFinish]reply statusCode=200
[DJILogin] Get C############## from server: 6175
release class DJIIdentifierInterface<class DJISecondIdentifier>
release class DJIIdentifierInterface<class DJIGeneralIdentifier>
```
(DJI's own logger redacts the identifier value with `#`.) HTTP 200, a value
returned from the server, then clean teardown of the identifier objects - not an
error path.

**V. `WINEDEBUG=+loaddll,+module` traced the actual process tree** (not captured in
attempt 1): `DJI Assistant 2.exe` relaunches itself once (single-instance pattern,
PIDs `0024` -> `0130`), which spawns `DJIEngine/DJIService.exe` (`0138`) and
`DJIEngine/DJIBrowser/DJIBrowser.exe` (`014c` - the actual CEF render host, not
mentioned in attempt 1's static analysis). **All four processes exit via a clean,
voluntary `LdrShutdownProcess()`** - no SEH exception, no fixme/err around the
exit point, in both the relauncher and the two "worker" processes alike. `0130`
(the relaunched main exe) reaches `ExitProcess` within a few hundred trace lines of
loading just `kernel32`/`kernelbase` - it never loads any Electron/CEF-identifying
module (no `libcef`, `node`, `ffmpeg`), meaning its own entry point barely runs any
app logic before quitting.

**I. Working theory now: a shared startup/environment gate in DJI's own code, not
a network or Electron-specific fault.** `DJIService.exe` launched **standalone**
(bypassing the Electron launcher entirely) reproduces the exact same pattern: runs
its real startup diagnostics (WLAN enumeration, `toolhelp32` snapshot - identical
to attempt 1's description), then exits voluntarily on its own, with no parent
process and nothing to report back to. Every binary in the suite that was tried
exits the same way independent of launch order or parent/child relationship,
which points at common gate code (e.g. an environment/signature/anti-tamper check
shared across the DJI engine binaries) rather than a per-process bug. Not
confirmed - would need an x86 disassembly pass on the shared startup path to
pin down (same class of work flagged as outstanding in attempt 1).

**V. `DJISimulatorUI.exe` (a different EXE in the same `DJIEngine/` folder) behaves
completely differently** - it is not subject to whatever gate stops the other
three. It runs for real: loads a full OGRE3D scene (flight-sim aircraft models,
textures, shader compositors), logs normal asset-parsing output, then **crashes**
with `wine: Unhandled stack overflow at address 7B31E867 (thread 0138)` after a
`WARNING: ... Fragment program GlowB_fp cannot be used - not supported` (the
software/llvmpipe GL path lacks a fragment-program feature the Glow compositor
needs). This is a genuine Wine/GL compatibility crash, unrelated to the other
exes' silent-exit pattern - interesting confirmation that *some* window-drawing
DJI code path does run under this Wine setup, but not useful for DUML capture
(it's the flight simulator, not the device-comms UI).

**Not achieved: a live capture, and no DUML bytes were sent or received this
session** - no serial proxy was started, since the Electron UI (the one process
that would open the COM port) never got far enough to try. `glxinfo` on `:99`
confirms direct rendering/GLX works (SGI GLX 1.4, llvmpipe), so GL itself is not
the blocker for the Electron/CEF side specifically.

Winetricks already has `dotnet40`/`dotnet48`/`winxp` installed in this prefix
(from attempt 1 or earlier); `vcrun2013`/corefonts/d3dcompiler (task's approach 3)
were not tried this session since msvcr120/msvcp120/vcomp120 ship inside
`DJIEngine/` already (confirmed by directory listing) - no missing-CRT symptom
was observed, so that avenue looks unlikely to be the cause and wasn't pursued
further given the gate-pattern evidence above.

All wine processes (`wineserver -k`) and the Xvfb `:99` process were torn down;
confirmed via `ps aux` (no `wine`/`Xvfb` left) and the real FC device
(`fuser`/`lsof` on `/dev/ttyACM11`) was empty before, during and after.

## Reference tooling (upstream)
- `comm_serialtalk.py` / `comm_og_service_tool.py` (o-gs/dji-firmware-tools): serial port, default 9600, sender type PC (`0`), receiver `ANY`, packet type Request, ack `No_ACK_Needed`. Phantom 3 listed as supported, so the same framing is expected.

## Real-hardware re-test after the ~6s boot-to-IRQn67-unmask finding (2026-10-23)

The Renode-simulated boot (`docs/fc-usb-duml.md`) showed the firmware's IRQn67 (OTG_FS)
interrupt stays masked until ~6s into a simulated boot, raising the possibility that earlier
probes (which started as soon as `/dev/ttyACM11` existed, with a 3s passive window) simply
ran too early relative to the real board. Retested directly:

- **V.** Power-cycled the aircraft battery. `lsusb` showed the DJI controller re-enumerate
  under a new USB device number (103 -> 104); `/dev/ttyACM11`'s ctime jumped accordingly -
  confirms a genuine reboot happened, not just a stale cached listing.
- **V.** A passive 60s capture (`scripts/re/capture_fc_boot.py`, no bytes transmitted)
  started 16s after the confirmed reboot and ran for a further 60s (so covering roughly
  t+16s to t+76s post-reboot, well past the 6s simulated-boot mark): **0 bytes received.**
  No unsolicited boot-time log/telemetry output on this port at all, at any point in that
  window.
- **V.** Immediately after, `scripts/probe_fc_usb.py` sent DUML Get-Version to all four
  targets (flight-controller, camera, gimbal, rc/ofdm) against the same now-confirmed-fresh
  boot: **0 bytes received** for every target, same as the original 2026-10-23 probe and the
  2017 public report.
- **Conclusion: the ~6s boot timing was not the explanation for the silence.** The port is
  silent whether probed right after device-node creation or minutes into a confirmed-fresh
  boot. Narrows the real cause back toward the m0306 USB-OTG dead-ISR / CDC-receive-handler
  question in `docs/fc-usb-duml.md`, not a premature-probe timing artifact.

## RC's own micro-USB port, and receiver-address sweep (2026-10-23)

With the RC also connected: `lsusb` shows a second DJI USB device, `2ca3:0008`
(`/dev/ttyACM4`), distinct from the aircraft's `fff0:0008` (`/dev/ttyACM11`). Noted for the
VID/PID table: this one's USB serial string is `DJI_CONFIF_DJI_CONTROLLER_0001A0000000` -
same serial number as the aircraft, with manufacturer string `DJI  CONFIF  ` (likely a
truncated/garbled "CONFIG") - the lsusb database label "Mavic Mini MR1SD25 Remote
controller" is almost certainly a generic cached USB-ID-database string DJI reused across
RC hardware revisions, not evidence this is actually Mavic Mini hardware.

**Resolved (2026-10-25):** this is `gnd_rc_lpc1765`'s (m1400) **own on-chip USB device
stack**, not the FX3 (`gnd_fx3_cyusb2014`) and not a second bridge chip — the manufacturer/
product/serial strings above are literal constants inside m1400's own compiled image, and
the port's `VCOM`/`MSCM` class-tag pair matches this doc's own FC-side pattern exactly. Full
finding: `ground-upgrade-path.md` §"Q5: the RC's own micro-USB port".

- **V.** `scripts/probe_fc_usb.py` run against `/dev/ttyACM4` (the RC port): same result as
  the aircraft port - 0 bytes passive, 0 bytes on Get-Version to all four `TARGETS`.
- **V.** Retried Get-Version addressed to receiver `0x06` (RC devicetype, per this repo's
  own `app/packages/duml/lib/src/catalog.dart` - `probe_fc_usb.py`'s `TARGETS` dict labels
  `0x07` "rc/ofdm", which is wrong for "RC"; `0x06` is the correct RC devicetype) on *both*
  ports: still 0 bytes either way.
- **Conclusion:** silence is not explained by boot timing (previous section) nor by
  receiver-address choice - tried `0x01`/`0x03`/`0x04`/`0x06`/`0x07` across both the
  aircraft's and the RC's own USB ports, all silent. Narrows further toward either (a) a
  host-side handshake/wake sequence Assistant performs that a bare DUML send doesn't
  replicate, or (b) the CDC-receive-to-DUML-dispatcher gap already suspected from the
  m0306 ISR work in `docs/fc-usb-duml.md` being a shared code path across both MCUs.

## Community cross-check: this is a known, longstanding, still-unsolved symptom (2026-10-23)

Searched for prior reports of the exact symptom (correctly-framed DUML from a PC over
serial, no reply) before assuming it's specific to this setup or this probe method.
Found `o-gs/dji-firmware-tools#25` ("P3 Serial Data", 2426 lines, 2017-2021, the main
community RE thread for this protocol family across Phantom 3/Mavic/Spark).

- **V.** Another researcher (`Mavic129`) reported the **identical symptom** on a Mavic:
  sending a correctly-framed DUML packet from a PC over serial "didn't get any reply from
  the drone." This is the same family of firmware/protocol, same symptom, independently
  observed years before this session, with no fix found in the thread.
- **V.** The thread's own deciphered cmd-type semantics (`pawelsky`: 9th byte `0x00`=No ack,
  `0x20`=Push, `0x40`=Ack, `coptersafe`: `0x80`=just return) match what this repo's probes
  already tried (`cmd type 0x00 and 0x40` - the value documented as eliciting a response).
  Framing/sender/cmd-type were not the gap.
- **V.** Across the entire thread, every real protocol decode comes from **passively
  sniffing** FC<->ESC, FC<->battery, or FC<->GPS UART bus traffic, or from reading DJI
  Assistant's own extracted `app.asar` - not from a PC successfully injecting a command on
  the USB "Assistant" port and getting a reply. No one in this thread demonstrates working
  PC-initiated serial command/response on this specific port, on any aircraft in the
  product family.
- **Reframes the open question:** this was never a "did we frame the packet wrong" problem.
  It's either a per-session/per-device handshake that only DJI's own Assistant software
  performs (and that no public RE effort has reproduced, in years of community effort), or
  a firmware-side gap consistent with the m0306 dead-ISR/no-dispatcher findings in
  `docs/fc-usb-duml.md` - and if it's the latter, it would explain why the community never
  found a fix either, since there'd be nothing in the firmware to find.

## Why Assistant 2 says "device not supported" (2026-10-23)

A real-Windows-VM capture (parallel session, `win11` VM, genuine DJI Assistant 2 For
Phantom 2.0.10) showed the RC (`2ca3:0008`) correctly answering Get-Version
(`GL300C`, build `WM320_A7_LPC1 20170828/00`), then Assistant reporting the device as
unsupported. Checked whether this is a firmware-version problem (fixable by an
upgrade/download) or something else.

- **W, from DJI's own support forum threads** (`forum.dji.com` and `sdk-forum.dji.net`,
  multiple independent threads): **DJI Assistant 2 does not support the Phantom 3 series
  at all** - this is DJI support's own stated answer to other users hitting the same
  "device not supported" message on Phantom 3/GL300-family controllers. DJI support's own
  suggested fix in these threads is to use **DJI GO** (the mobile app), not Assistant 2, for
  Phantom 3 firmware/controller updates - matching the official Phantom 3 Pro support
  page's own tutorial list ("Upgrading the aircraft firmware on the Phantom 3", "Upgrading
  the firmware of remote controller" - both app/USB-SD-card based, no PC "Assistant" tool
  listed).
- **Conclusion: not a version mismatch, no firmware upgrade fixes this.** Assistant 2 (built
  for the Phantom 4 Pro V2 / newer GL300L-style controller generation) was never the right
  tool for a Phantom 3 Professional + GL300C pairing, regardless of firmware version on
  either side. `WM320`/`20170828` are consistent, correctly-paired, in-era firmware/RC
  builds - there is nothing stale to upgrade.
- **Also explains the FC USB-DUML silence findings above**: the "PC app talks DUML directly
  over USB to the aircraft" workflow was introduced for later DJI product generations.
  Phantom 3 was never designed to be driven that way, consistent with (not necessarily
  caused by) the m0306 dead-ISR/no-PC-dispatch findings in `docs/fc-usb-duml.md` - there
  may genuinely be nothing on DJI's side to find, because no DJI PC tool ever needed that
  path for this product.

## Replaying the real working Windows request on Linux - still silent (2026-10-23)

A parallel session got a genuine reply from the RC (`2CA3:0008`) on a real Windows 11 VM
using `o-gs/dji-firmware-tools`' `comm_serialtalk.py` (documented in
`docs/usb-tools-test-2026-10-23.md`). Replayed the exact same tool/command on Linux against
the same physical RC to isolate whether the earlier silence was a parameter mistake on this
side or a real platform difference.

- **V.** First attempt omitted `comm_serialtalk.py`'s `-a` (ack type) flag, which defaults to
  `No_ACK_Needed` - this produced a packet with ack-byte `0x00` (`...0a 0e 00 00 00 00 01...`),
  not `0x40`. This is exactly the cmd-type/ack byte the o-gs community thread (`#25`, cited
  above) says the FC/RC only responds to at `0x20`/`0x40`. Genuinely a parameter mistake, not
  evidence of anything.
- **V.** Retried with the Windows doc's exact working flags (`-b 115200 -a 2`, same
  `-t 1000 -r 1400 -s 0 -i 1`): produced the **byte-identical** request
  (`55 0d 04 33 0a 0e 00 00 40 00 01 e8 03`) to the one documented as working on Windows,
  against the same physical device (`/dev/ttyACM11`, re-verified via udev `by-id` immediately
  before the test, same `2CA3:0008` RC). **Still a timeout - zero bytes back.**
- **Conclusion: the packet is provably not the problem.** With byte-exact framing ruled out,
  whatever makes Windows work and Linux silent must be below the DUML layer - CDC control
  transfers (`SET_LINE_CODING` stop-bits/parity, not just baud; `SET_CONTROL_LINE_STATE`
  DTR/RTS sequencing/timing) that Windows' `usbser.sys` and Linux's `cdc_acm` may issue
  differently, or something timing-sensitive the kernel driver doesn't replicate. Asked the
  parallel session (which has the pcap) for the exact control-transfer parameters to check
  against what Linux's `cdc_acm` sends - not yet answered.

## Cross-check against the Windows "don't toggle after open" finding (2026-10-23)

The parallel session's `docs/p3-usb-observations-2026-10-23.md` found: the aircraft's one-way
log stream stops if DTR/RTS are changed *after* `open()`, regardless of the final value - three
different fixed combos (0/1, 1/1, 1/0) all worked when set once before open; a post-open change
(even a 0/0 pulse) stopped it. This matched my own earlier Linux test exactly (open, then
`TIOCMSET` - a post-open edge), so retried cleanly.

- **V.** Re-tested with a single `open()`, line config folded into one `tcsetattr` call, **no**
  `TIOCMSET` call at all afterward (accepting `cdc_acm`'s default auto-assert, confirmed
  DTR=1/RTS=1 - one of the three combos the Windows test found working). 15 s listen:
  **still 0 bytes.**
- **Confound, not controlled for:** getting `/dev/ttyACM11` back required an explicit unbind/bind of the USB device immediately before this test. Its interfaces had been claimed via `usbfs` by something that exited without releasing them (cause not identified).
  - That rebind is itself a device-level reconfiguration (likely another `SET_LINE_CODING`/line-state equivalent).
  - So this test does not cleanly isolate "clean single open" from "freshly re-enumerated after an unrelated reset."
- **Also uncontrolled:** the aircraft is stationary on a bench. The log lines seen in the Windows capture (`gimbal pitch/roll/yaw`, `gps init`, `compass stuck`) look like transient boot/state-change events, not a guaranteed continuous stream.
  - Silence here may mean "nothing new to log" rather than "stream gated."
- **V, tried.** Replicated Windows' exact two-stage line-coding sequence (`tcsetattr` to 9600,
  then to 115200 on the same fd, no close in between): **still 0 bytes**, 10 s listen.
- **Status: still inconclusive on Linux, but the negative result is now thorough.**
  - Tried on this port: baud 9600/115200/two-stage, all three DTR/RTS combos the Windows test found working (pre- and post-open), 5 receiver addresses, byte-exact packet replay of the working Windows request, and a clean single-open with no post-open control-line change.
  - Silent every time, on the same physical device that answers correctly from Windows on the same host.
  - The real remaining uncontrolled variable is whether the aircraft has anything to spontaneously log *right now* (idle on a bench, not flying). Further port/baud/DTR tuning cannot resolve that.
  - Not pursuing this angle without new information (e.g. a capture confirming the log stream is genuinely continuous/periodic, not event-triggered).

## Cross-product cmdset fuzz - also silent (2026-10-23)

Per the operator's "a command from another product might be a hint" idea: swept every cmdset
number the public dissector names (0-23, 28, 33 - including product generations the Phantom 3
doesn't nominally use, e.g. `FPGA Air`(19), `FPGA Ground`(20), `Automation`(16), `BVision`(18),
`MavLink`(22), `Watch`(23)) with a Get-Version/Ping probe against the aircraft's port
(`scripts/re/cmdset_fuzz.py`).

- **V.** All 52 cmdset/id combinations: **silent.** No cmdset from any product generation gets
  a reply from this port. Thorough, not a sampling - this specific hypothesis is now closed for
  this port.
- **Also tried (same session): "Enter Loader" (`RequestUpgrade`, cmdset 0 id 7)**, on the theory
  that a bootloader-level check might respond even though the application firmware doesn't -
  **also silent**, no behaviour change observed, device re-enumerated normally afterward.
- Not yet tried against the RC's own port (`2ca3:0008`) - the RC is known to answer correctly to
  its own cmdset already, so a parallel fuzz there would show whether *any* other cmdset gets a
  reply from a device that's proven responsive, vs the aircraft which has never replied to
  anything all session. Deferred: the RC was actively attached to the parallel session's VM for
  a live Assistant 2 debug-mode test at the time this was run - not taken away mid-test.

## What is needed next
1. Find the VCOM data-out handler in `m0306` and read what gates DUML replies - the m0306 USB-OTG dead-ISR finding (`docs/fc-usb-duml.md`) may mean Assistant would get no reply either, independent of the Wine issues above.
2. If a live Assistant capture is still wanted: the silent exit is NOT a network/CEF-startup issue (refuted above, with independent host-side confirmation) - every DJI engine binary tried (DJIService.exe standalone included) exits the same voluntary way, pointing at a shared gate in DJI's own startup code (possibly anti-tamper/environment detection, akin to the DJI GO 4 APK's AppGuard packer). Next: x86-disassemble the shared init path in `DJIDevice.dll`/`DJIService.exe` to find the actual gate condition, or try real Windows/a VM instead of Wine to sidestep it entirely.
3. Rule out line-coding/baud dependence with a CDC SET_LINE_CODING sweep.

Scope & safety: see `SAFETY.md`.

Tools: `scripts/probe_fc_usb.py`, `scripts/re/fc_usb_xrefs.py`. Wiki: https://github.com/o-gs/dji-firmware-tools/wiki/P3X-ESC-center-board , https://github.com/o-gs/dji-firmware-tools/wiki/P3-Flight-Controller-aka-MC
