# AOA capture regression check: `awto_dji_app` vs the RC's USB-A port (2026-10-26)

Status tags: **V** verified here, **I** inferred, **U** unknown. Repeats the test in
[aoa-live-test-2026-10-23.md](aoa-live-test-2026-10-23.md) (read that + its correction in
[pc-video-preview.md](pc-video-preview.md) first) against the current `main` working tree,
to check whether the capability still works. Hardware: owner's P3 Pro RC, Samsung S9
(SM-G960F, LineageOS) on WiFi ADB (192.168.25.123), connected to the RC's USB-A port via a
plain cable. **Correction (same day, confirmed by the operator live):** the aircraft was
**off** during this test, not powered - the original "bird powered" note here was wrong.
Raw logs from this specific run (`captures/sessions/2026-10-26/`) were deleted later the
same session as superseded/garbage once a physical USB reconnect was found to fix a
separate, much larger transport problem (see `HISTORY.md`) - not available to re-check
against.

## Headline

**V.** USB/AOA capture still works and matches the documented 2026-10-23/24 behaviour once
the link is actually open: real bytes flow continuously, demux correctly into the `55 cc`
envelope format, and DUML frames decode with a high CRC-pass rate.

**V, regression found.** The app no longer gets from "launched" to "connected"
unattended. The 2026-10-23 test launched the app by tapping Android's own "open with this
app" dialog (triggered by the manifest's `USB_ACCESSORY_ATTACHED` filter), which
auto-grants USB accessory permission for that launch. The app has since been refactored to
be intent-driven with no on-screen Connect form (`58fe247 app: intent-driven link, remove
connect screen`, 2026-10-24). Launching it the documented way for this refactor (`adb shell
am start -a au.awto.dji.action.CONNECT --es relay <host>:<port>`) does **not** carry that
auto-grant: the native `AoaShim.connect()` (`android/app/.../AoaShim.kt`) calls
`usb.requestPermission()` and silently awaits a system `UsbPermissionActivity` dialog that
nothing answers in a non-interactive launch. The Dart side (`AoaTransport.connect()`,
`lib/transport/aoa_transport.dart`) sits in `LinkState.connecting` forever - no exception,
no timeout, no log line past `[relay] connected to ...` - which is itself a gap (should at
least time out and surface a "waiting for permission" status). Confirmed via
`adb shell dumpsys window | grep mCurrentFocus` showing
`com.android.systemui/.usb.UsbPermissionActivity` focused, and a screenshot reading
"Allow AWTO DJI to access DJI Inspire 1?". Manually tapping OK (adb `input tap`, matching
this session's standing permission to actuate RC/phone with props off) unblocked it
immediately; a second `CONNECT` intent then connected in well under a second.

- **I.** This previously granted permission was presumably live from the 2026-10-23/24
  session but did not carry over - either because it's scoped to the specific
  `UsbAccessory` object (reissued per USB renegotiation, not per app) or because the app
  was reinstalled (`flutter build apk --debug` + `adb install -r` this session). Not fully
  isolated which.
- **What this means for reproducing the test:** after an app reinstall or any time the
  phone-RC USB link has been replugged, the first `CONNECT` intent after that needs either
  a physical replug (so Android's own auto-launch-with-grant intent fires) or a manual tap
  on the resulting permission dialog. Scripted/unattended runs will hang silently otherwise.

## Result once connected

- **V.** `dumpsys usb` on the phone: `current_functions=ACCESSORY`,
  `connected=true`, `configured=true`,
  `current_accessory={manufacturer=DJI, model=T600, description=DJI, version=v1.2.3.4,
  uri=www.dji.com, serial=12345678}` - identical to the 2026-10-23 result, still held at
  the end of this session (`captures/sessions/2026-10-26/dumpsys_usb_final.txt`).
- **V, new observation.** The Android system permission dialog names the accessory **"DJI
  Inspire 1"**, not "T600" (screenshot, see session README). `dumpsys usb`'s
  `current_accessory.model` field says `T600`. Both come from the same `UsbAccessory`
  object the RC presents; the permission dialog text is Android's own
  "Allow X to access Y accessory?" using a different accessory field than `dumpsys` prints
  (likely `description` vs `model`, or a device-specific Android build difference) - not
  resolved which field carries "DJI Inspire 1", only that the RC's AOA identity surfaces
  that string somewhere. Worth a closer look if the accessory-identity strings matter
  elsewhere in the repo.
- **V.** `scripts/re/aoa_chunk_decode.py` against the full raw relay log
  (`captures/sessions/2026-10-26/aoa_relay_server.log`, 426,552 decoded bytes from a
  ~9.5-minute capture, well beyond the couple-minute sample originally asked for since the
  connection stayed up): **3113 DUML chunks, 0 video chunks, 5959 CRC-valid DUML frames.**
  Senders: `0x0e` (DM368 sky-end) 5577 frames, `0x10` 379, `0x06` 2, `0x01` (camera) 1; all
  addressed to `0x02` (app) except `0x06->0x0a`. This is a materially larger clean sample
  than the 2026-10-23 test's 116 CRC-valid frames - the `55 cc` demux and DUML CRC
  validation both still work correctly end to end on the current code.
- **U.** Zero video (`0x574a`) chunks appeared in this entire ~9.5-minute capture, versus
  211 video chunks in the 2026-10-23 session. Not established whether this is a camera/FPV
  state difference on the bench (lens cap, standby, no video session triggered) or an app
  change - `relayVideo` still defaults to `true` (`lib/link/link_host.dart`) so the app
  would have forwarded video if its `AoaMux` ever saw a `0x574a` channel. Needs a session
  where video is confirmed actively streaming (e.g. DJI GO app open, or an explicit I-frame
  request) to tell apart.

## App's own view (logcat) partially disagrees with the PC-side decode

- **V.** `adb logcat` (`captures/sessions/2026-10-26/logcat_raw.log`) shows the documented
  debug chokepoints are all still present and firing: `[transport:android-accessory]
  state=...` transitions (`connecting` -> `connected`, and one `disconnected` ->
  `connecting` -> `connected` auto-reconnect cycle), `[link] rx`, `[link] packet
  set=.../id=...`, `[link] bad frame (...)`.
- **V.** Over the live window: 5773 `[link] packet` (good, CRC-valid) lines vs 4007
  `[link] bad frame` lines in-app - a ~41% bad-frame rate as *LinkSession* (the in-app DUML
  framer) sees it. This is higher than the PC-side pass rate implies and worth noting: the
  PC tools (`aoa_chunk_decode.py`, `aoa_relay_server.py`'s `StreamDemuxer`) don't
  independently re-derive this number from the raw USB stream - they decode the phone's
  **already re-encoded** relay records (`AoaMux` packet -> `AoaPacket.encode()` ->
  `RelayRecord`), so a clean PC-side decode mainly confirms the phone's own demux
  round-trips consistently, not that `LinkSession`'s in-app byte stream is clean.
- **U, flagged not resolved.** A recurring minority of `[link] bad frame` dumps contain the
  literal bytes `55 cc 49 57 ...` - i.e. what looks like an **un-stripped AOA envelope
  header for the very next command-channel packet** - sitting inside bytes `LinkSession`
  is treating as pure DUML payload, e.g. (verbatim from `logcat_raw.log`):
  ```
  [link] bad frame (DUML: packet CRC mismatch) 39B 55 27 04 15 0e 02 c8 4d 03 81 7b fa 61 87
  09 89 6a 87 63 fa 3f 87 8c b0 55 cc 49 57 47 00 00 00...
  [link] bad frame (DUML: header CRC mismatch) 4B 55 cc 49 57
  ```
  `AoaMux.add()` (`lib/transport/aoa_mux.dart`) only ever emits `packet.payload` as the
  bytes strictly between `offset+8` and `end` for one envelope, so this shouldn't be
  possible by construction unless either (a) it's coincidental noise inside genuine DUML
  payload content that happens to match the envelope magic + a valid channel ID - possible
  but the exact 4-byte run `55 cc 49 57` (the command channel's own ID) recurring this
  often across the session makes pure coincidence look unlikely, or (b) there is a real
  boundary-tracking bug in `AoaMux` that occasionally leaves the next envelope's header
  attached to the end of the previous packet's payload. **Not root-caused in this pass** -
  flagging as a specific, reproducible-looking anomaly for someone to dig into with
  `app/packages/duml` test fixtures or a byte-level trace, not asserting which explanation
  is correct.

## What this confirms vs. the prior session

| | 2026-10-23/24 | 2026-10-26 |
|---|---|---|
| Genuine AOA handshake (`dumpsys usb`) | V | V, identical accessory identity |
| App reaches `LinkState.connected` unattended | V (on-screen tap once) | **regressed** - needs a permission tap/replug first when launched via intent |
| `55 cc` envelope demux + DUML CRC (PC side) | V, 116 valid frames | V, 5959 valid frames (longer sample) |
| Video channel present | V, 211 chunks | not seen this session (U, cause not established) |
| `[link]`/`[transport]` debug chokepoints present | V | V |
| In-app (`LinkSession`) frame quality vs PC-side decode | not directly compared | **new finding** - in-app bad-frame rate (~41%) higher than PC-side numbers suggest; possible envelope-header leak, not resolved |

## What's needed next

1. Decide whether the permission-flow gap (no auto-grant, no timeout/error surfaced) is
   worth fixing before this intent-driven flow is relied on for further unattended/scripted
   testing - currently any fresh permission state hangs silently.
2. Chase the `55 cc` leak into `LinkSession`'s byte stream: reproduce with a unit test
   feeding `AoaMux` two back-to-back command-channel envelopes and checking the emitted
   payloads never contain the next envelope's magic bytes.
3. Re-run with video actively streaming (DJI GO app open, or send the existing I-frame
   request) to check whether the 0-video-chunks result here was a bench-state artifact or a
   real change.
