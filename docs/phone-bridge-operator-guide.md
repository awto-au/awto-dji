# Phone/AOA bridge: operator's guide for taking this over

Everything needed to drive `awto_dji_app` on the test phone and the PC-side relay
without re-deriving it from chat history. Written so another agent/session can pick
this surface up directly. Nothing here is firmware RE - it's the app's own operator
surface.

## Topology

```
RC (USB host) --USB-A--> phone (Android, AOA accessory) --WiFi--> PC relay (aoa_relay_server.py, :9900)
                              |
                         awto_dji_app
```

- The **RC** is the USB host; the **phone** is an AOA accessory (not USB-serial). The
  phone must be plugged into the RC's **USB-A** port with a plain cable (no OTG
  adapter) - see `docs/aoa-live-test-2026-10-23.md`.
- The phone removes AOA envelopes and routes command/video payloads locally. If a
  relay is configured, it forwards complete, channel-tagged records to
  `scripts/re/aoa_relay_server.py`. The reverse direction carries raw DUML.
- **Check before assuming this topology is live**: the RC and aircraft are frequently
  plugged into the PC directly instead (for `duml_probe.py`/`duml_watch.py` work on
  `/dev/ttyACM*`) - `lsusb | grep -iE "2ca3|fff0"` tells you which.

## Test phone: finding and (re)connecting it

The phone has no fixed address - wireless-debugging picks a new port on every reboot.

1. `adb devices -l` - if already connected (USB or a prior `tcpip` session), it shows
   up as `<ip>:<port>`.
2. If not: the phone needs **Settings -> Developer options -> Wireless debugging**
   on, which shows its current IP:port. Ask the operator for it rather than guessing a
   port (the old default `5555` only works after step 3 below, not from a cold boot).
3. Once connected at whatever port Wireless debugging shows, run
   `adb -s <ip>:<old-port> tcpip 5555` then `adb connect <ip>:5555` - this moves it to
   a fixed, predictable port for the rest of the session (does not survive a reboot).
4. If a reboot happens mid-session, you're back to step 2 - the IP can also change
   (house DHCP), so re-ask rather than retrying the last known address blindly.

At the time of writing the phone is a Samsung S9 (LineageOS), package
`au.awto.dji.awto_dji_app`, with DJI GO 4 (`dji.go.v4`) also installed as a reference.

## Building and installing

```
cd app/awto_dji_app
flutter pub get
flutter test
flutter analyze                       # see known unrelated findings below
flutter build apk --debug
adb -s <ip>:5555 install -r build/app/outputs/flutter-apk/app-debug.apk
```

## Driving the app: intents, not a UI form

There is **no on-screen connect form** - `ConnectScreen` was removed. The app is
driven entirely by Android intents, handled in `MainActivity.kt` ->
`LinkHost.handle()` (`lib/link/link_host.dart`). A plain launch, or the RC's USB
accessory attaching, auto-connects with the default relay.

```
adb -s <ip>:5555 shell am force-stop au.awto.dji.awto_dji_app   # intents to a
                                                                   # running instance
                                                                   # silently no-op; stop first
adb -s <ip>:5555 shell am start -n au.awto.dji.awto_dji_app/.MainActivity \
    -a au.awto.dji.action.CONNECT --es relay 192.168.25.114:9900
```

| Action | Extras | Effect |
|---|---|---|
| `au.awto.dji.action.CONNECT` | `source` (`accessory` default / `simulated` / `replay`), `relay` (`host:port`, default `192.168.25.114:9900`), `relayVideo` (`true` default / `false`), `protection` (`auto` default / `none` / `simple`), `path`/`speed` (replay only) | Disconnects any existing session, builds a new transport, connects |
| `au.awto.dji.action.DISCONNECT` | none | Tears down the current session |
| `au.awto.dji.action.GIMBAL` | `pitch`/`roll`/`yaw` (deg), `duration` (ms, default 300), `overtime` (default 10) | Sends the permission request then the angle command - **no confirm dialog**, sends immediately |
| `au.awto.dji.action.SEND` | `set`, `id`, `receiver` (required), `sender` (default app), `ack` (0-2, default 2), `payload` (hex) | Any single DUML frame |

Status (what connected, errors, last send) is visible on screen (`LinkHostScreen`) -
screenshot via `adb exec-out screencap -p` rather than guessing state from logs alone.

## PC-side relay and command proxy

```
python3 -I scripts/re/aoa_relay_server.py --port 9900
```

- Point the app's `relay` extra (or the simulated-default baked into `LinkHost`) at
  this machine's LAN IP:9900.
