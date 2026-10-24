# PC video decoding and capture replay

2026-10-24. The PC demultiplexer and FFmpeg decoding path have been implemented
and tested. **The saved aircraft recording still cannot produce a picture:** it
contains no SPS/PPS parameter sets or IDR keyframe. No live hardware test was run;
the operator requested saved captures only.

## Correct AOA framing

The raw accessory stream has an **8-byte envelope**:

| Offset | Field |
|---|---|
| 0–1 | Magic `55 cc` |
| 2–3 | Channel/type, little-endian u16 |
| 4–7 | Payload length, little-endian u32 |
| 8 onward | Exactly that many payload bytes |

Channel `0x5749` (22345) carries commands/DUML; `0x574a` (22346) carries camera
video; `0x574b` (22347) is an alternate FPV video channel in the APK. The APK parser
accepts types 22345 through 22349. These are distinct from the nested Lightbridge
channel parser's own format.

Evidence: captured bytes begin `55 cc 4a 57 00 08 00 00`, followed by a 2048-byte
video payload. Dynamically unpacked APK `dji/midware/usb/P3/UsbAccessoryService.java`
registers magic `55 cc` and a further six header bytes; `usb/P3/b.java` reads the
channel and length and routes 22345 to the command parser and 22346 to camera video.
Only format facts were used for the independent implementation.

**Correction to `aoa-live-test-2026-10-23.md`:** the claim that no demux header
exists was wrong. Scanning raw bytes for H.264 start codes leaves USB envelope
headers and interleaved command traffic inside video NALs. NAL units and start codes
can cross envelope boundaries, so strip envelopes and concatenate only the selected
video channel before parsing/decoding H.264.

## Tools

- `scripts/re/aoa_mux.py`: incremental envelope parser, preserving arbitrary split
  headers/payloads, bounding accepted lengths and recording discarded bytes.
- `scripts/re/pc_video.py`: saved relay-log/raw-AOA extraction, NAL inventory,
  FFmpeg frame-count validation and optional `ffplay` preview. It ignores TX log
  entries and discards incomplete envelopes between logged connections.
- `scripts/re/aoa_relay_server.py`: now uses the same envelope parser for commands
  and video. `--video-out PATH` writes camera-channel payloads only for future
  captures; this option was not used against live hardware in this pass.

Extract and check the existing recording:

```sh
python3 -I scripts/re/pc_video.py captures/sessions/2026-10-23/aoa_relay_server.log --output tmp/camera-video.h264 --check --report tmp/camera-video-report.json
```

The command returns **2** when FFmpeg decodes zero frames. The retained result is
[data/pc-video-capture-analysis-2026-10-24.json](data/pc-video-capture-analysis-2026-10-24.json).
It reports 211 camera envelopes, 405,568 extracted video bytes, NAL types 1 and 9,
and no SPS/PPS/IDR. FFmpeg reports `non-existing PPS ... referenced`. The duplicate
stdout capture contains the same received bytes and produces the same result.
The recording requires resynchronization (76,095 discarded bytes); completeness
of the archive must not be assumed.

For a **complete** saved capture, add `--preview` to open a PC player. The tool
refuses to launch preview when SPS/PPS/IDR are absent, instead of opening a black
window. FFmpeg/ffprobe/ffplay must be installed. For binary raw AOA input rather
than a text relay log, pass `--format raw`.

Future capture, when live testing is requested:

```sh
python3 -I scripts/re/aoa_relay_server.py --port 9900 --video-out tmp/live-camera.h264
```

Listen before the phone connects and preserve the stream startup. Confirm the
recording includes SPS/PPS and a keyframe before claiming a usable preview.
The phone remains the previously established AOA-to-TCP bridge; direct PC USB
video access through alternate controller modes is a separate unverified path.

## Validation

`python3 -I scripts/re/test_aoa_mux.py`: six passing regression tests covering
all chunk sizes for envelope splitting, embedded magic inside payloads, noise and
oversized lengths, bounded buffering, channel isolation, cross-envelope DUML,
and connection boundaries/TX exclusion in replay.

A generated 12-frame 320×180 H.264 stream was split into 257-byte AOA video
payloads and interleaved with command envelopes containing deliberately misleading
H.264-like bytes. The PC tool recovered **byte-identical H.264**, and ffprobe
decoded **12 frames at 320×180 with no diagnostics**. This verifies the software
path with complete data; it is not a claim of an aircraft picture or a GUI test.

## Android channel routing and remaining limitation

The issue #23 MVP now removes AOA envelopes on the phone: telemetry and SIMPLE
mode selection see only command payloads, and the Annex-B extractor sees only
camera payloads. Three- and four-byte NAL prefixes and reconnect resets are tested.
The relay carries versioned channel-tagged records, with video forwarding on by
default; `--es relayVideo false` suppresses camera/FPV forwarding while retaining
commands, unknown channels and discarded-byte diagnostics. See the
[operator guide](phone-bridge-operator-guide.md) for the wire format and compatibility.

`VideoShim` still returns from an input-buffer callback when there is
no pending NAL without retaining that available buffer index; later NAL arrivals
do not trigger draining those available buffers. This still needs repair before
calling Android playback verified. The native shim was not changed in this pass.
The older document's claim that the whole chain was verified correct is
superseded by these findings.
