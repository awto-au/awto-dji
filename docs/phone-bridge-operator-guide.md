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

- **U.** `./dev.py phone-connect [--serial S] [--connect IP:PORT]` resolves the phone: `--serial`, else `$AWTO_PHONE`, else the one usable `adb devices -l` entry (a phone listed over USB and wireless resolves to the wireless one); several or none: prints the list and exits 1. Prints serial, model, Android release and installed state of `dji` (`au.awto.dji.awto_dji_app`), `bench` (`au.awto.aoabench`), `old-bench` (`au.awto.dji.awto_dji_app.aoabench`, superseded).
- Wireless-debugging picks a new port on every reboot (IP can change too): take the current `IP:PORT` from Settings -> Developer options -> Wireless debugging and pass `--connect IP:PORT`; never reuse a remembered port.
- Every other dev.py phone command takes `--serial` and resolves it the same way.

At the time of writing two phones have been used: a Samsung S9 (LineageOS, 1440x2960,
`device:starlte`), DJI app package `au.awto.dji.awto_dji_app`, and a Samsung S20+ (1440x3200,
`device:y2s`), both with DJI Pilot (`dji.pilot`) also installed as a reference - the
app that actually connects to the Phantom 3X.

**Screen resolution is per-phone - never hardcode a pixel coordinate across devices**
(2026-11-01, hit live: the S9-derived dropdown tap in `select-aircraft` landed wrong
on the S20 until re-measured). `scripts/re/dji_pilot_bench.py` resolves every tap it
can from a fresh `uiautomator dump`'s `bounds=` for the target `resource-id`, not a
literal pixel pair; `DROPDOWN_TAP` is the one remaining hardcoded exception (S9-only,
no stable resource-id found yet for that dropdown trigger). If driving a third phone,
re-measure `DROPDOWN_TAP` or scale it by `target_width/1440, target_height/2960` as a
starting guess, then verify against a dump rather than trusting the scaled number.

**A single `adb shell input tap`/`input text` is not reliable even at the right
coordinates** - observed on the S20 login form: a tap can land before the
keyboard/IME has focus-settled on the intended field, so a `KEYCODE_DEL` flood or
`input text` meant for one `EditText` partially lands in another, silently
truncating or corrupting both. Verify `focused="true"` on the target node before
editing (retry the tap if not focused yet), and after typing, re-dump and compare
text until it reads identical twice in a row before trusting it - one dump
immediately after the edit can catch mid-IME-commit state. `ensure_focus`/
`stable_field_text`/`set_field` in `dji_pilot_bench.py` are this pattern,
factored out for reuse; don't re-invent a single blind tap+type.

### DJI account login

DJI Pilot requires a DJI account sign-in (no guest/skip option found on this build,
3.1.83) before it will show the aircraft picker. Credentials are
`~/.config/awto/secrets.yaml` `dji:` (url/purpose/username/password) - stated purpose
is exactly this sign-in; never print/log the values, only lengths or match booleans.
Run `./dev.py dji-pilot login` (wraps `cmd_login` in `dji_pilot_bench.py`, uses the
focus/poll pattern above) rather than typing it by hand.

