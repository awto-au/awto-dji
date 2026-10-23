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

## Reference tooling (upstream)
- `comm_serialtalk.py` / `comm_og_service_tool.py` (o-gs/dji-firmware-tools): serial port, default 9600, sender type PC (`0`), receiver `ANY`, packet type Request, ack `No_ACK_Needed`. Phantom 3 listed as supported, so the same framing is expected.

## What is needed next
1. Capture the Windows DJI Assistant session with usbmon/Wireshark: shows any init or mode-switch the port needs. Best lead.
2. Otherwise: find the VCOM data-out handler in `m0306` and read what gates DUML replies.
3. Rule out line-coding/baud dependence with a CDC SET_LINE_CODING sweep.

Scope: owned aircraft, interoperability only (see `../CLAUDE.md`). No key extraction, no geofence or flight-restriction work.

Tools: `scripts/probe_fc_usb.py`, `scripts/re/fc_usb_xrefs.py`. Wiki: https://github.com/o-gs/dji-firmware-tools/wiki/P3X-ESC-center-board , https://github.com/o-gs/dji-firmware-tools/wiki/P3-Flight-Controller-aka-MC