- Receives phone relay v1 records, then independently decodes the original AOA
  envelopes via `scripts/re/aoa_mux.py` - the accessory stream is
  envelope-framed (`55 cc`, channel u16 LE, length u32 LE; channels `0x5749`-`0x574d`,
  corroborated against the APK's `usb/P3/b.java`), command on `0x5749` and camera video
  on `0x574a` - **supersedes `docs/aoa-live-test-2026-10-23.md`'s earlier "no demux
  header exists" conclusion**, check that doc's currency before relying on it. Logs to
  `captures/sessions/<date>/aoa_relay_{server,frames}.log` (tracked - real hardware).
- Update both the phone APK and PC server for the new wire format. For an older
  app that mirrors raw USB chunks, run the server with `--input-format raw`.
  Existing hex logs and `pc_video.py` remain compatible: RX log entries contain
  original AOA/discarded bytes, not the relay record headers.
- Also runs a **command FIFO** at `tmp/aoa_send.fifo`: anything written there (one
  hex-encoded DUML frame per line) gets forwarded to the phone's accessory `write()`,
  reaching the RC exactly like an app-originated frame - a way to inject frames from
  the PC with no app UI involved. Send via `scripts/re/aoa_send.py`, not by hand-typing
  into the FIFO.
- `scripts/re/aoa_send.py --set 0x04 --id 0x0a --receiver 0x04 --payload ...` - raw
  one-shot frame builder. `scripts/re/duml_commands.py` + `duml_cli.py` are the
  declarative, byte-exact (matched against the decompiled APK's own `doPack()`)
  alternative for specific commands (gimbal, etc.) - prefer these over hand-built
  frames when a command is already declared there.

## Gotchas already paid for

- **Gimbal sends need the APP device-type sender** (`DeviceType.app`, not PC) and a
  permission request first (RC cmdset `0x06`/`0x22`, receiver OSD `0x0e`) or the
  gimbal silently ignores the angle command - both are handled automatically by
  `GimbalCommands`/`LinkHost.sendGimbal`, don't hand-roll this.
- **`am start` to an already-running instance is a silent no-op** - force-stop first,
  or the intent appears to do nothing.
- Relaunching the app after an install resets to the simulated/default source only if
  you pass no `source` extra and nothing auto-triggers `CONNECT` - check `am start`'s
  actual extras, not assumptions, if the app comes up in the wrong mode.
- DUML now supports the matched SIMPLE-XOR table. CONNECT accepts
  `--es protection auto` (default), `--es protection simple`, or
  `--es protection none`. Auto learns from valid received frames; SIMPLE selection
  follows the APK's COMMON/camera exclusions. Explicit protected packets are not
  transformed twice. See `docs/duml-protection.md` for behavior and test limits.
  This is software-tested support; no new hardware interoperability result is implied.

To select SIMPLE for a connection, append `--es protection simple` to the existing
CONNECT intent command. `--es protection auto` restores automatic mode for the new
connection; `--es protection none` leaves outgoing wire frames as supplied. A
connection change closes the previous session and resets learned peer mode.

## Minimal channel-routing implementation (issue #23)

The phone has one AOA envelope parser. Only `COMMAND=0x5749` payloads feed
`DumlProtection` and the telemetry session. Only `CAMERA_VIDEO=0x574a` payloads
feed the Annex-B extractor; start codes/NALs may span envelopes. Parser, video
tail and learned protection state reset at connection boundaries.

Forwarding video is **on by default**. Append `--es relayVideo false` to CONNECT
to suppress camera `0x574a` and FPV `0x574b` records on WiFi; local camera
decoding continues. Command records and unknown `0x574c`/`0x574d` records
always forward. Discarded USB spans, including incomplete final envelopes, also
forward as diagnostic records and remain visible in the PC hex log.

Phone-to-PC records have this 12-byte header, followed by the stated payload:

| Offset | Field |
|---|---|
| 0–3 | ASCII `AWTO` |
| 4 | Version `1` |
| 5 | Kind `1` = original complete AOA envelope; `2` = discarded USB bytes |
| 6–7 | Channel u16 LE; zero for discarded bytes |
| 8–11 | Payload length u32 LE, bounded to 1 MiB + 8 |

Kind 1 retains the original eight-byte AOA header so the PC can check channel and
length against the phone's record header. TCP reads may split or combine records.
The PC independently parses/decodes, including SIMPLE, but **automatic comparison
against the phone's decoded fields is deferred**. No phone verdict metadata,
per-channel UI or key exchange is part of this MVP. A valid-looking incomplete
AOA envelope waits for its advertised payload until disconnect; no speculative
resync inside a payload is attempted.

The inject-back FIFO remains raw DUML, without relay/AOA headers. The phone
reassembles fragmented/coalesced TCP frames and applies the selected SIMPLE
policy before the existing accessory write.

Validation: 30 app tests and 28 DUML tests; nine Python parser/relay tests.
Mocked USB plus a loopback TCP server cover channel isolation, both video toggle
settings, unknown channels, fragmented commands, discarded bytes, and reconnect
state. The APK is built, not installed or live-tested. Full app analysis retains
two unrelated findings in `video_decoder.dart` and `video_screen.dart`.
Android MediaCodec input-buffer scheduling remains a separate known limitation;
see [PC video notes](pc-video-preview.md).

## What this doesn't cover

- The aircraft's **front micro-USB port** (`/dev/ttyACM11` on the PC, not through the
  phone at all) - that's `docs/fc-usb-duml.md` + `scripts/re/duml_probe.py` /
  `duml_watch.py`, a separate, PC-direct surface.
- Camera SD-card / Ambarella Linux access - `docs/camera-linux-console-access.md`.