**If login fails with `EHOSTUNREACH` in `dji.pilot`'s logcat** (`adb logcat -d
--pid=$(adb shell pidof dji.pilot)`), that is very likely **not** a bad credential or
a dead DJI server - check for a stale global HTTP proxy on the phone first:
`adb shell settings get global http_proxy`. Hit live 2026-11-01: a leftover
`<host>:8080` global proxy (unrelated to this project, already present before this
session touched the phone) pointed at a host nothing answered on, breaking every
app's connectivity including Pilot's login *and* the phone's own "connected to
Wi-Fi, no internet" state - Wi-Fi association was fine throughout. Clear it with
`adb shell settings put global http_proxy :0` (Android's documented way to unset a
global proxy) and re-check `ping www.google.com` from the phone before retrying
login.

### Driving DJI Pilot as a reference app

Use `./dev.py dji-pilot select-aircraft|connect|screenshot`; the raw adb below only explains what it does.

No intent exists to pick the aircraft model directly (internal app state, no exported
extras for it) - this is the fastest known manual recipe, via `adb shell input tap`/
`uiautomator dump`, not a shortcut:

```
adb -s <id> shell am force-stop dji.pilot
adb -s <id> shell am start -n dji.pilot/.main.activity.DJILauncherActivity
adb -s <id> shell input tap 719 382          # opens the aircraft-type dropdown
```

The dropdown opens scrolled to whatever family was last selected (often Inspire, not
Phantom) - it does NOT remember the last selection across a force-stop+relaunch, so
expect to redo this every time. Scroll the list to reach the Phantom 3 entries, then
find and tap the exact row (coordinates shift with scroll position, don't hardcode
them):

```
adb -s <id> shell input swipe 720 500 720 200 300     # scroll the open dropdown list
adb -s <id> shell uiautomator dump /sdcard/ui.xml
adb -s <id> shell cat /sdcard/ui.xml | tr '>' '>\n' | grep -B1 'text="PROFESSIONAL"' | grep -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"'
# tap the center of the row's bounds (parent item_content_ly, not just the PROFESSIONAL text node)
```

**Known unreliable:** that `input swipe` on the dropdown list does not consistently
scroll it - it worked once (2026-10-26, operator did it manually on-device), and
repeated attempts at the same coordinates/parameters via `adb shell input swipe`
afterward did nothing (dump kept showing the same 3 Inspire rows). Not yet root-caused
(possibly needs a real multi-touch fling gesture with specific velocity that `input
swipe`'s single linear interpolation doesn't produce, or the list may not be a plain
scrollable `ListView` despite `uiautomator`'s class name for it). If automating this,
don't assume one `input swipe` call is sufficient - verify via a fresh `uiautomator
dump` that the visible rows actually changed before proceeding, and be ready to fall
back to asking the operator to swipe manually on-device.

Also tried, none scrolled the list (U, from a 2026-10-26 session, not re-run): four `adb
shell input touchscreen swipe` coordinate/duration variants, and raw `sendevent` multi-touch
sequences against `/dev/input/event0` in four profiles (slow drag, fast fling,
dwell-then-drag, full `BTN_TOOL_FINGER` protocol); each left the dropdown unchanged or
dismissed it. `uiautomator` reports `scrollable="false"` on the list. A look through
`/data/data/dji.pilot/shared_prefs/*.xml` for a stored last-selected aircraft (to skip the
UI) found no obvious key; one ~260-line file was not in the expected `name="..."` format
and was not explored. `scripts/re/dji_pilot_bench.py select-aircraft` falls back to a clear
error asking for a manual swipe.

Then tap the big "Camera" button (`dji.pilot:id/v2_phantom_start_connect_btn`) to actually
start the connect attempt - it looks like a camera-roll shortcut but it's the real connect
trigger on this screen.

Reference screenshots (Samsung S9, **1440x2960** - scale all coordinates above by
`target_width/1440`, `target_height/2960` on a different phone):
`docs/img/dji-pilot/aircraft-dropdown-phantom3-1440x2960.png` (dropdown open, Phantom 3 Professional
visible), `docs/img/dji-pilot/phantom3-professional-selected-1440x2960.png` (selected, dropdown
closed, "Camera"/connect button visible at the bottom).

`dji.pilot/.main.activity.DJIAoaActivity` is the activity registered for
`android.hardware.usb.action.USB_ACCESSORY_ATTACHED` - that's what actually opens the
accessory once a model is selected; the launcher activity above is just the picker UI.

## Building and installing

- **U.** `./dev.py load --dji` builds the DJI app (`flutter build apk --debug`, `AWTO_BENCH` stripped from the environment) and `adb install -r`s it; `--bench` / `--both` for the bench app; `--no-build` reinstalls the APKs kept in `tmp/apk/`. Build output: `tmp/logs/build-<name>.log`; no output for 120 s = hung, killed.
- `./dev.py unload --dji|--bench|--old-bench` uninstalls.
- Tests/analyze stay `./dev.py test` / `./dev.py lint`.

## Driving the app: intents, not a UI form

There is **no on-screen connect form** - `ConnectScreen` was removed. The app is
driven entirely by Android intents, handled in `MainActivity.kt` ->
`LinkHost.handle()` (`lib/link/link_host.dart`). A plain launch, or the RC's USB
accessory attaching, auto-connects with the default relay.

- `./dev.py phone connect [--relay HOST:PORT]` (`phone_bench.py`) force-stops the app and sends CONNECT with the extras below. What it does on the phone: `am force-stop`, then `am start -n au.awto.dji.awto_dji_app/.MainActivity -a au.awto.dji.action.CONNECT --es relay <host:port>`; intents to a running instance silently no-op, hence the stop.

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

- **DJI Pilot login `EHOSTUNREACH` -> check the phone's global HTTP proxy, not
  creds/DJI servers first.** See "DJI account login" above.
- **Never hardcode a UI tap coordinate across phones** - resolve from a fresh
  `uiautomator dump`'s `bounds=`. See "Screen resolution is per-phone" above.
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

## Answering the USB accessory dialog without touching the phone

- **V.** The dialog ("Allow AWTO DJI to access ...?") blocks a non-interactive CONNECT; the shim now fails in 3 s and a repeat CONNECT after the grant connects at once (`docs/aoa-live-test-2026-10-26.md`).
- **I.** `./dev.py grant [--serial S]` (`phone_usb_dialog.accept`) dumps the UI, ticks "Use by default for this USB accessory", taps OK from `bounds=`; exit 0 granted, 1 no dialog, 2 controls not found. Parser tested on canned XML only.
- **I.** The "default" tick makes Android launch the app on `USB_ACCESSORY_ATTACHED` with the grant; it survives reboot, not uninstall or clear-data.
- **U.** Persists per manufacturer+model on Android 12 (Pixel 3 XL): confirm with `dumpsys usb` on the phone after the first grant. Control ids (`android:id/alwaysUse`, `button1`) are unverified on a phone.

## Emulating the RC from a PC or a Cynthion

- **I.** `./dev.py rc [--serial S] [handshake|listen|replay FILE] --vid H --pid H [--seconds N] [--accept-dialog]` (front for `scripts/re/t600_rc_emulator.py`) plays the RC (AOA accessory host, manufacturer/model parsed from `aoa_identity.dart`) toward the phone: `handshake`, `listen`, `replay FILE`; log `tmp/logs/t600_rc_emulator.log`.
- **V.** description/version/uri/serial = `DJI` / `v1.2.3.4` / `www.dji.com` / `12345678`, as read off the phone with a real RC (`docs/aoa-live-test-2026-10-23.md`).
- **I.** Replay sends only DUML frames with receiver 0x02 (the app) and never an app-sent frame; it forwards recorded frames and builds none, so no flight-control path. Covered by `test_t600_rc_emulator.py` (fake backend).
- **U.** Nothing here has run on hardware: PyUSB switch, bulk endpoints, re-enumeration (limit 5 s), `--accept-dialog` timing. `CynthionBackend` is a stub awaiting `usb <port> aoa|tx|rx` shell verbs.

## AOA bench app

Generic AOA test rig, not DJI-specific: a Cynthion (RISC-V shell) or `t600_rc_emulator.py` plays the AOA host, this app is the AOA **device**, a script on the PC drives it over WiFi.

### Build / install / run
- **U.** `./dev.py up [--serial S] [--connect IP:PORT] [--no-build]`: phone -> `load --bench` -> listener in the background -> `connect` -> listener in the foreground (^C stops it). Replaces every manual step below; not yet run end to end.
- Steps, each also a command (all take `--serial`):
  - `phone-connect`: find the phone.
  - `load [--bench]`: `AWTO_BENCH=1 flutter build apk --debug --dart-define=BENCH=true`, `adb install -r`, then checks the package is on the phone.
  - `listen [--port 9910]`: `scripts/re/bench_host.py --listen 9910 --tail` in the foreground; refuses and shows the holder if the port is in use (9910 is unused elsewhere; relay uses 9900/9901).
  - `connect [--host H] [--port 9910] [--pkg bench|dji]`: host defaults to the local address `ip route get <phone-ip>` reports; waits 10 s for the listener's first `STATE` line (read from `tmp/logs/bench_host.log`), else prints the logcat tail.
  - `grant`: answers the accessory dialog. `suite NAME...`: see the test catalog. `rc ...`: the RC emulator.
- **V.** `AWTO_BENCH=1` gives the bench package id `au.awto.aoabench` and launcher label "AOA Bench" (namespace and classes stay `au.awto.dji.awto_dji_app`): it installs **next to** the DJI app (`au.awto.dji.awto_dji_app`). Both declare the `DJI`/`T600` accessory filter, so a real attach shows Android's app chooser while both are installed. `lib/main.dart` switches on `const bool.fromEnvironment('BENCH')`.
- **I.** `connect` runs `am force-stop au.awto.aoabench`, then `am start -n au.awto.aoabench/au.awto.dji.awto_dji_app.MainActivity -a au.awto.dji.action.BENCH --es host <pc-ip> --ei port 9910` (command construction unit-tested; the stop is needed because an intent to a running app is a no-op).
- **V.** The bench app under the earlier id `au.awto.dji.awto_dji_app.aoabench` was installed and run on a Pixel 3 XL (Android 12) over wireless adb: connects to the host script, state lines flow. **U.** The same under `au.awto.aoabench`; everything involving a USB accessory attach.
- **U.** That superseded build is still on the test phone: `./dev.py unload --old-bench`.
- `au.awto.dji.action.CONNECT` accepts the same `host`/`port` extras; `DISCONNECT` stops the accessory pump. Relaunch by `USB_ACCESSORY_ATTACHED` after process death has no host (not persisted): re-run `connect`. **U.**
- Log also in the phone's external files dir: `bench.log`.

### Screen
- Top half, 2 Hz: PORT (`idle|attached|permission|connected|streaming|failed` + last error), USB (attached, permission, manufacturer/model/description/version/uri/serial), POWER (BatteryManager: plugged usb/ac/wireless/none, status, mV, uA), SPEED, MSGS (1 s and 10 s rates, totals, seconds since last, CRC-bad, discarded bytes), MODE (test verdict), HOST (TCP link + RTT).
- Bottom half: timestamped log, newest last, auto-follow, 2000-line ring, mirrored to the file and the host.
- SPEED: Android exposes no USB speed or endpoint info for accessories. Label is **inferred** from bulk max packet (512 high, 64 full, 1024 super); the app currently has no max packet source so it shows `unknown`, plus `/sys/class/udc/*/current_speed` when readable and the largest single read (`chunk`). **U** (all three).
- PORT `streaming` = envelope/chunk within the last 2 s.

### JSON protocol (one object per line, app is the TCP client)
| Dir | Message | Meaning |
|---|---|---|
| app>host | `{"t":"hello","app","build"}` | on connect (log ring replayed after) |
| app>host | `{"t":"state", usb, power, speed, msgs, port, host, mode, echo}` | every 500 ms and at once on a discrete change |
| app>host | `{"t":"log","ts","lvl","msg"}` | each log line |
| app>host | `{"t":"rx","ch","len","crc_ok"}` | each decoded AOA envelope (passive/duml modes); DUML CRCs checked on ch 0x5749 |
| app>host | `{"t":"result","test","mode","frames","bytes","pass","first_mismatch":{"seq","offset","got","expected","hint"},...}` | test verdict; `final:true` when a run ends |
| app>host | `{"t":"pong","id"}` / `{"t":"ping","id"}` | answer to host ping / app-initiated RTT probe (host answers `{"cmd":"pong","id"}`; added beyond the brief so the grid shows RTT) |
| host>app | `{"cmd":"ping","id"}` | app answers `pong` |
| host>app | `{"cmd":"send","hex"}` | raw bytes on bulk-out, one write |
| host>app | `{"cmd":"echo","on"}` | passive-mode echo of each decoded payload (not the envelope) |
| host>app | `{"cmd":"mode","m":"passive\|echo\|sink\|source\|duml", ...params}` | see modes |
| host>app | `{"cmd":"result"}` | emit a `result` now, test continues |
| host>app | `{"cmd":"stats_reset"}` / `disconnect` / `reconnect` | reset counters / stop pump and auto-connect / drop and reconnect now |

Bounds: host TCP connect 3 s (LAN <= 1 s, 3x); host reconnect backoff 1,2,4,8 s then 8 s (cap bounds how long a freshly started script waits); accessory retry backoff 1..8 s likewise; AoaShim permission wait 3 s; source `dur_ms` default 10 s. Each is commented where it is set.

### Modes (`{"cmd":"mode","m":...}`)
| Mode | Params | Behaviour |
|---|---|---|
| `passive` | none | default: decode envelopes via `AoaMux`, count, `rx` messages |
| `echo` | none | write every raw read back unchanged (empty read -> empty write) |
| `sink` | `test`, `expect` (auto-finish after N frames) | parse AOAT stream, verify, report first mismatch offset; counts headerless `<24 B` transfers as `short`, empty reads as `zlp` |
| `source` | `test`,`size`,`count` (0=until `dur_ms`),`rate` (fps, 0=max),`gap_ms`,`idle_ms`,`dur_ms`,`pattern` (addr\|counter\|random\|zeros\|ones\|alt),`seed` | generate AOAT frames app>host; `size` 0 = empty write, `<24` = headerless address-pattern bytes |
| `duml` | `act` (`answer` default\|`emit`), `sender`,`receiver`,`cmd_set`,`cmd_id`,`seq0`,`payload_len`,`seed`,`count`,`rate`,`bad` (none\|hdr\|crc\|mix) | answer valid DUML requests with swapped addresses, or emit enveloped DUML test frames with a fake address-pattern payload and chosen addresses / bad CRC |

### AOAT test frame (shared: `scripts/re/aoa_testkit.py`, `lib/bench/aoat.dart`, vectors `scripts/re/aoat_vectors.json`)
- Little endian: `'AOAT'`, test_id u16, pattern u8, flags u8, run_seed u32, seq u32, total_len u32, payload, crc32 (zlib) over all before it. Min 24 B; accepted max 8 MiB.
- Patterns: `addr` (every 32-bit word = byte offset XOR mix(seed,seq,test): a wrong word names the offset it was generated for), `counter`, `random` (xorshift32), `zeros`/`ones`/`alt` (0xAA,0x55; bit-stuffing/NRZI stress).
- A corrupt frame still localises: payload is compared to the regenerated one, first differing offset + hint reported even when the CRC also fails.
- **V.** Python and Dart produce byte-identical frames for the golden vectors (both test suites).

### Test catalog (`./dev.py suite NAME...`, i.e. `scripts/re/bench_host.py --suite <name>`; the suite owns the port, so no `listen` running; peer = the other end of the cable)
| Suite | Cases | Bounds |
|---|---|---|
| `size_sweep` | 0,1,2,3,7,8,15,16,31,32,63,64,65,127,128,255,256,511,512,513,1023,1024,1025,4095,4096,16383,16384,65535,65536 B, both directions | wait = 1 s + bytes / 100 kB/s (slowest plausible full-speed rate, 10x under ceiling) |
| `zero_length` | frame-level empty payload (24 B frame); USB-level: exact multiples of the peer's max packet (64 or 512) sent with and without a trailing ZLP, both directions; reported as `ZLP:` cases | same |
| `throughput` | 64, 512, 4096, 16384, 65536 B per direction, bytes/s over a 2 s window (>10 state ticks, skips ramp-up, 20 windows = 40 s) | window + 1 s |
| `limits` | largest accepted transfer (128 KiB doubling to 4 MiB), 10000 x 24 B back-to-back, 5 s idle then 200 x 512 B burst (5 s = 2.5x Android's 2 s USB autosuspend) | per size |
| `fuzz` | `suite fuzz --fuzz-seed N` (logged; omitted = random, printed): random sizes/patterns/gaps, truncated and oversized frames, DUML with bad CRC, ZLPs; oracle = `aoa_testkit.SinkModel` over the same chunks | bytes-based |
| `soak` | `suite soak --soak-minutes N` stream from seq 0xFFFFFF00 (u32 wrap in first 256 frames), 10 s windows, drift = max deviation from median < 50% | N min |

- API: `BenchHost.start()`, `wait_for_state(pred, timeout)`, `wait_for_result(...)`, `send_cmd(dict)`, `latest_state()`, `log_lines()`, `ping()`; `Peer` interface (`tx`, `rx`, `max_packet`) is implemented by `EmulatorPeer` (over `t600_rc_emulator.Backend`) or a Cynthion shell driver. CLI `--peer none` runs app-only steps and fails peer steps.
- **V.** pytest: `scripts/re/test_aoa_testkit.py`, `scripts/re/test_bench_host.py` (fake in-process app + loop peer); `flutter test` covers model, AOAT codec, mode engine, controller over loopback TCP.
- **I.** Fuzz oracle matches the Dart sink only as far as the two implementations agree on edge cases (headerless chunk rule, resync); only checked Python-vs-fake-app.
- **U.** Everything on hardware: `BenchShim.kt` (accessory info, battery, udc speed, log dir); `FileOutputStream.write` of 0 bytes emitting a ZLP; `FileInputStream.read` surfacing a ZLP as a 0-length read; transfers >= 64 KiB through the accessory driver; read coalescing vs the sink's chunk rule; WiFi half-open detection (no heartbeat from the app side beyond RTT probe); bench screen layout on a phone; `EmulatorPeer`/Cynthion driver against real USB.

## What this doesn't cover

- The aircraft's **front micro-USB port** (`/dev/ttyACM11` on the PC, not through the
  phone at all) - that's `docs/fc-usb-duml.md` + `scripts/re/duml_probe.py` /
  `duml_watch.py`, a separate, PC-direct surface.
- Camera SD-card / Ambarella Linux access - `docs/camera-linux-console-access.md`.
