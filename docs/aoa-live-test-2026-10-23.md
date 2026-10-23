# First real-hardware AOA test: `awto_dji_app` vs the RC's USB-A port (2026-10-23)

Status tags: **V** verified here, **I** inferred, **U** unknown. Hardware: owner's P3 Pro RC,
Samsung S9 (LineageOS) connected to the RC's USB-A (phone) port via a plain cable - no OTG
adapter needed, the RC is the USB host on this port (see `docs/fc-usb-port.md` for the
separate micro-USB/PC-facing port, which is a different physical connector).

## Setup

- **V.** `adb tcpip` + `adb connect` to the S9 over WiFi (no cable to the dev machine needed).
  `dumpsys usb` confirmed a genuine AOA (Android Open Accessory) handshake before any app was
  even running: `current_functions=ACCESSORY`, `connected=true`, `configured=true`,
  `current_accessory={manufacturer=DJI, model=T600, description=DJI, version=v1.2.3.4,
  uri=www.dji.com, serial=12345678}`. This resolves the "U" in `docs/apk-analysis.md` section 1
  ("Version/description/uri/serial strings the app sends") - these are real values read
  straight off the device, with no app involved; Android's own accessory-gadget detection
  surfaces them automatically.
- **V.** Built `app/awto_dji_app` (debug APK), installed on the S9, selected "Android accessory
  (RC)" on the Connect screen. The manifest's `USB_ACCESSORY_ATTACHED` intent-filter + Android's
  own "open with this app" dialog granted USB permission in one tap - no further friction.
- **V.** Added a debug-only TCP relay (`lib/debug/tcp_relay.dart`, wired into `AoaTransport` via
  an optional `relayHost`/`relayPort`, exposed as a "Diag relay host:port" field on the Connect
  screen) that mirrors every raw accessory byte chunk to a plain TCP listener
  (`scripts/re/aoa_relay_server.py`) on the dev machine. Lets the real DUML decoder run natively
  in Python instead of needing an APK rebuild per protocol change. Also added `debugPrint`
  logging at the two transport-agnostic chokepoints (`LinkSession._onBytes`/`_onBad`,
  `BaseTransport.setState`), so `adb logcat` alone shows connection state and every
  received/bad frame without screenshots.

## Result

- **V.** Real bytes flow continuously over the AOA link - unlike the PC-facing micro-USB port
  (`docs/fc-usb-port.md`), which is provably silent to any DUML command from a PC, this port is
  actively producing data the moment the accessory connection opens.
- **V.** Most of what `scripts/re/aoa_relay_server.py`'s naive SOF-scanning DUML reframer finds
  fails CRC (header CRC8 and/or full CRC16) - but **not all of it**. A handful of frames pass
  *both* checks outright, e.g.:
  `sender=0x03 receiver=0x02 ... hdrCRC=ok crc16=ok` (flight controller -> app/mobile devicetype)
  `sender=0x0e receiver=0x02 ... hdrCRC=ok crc16=ok`
  This is strong confirmation, not just inference, of what `docs/apk-analysis.md` already named
  from the APK's class structure: the raw AOA byte stream is multiplexed (DUML + video/other via
  a Lightbridge channel-ID layer, `DJIPluginLBChanneParser`/`DJILBChannelID`), and a bare
  DUML framer run directly on the raw stream will only ever find real frames by chance, landing
  on a DUML-channel byte run.
- **I, not yet located:** the actual channel/length header DJI's own code strips before handing
  bytes to the DUML parser. This is the concrete missing piece - not a DUML framing bug, not an
  AOA transport bug (both already proven correct/working here), just a missing demux stage.

## What is needed next

1. Find the LB channel-ID demux layer: either from `DJIPluginLBChanneParser`'s real behaviour
   (would need arm64 bytecode/native analysis the APK work declined, or a public dissector that
   already covers it), or empirically from the relay capture (look for a periodic marker/length
   field that, once stripped, makes *all* SOF-aligned frames pass CRC, not just the lucky ones).
2. Once demuxed, cross-check decoded OSD/telemetry fields against the aircraft's real state
   (it was stationary on a bench during this test - expect near-zero velocity/attitude change).
3. Asked the parallel session (real Windows VM, live Assistant session) whether DJI's own
   app.asar/native code names the demux header explicitly - not yet answered.

Reproduce: `flutter build apk --debug` in `app/awto_dji_app/`, install on an Android device
connected to the RC's USB-A port, select "Android accessory (RC)" with the diag relay field set
to `<dev-machine-ip>:9900`, and run `python3 -I scripts/re/aoa_relay_server.py --port 9900` on
the dev machine first. Logs: `tmp/logs/aoa_relay_server.log` (raw), `tmp/logs/aoa_relay_frames.log`
(decoded, CRC-tagged).
