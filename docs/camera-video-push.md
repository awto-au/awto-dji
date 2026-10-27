# Phantom 3 Professional camera recording settings over DUML

Investigation for [#66](https://github.com/awto-au/awto-dji/issues/66), 26 October
2026, based on main `5cd5aa449a0895280ea2fbf5ec403ea5be7f377b`.

**Result:** use the already-arriving **CAMERA/0x81 GetPushShotParams**, qualified
by **CAMERA/0x80 GetPushStateInfo** camera identity. No new queries are needed.
The saved capture contains one configured setting: **4096 × 2160, nominal 24 fps,
primary H.264, MP4** under classic GO's getters. This is a capture-backed static
interpretation, not an independently observed screen/recorded-file comparison.

V = verified in the named static artifact or captured bytes; I = inference;
U = unresolved. A static enum is not proof that every camera supports its values.

## Evidence and provenance

The correct consumer app is classic **DJI GO, package `dji.pilot`**, not GO 4 or
an enterprise-app inference from that package name. Reuse the identity/signature
audit in [PR #44](https://github.com/awto-au/awto-dji/pull/44) and its
[3.1.8 manifest](https://github.com/awto-au/awto-dji/blob/audit/dji-go-p3-provenance/docs/data/dji-go-3.1.8-provenance.json).
That audit pins GO 3.1.8 / 31018968, contemporaneous with P3 Pro firmware 1.11.20,
to APK SHA-256 `f7a4eaaf0adf6bee86d1cd50c4a221824b17e97132807f0f4172f9b68b9f1965`.

For this investigation the retained APK itself is incomplete and cannot be
reverified. **All four retained extracted DEX files were freshly SHA-256 checked
and exactly match that manifest.** The two push classes were also freshly
decompiled from those DEX files with jadx 1.5.3. This preserves a byte-pinned
implementation source without claiming a new APK signature verification. No
vendor bytecode or decompiled source is committed. The packed 3.1.83 extraction
does not supply readable DJI bodies here; no cross-version layout identity is
asserted.

Relevant DEX hashes:

| DEX | SHA-256 |
|---|---|
| classes.dex | `deb78b2ec83986e54fed1aca696167b983a6068c05b6fb2bd8ae68b89a6d1c16` |
| classes2.dex | `9a5080fb6e4f9796cb8a54065bd5ae59d5304ea8787f1708aa06e67f560d6cc3` |
| classes3.dex | `3577f6005816827a1b15cea424bfcc1ba9c03888236f38a5e1fb89d65ce38819` |
| classes4.dex | `845e3a4310401584b6d301d5ac2fde7ed4370d1e015e63096f2a3aa120cc246c` |

Paths below are relative to `tmp/apk/go_3.1.8/static/sources/dji/` in the audit
checkout. Method names are preferred over line numbers because a DEX-only
decompilation changes imports/formatting:

- `midware/data/config/P3/q.java`, CAMERA enum: 128/129/130/131 register the
  StateInfo/ShotParams/PlayBackParams/ChartInfo models (original lines 476-479).
- `midware/data/model/P3/DataCameraGetPushShotParams.java`, named getters in the
  field table below; `DataCameraSetVideoEncode.VideoEncodeType` defines 0/1.
- `pilot/fpv/camera/more/a.java`, `W()/X()/Y()`, `r(int)`, `c(int,int)` and
  `d(int,int)`: actual camera-type/protocol-specific resolution and FPS UI choices.
- `pilot/fpv/camera/more/d.java`, `Q_`, `R_`, `S_`: shared resolution/FPS resources.
- `pilot/set/view/VideoResolutionSetterView.java`: parallel resolution/FPS arrays,
  visible PAL/NTSC text, selection by the push's getters and update subscription.
- `pilot/set/view/VideoFormatSetterView.java`: container getter, MOV/MP4 button
  order. Also `common/camera/DJICameraSettingsDef.CameraVideoFileFormat` = MOV(0), MP4(1).
- `pilot/fpv/camera/newfn/DJICameraFnVideoView.java`, ShotParams event handler:
  the camera video-settings UI consumes the **primary** encoding getter.
- `sdksharedlib/hardware/abstractions/c/b.java`, ShotParams event handler: the
  same resolution/FPS/container getters feed camera recording settings.

## Captured wire evidence

Source: [2026-10-23 raw relay log](../captures/sessions/2026-10-23/aoa_relay_server.log),
SHA-256 `6d8e730945a3e79820196ec272c103ca17d2040624441a8eab59eed3f3c57b92`.
The audit accepts complete AOA envelopes, selects **0x5749 command traffic**,
checks header CRC8 and frame CRC16, then decodes SIMPLE protection mode 3.
The historical `aoa_relay_frames.log` was produced before correct SIMPLE decoding;
its apparent command IDs are not the authoritative interpretation here.

There are 11 complete command envelopes and 211 video envelopes, with 116
CRC-valid command frames. 76,095 bytes are discarded while synchronising the
saved stream; these counts describe the recoverable capture, not all live traffic.

| Push | Count | Payload bytes | Distinct payloads | Finding |
|---|---:|---:|---:|---|
| 02/80 | 7 | 37 | 1 | connected=1, camera type=4 FC300X, protocol version=2 |
| 02/81 | 3 | 72 | 1 | resolution=22, FPS=1, container=1, standard=0, encode byte=0 |
| 02/82 | 0 | - | - | No playback push recovered from this capture |
| 02/83 | 1 | 64 | 1 | Histogram bins, not video settings |

Exact protected example frames, decoded payloads and counts are committed in
[the regression fixture](../app/packages/duml/test/fixtures/captured_camera_pushes.json).
Regenerate it independently from the raw log:

```sh
python3 scripts/re/camera_push_audit.py captures/sessions/2026-10-23/aoa_relay_server.log
python3 -m unittest discover -s scripts/re -p test_camera_push_audit.py
```

Other tracked logs were inspected. Android `[link] rx` and packet log lines are
truncated, so they cannot establish the trailing fields or a second complete
setting. The older PC/CDC logs do not add a verified setting transition. No
October 26 raw recording-setting capture is committed on this base.

## Payload offsets and enumerations

Offsets are **zero-based in the decoded push payload**, excluding the 11-byte
DUML header and trailing CRC. Pushes have no leading ACK result byte.

| Message / field | Offset | Width | Classic GO getter / interpretation | Evidence |
|---|---:|---:|---|---|
| 81 recording resolution | 13 | u8 | `getVideoFormat()` | V static + raw 22 observed |
| 81 recording rate code | 14 | u8 | `getVideoFps()` | V static + raw 1 observed |
| 81 FOV | 15 | u8 | `getVideoFov()`; not width/height | V static; not displayed |
| 81 second stream flags/ratio | 16/17 | u8 each | `getVideoSecondOpen()/Ratio()` | V static; not preview negotiation |
| 81 quality | 18 | u8 | `getVideoQuality()`; not codec/container | V static; not displayed |
| 81 container | 19 | u8 | `getVideoStoreFormat()`: 0 MOV, 1 MP4 | V static + raw 1 observed |
| 81 video standard | 55 | u8 | `getVideoStandard()`: 0 PAL, 1 NTSC in UI | V static + raw 0 observed |
| 81 primary encoding | 69 bits 0-3 | nibble | `getPrimaryVideoEncodeType()`: 0 H.264, 1 H.265 | V static + raw 0 observed |
| 81 secondary encoding | 69 bits 4-7 | nibble | `getSecondaryVideoEncodeType()`, same enum | V static + raw 0 observed; stream role U |
| 80 camera connected | 0 bit 0 | bit | `getConnectState()` | V static + raw 1 observed |
| 80 camera type | 33 | u8 | `getCameraType()`: 4 FC300X | V static + raw 4 observed |
| 80 protocol version | 36 | u8 | `getVerstion()` (vendor spelling); not firmware version | V static + raw 2 observed |

P3 recording resolution codes traced through the FC300X UI:

| Code | Size |
|---:|---|
| 4 | 1280 × 720 |
| 10 | 1920 × 1080 |
| 16 | 3840 × 2160 |
| 22 | 4096 × 2160 |
| 24 | 2704 × 1520 |

P3 nominal FPS codes: **1=24, 2=25, 3=30, 4=48, 5=50, 6=60**.
These are **not public SDK enum ordinals** (that enum begins 24fps at zero).
The shared UI additionally labels 7=120 and 11=96; those are deliberately not
mapped as P3 recording capabilities in this decoder. Exact fractional timing
(e.g. 24000/1001) cannot be established from these labels alone.

Model differences are substantive: FC300X (4) and FC300XW (10) expose the 2.7K
choice only when StateInfo protocol >=2; FC300S (3) has no 4K and exposes 2.7K
only from protocol 2. FC260 (2) has another capability set. FC220's 2.7K uses
size code 31 (2720 × 1530), not P3's 24. PAL/NTSC choices and high-rate modes vary
by model and resolution; the enum table is not a Cartesian product of supported
settings. H.265 is in shared app code, **not evidence of P3 H.265 capability**.
The application therefore enables this interpretation only for observed FC300X.

`GetPushStateInfo` has status, mode, storage and identity, not recording dimensions
or FPS. `GetPushPlayBackParams` has selected-file/playback metadata (including photo
width/height at 21/25); it must not override configured recording settings.
`GetPushChartInfo` exposes up to 64 luminance histogram bins.

## Implementation and remaining check

The canonical schema generates raw prefix decoders for Python and Dart. The Dart
wrapper validates source camera/index, app destination, request/push direction and
no-ACK semantics, and preserves unknown enums. A 20-byte ShotParams prefix is
enough for resolution/rate/container; standard requires 56 and encoding requires
70 bytes. Missing encoding is **unavailable**, never an implicit H.264 default
(the vendor enum lookup itself defaults to H.264 on unknown values; ours does not).

LinkSession accepts either push order, requires fresh identity and shot pushes,
clears settings on link loss/reconnect/camera disconnect or model change, and
expires the label after three seconds without either push. The small label timer
also expires it during total transport silence. Unknown models are withheld.
The video page labels this **Camera recording settings (DUML)**. It sends no new
commands and does not change MediaCodec, preview format, decoder counters or the
separate [lifecycle fix PR #68](https://github.com/awto-au/awto-dji/pull/68).

**Smallest useful physical follow-up:** save complete 0x5749 AOA traffic for a few
seconds at each of two known classic-GO settings, with a screen image of each:
current 4096×2160/24/MP4, then e.g. 1920×1080/50/MOV in PAL. Record a short local
clip at each setting. Compare the corresponding 81 payloads (13/14/19) and 80
identity, then run `ffprobe -show_streams` on the clips to check width, height,
codec, container and exact rational FPS. Codec byte 69 should remain H.264; a P3
H.265 switch is not requested or assumed. Return to the original setting after
the comparison. No flight or new speculative DUML query is needed.

Still U: exact rational FPS, independent screen/file confirmation, other firmware
variants, actual secondary-stream role and behaviour of short/unknown push
extensions. The saved single-setting evidence is sufficient for this bounded
implementation, not a claim of a completed live validation or reason to close #66.
