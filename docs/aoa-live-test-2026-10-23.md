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
## Correction (same day): no demux header exists - the CRC-failing frames are expected resync noise

Checked DJI's public Mobile SDK (`dji-sdk/Mobile-SDK-Android`) first, before digging further
into the APK: **dead end, not useful here.** MSDK doesn't support Phantom 3 at all (starts at
the Phantom 4 era; v5 only lists Enterprise/Matrice/Mavic 3E products); even where it does apply
to a product, the SDK core ships as a closed Maven `.aar`, not source - this repo is samples/docs
only. `dji-sdk/Onboard-SDK` is genuinely open source but a different product family (UART
companion-computer link for A3/N3/M100), not Phantom 3's AOA/DUML-over-USB. The APK remains the
only official-ish source for this specific product's protocol.

Reanalysed the full relay capture (concatenated raw bytes across the whole session,
`tmp/logs/aoa_relay_server.log`, 496,370 bytes) by scanning for every header-CRC8-valid SOF
position, not just the first few the live framer happened to log:

- **V.** 79 header-CRC8-valid SOF positions found; **75 of them also pass the full CRC16.**
  Within each burst, consecutive valid frames sit with **zero gap** between them - i.e. the
  stream genuinely is clean, correctly-framed, back-to-back DUML in those regions, not
  multiplexed with any per-frame channel/length header.
- **V.** Decoded all 75: real, live telemetry. `sender=0x03` (flight controller) pushes with
  smoothly incrementing `seq` (11414->11420), `sender=0x04` (gimbal) and `sender=0x01` (camera)
  likewise, all addressed to `receiver=0x02` (app/mobile devicetype). One frame
  (`sender=0x08`/DM368 sky-end, `set=0x00 id=0xf0`) carries a readable ASCII status line:
  `T:3174:558 R:0 H:1 L:1 USB:0 BW:80 SBR:5028 SFR:30` - a real air-side video-link status
  string, not noise.
- **Conclusion: there is no demux header to find.** The large gaps between bursts (50-90 KB)
  are something else entirely sharing the same raw accessory pipe - almost certainly the video
  stream, per `apk-analysis.md`'s already-correct note that there's "no second USB channel" -
  not DUML frames with a missing wrapper. The earlier "most frames fail CRC" observation was the
  framer's SOF-scanner finding occasional coincidental `0x55` bytes inside that non-DUML payload
  (expected: roughly 1/256 chance per byte of a false CRC8 match) and correctly rejecting them on
  CRC16 - ordinary resync behaviour, not a protocol problem needing a fix.
- **What actually needs fixing, if anything:** cosmetic only - the relay script and the app's UI
  log CRC16 failures as "errors" with equal visual weight to real frames, which reads as "mostly
  broken" when it's actually "working exactly as designed, with expected noise in between."
  Consider: only surface CRC16-valid frames by default, or label non-matches as "resync" rather
  than "error".

## What is needed next

1. Cross-check decoded OSD/telemetry fields against the aircraft's real state (it was stationary
   on a bench during this test - expect near-zero velocity/attitude change). Not yet done: these
   cmdset/id values (`0x03/0x1e` etc.) aren't yet named against `app/packages/duml`'s catalog.
2. Identify what the large inter-burst gaps actually carry (video, most likely) by checking
   whether their byte patterns match known H.264 start-code patterns, cross-referencing
   `apk-analysis.md` section 4 (video path, `dataType` 22346).
3. Make a longer capture (this one was ~500 KB) to see the burst period precisely and confirm it
   lines up with a plausible telemetry push rate (10 Hz typical for OSD per other docs in this
   repo).

Reproduce: `flutter build apk --debug` in `app/awto_dji_app/`, install on an Android device
connected to the RC's USB-A port, select "Android accessory (RC)" with the diag relay field set
to `<dev-machine-ip>:9900`, and run `python3 -I scripts/re/aoa_relay_server.py --port 9900` on
the dev machine first. Logs: `tmp/logs/aoa_relay_server.log` (raw), `tmp/logs/aoa_relay_frames.log`
(decoded, CRC-tagged).
