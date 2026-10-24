# awto-dji app (Phantom 3 Professional, direct — no DJI SDK)

Goal: a Flutter app on an Android phone that drives the Phantom 3 Professional
**directly**, speaking the aircraft's own DUML protocol over the remote
controller's USB link, without the DJI Mobile SDK.

This is interoperability work for an aircraft the operator owns. It does not defeat
any DJI protection. The operator remains responsible for airspace rules, geofencing
and safe flight.

## How the phone connects to the bird (established)

Confirmed from the DJI app manifest (`manufacturer="DJI" model="T600"`, the
Phantom 3 / Inspire 1 generation):

- The link is **Android Open Accessory (AOA)**: the **controller is the USB host**,
  the **phone is the accessory**. Not USB-serial — the `usb_serial` plugins do not apply.
- The accessory file descriptor carries AOA envelopes (`55 cc`, channel u16 LE,
  payload length u32 LE). The phone routes command payloads from `0x5749` to DUML
  and camera payloads from `0x574a` to H.264 extraction.
- **DUML** frames use SOF `0x55`, header CRC-8 and body CRC-16.

## Layers

```
 awto_dji_app/lib/ui         Material 3: Connect, Telemetry, Packet log, About
   │
 lib/safety                  SafetyGate wraps packages/geofence (display only, no override)
 lib/link                    LinkSession: bytes -> DumlFramer -> packets/OsdGeneral, counters
   │
 lib/transport               LinkTransport: Simulated | Replay | Aoa (Kotlin shim)
   │
 packages/duml, geofence     pure Dart, unit-tested off-device
   │
 DJI RC (USB host) ──radio──> Phantom 3 Professional
```

### `awto_dji_app` — read-only milestone
- `transport/`: `LinkTransport` (bytes, state, connect/disconnect/write); `SimulatedAircraftTransport`
  (OSD General circle flight via the duml encoder); `ReplayTransport` (raw or hex-text captures,
  same as `telemetry_scan.dart`; no timestamps in captures, so paced per frame); `AoaTransport`
  + `android/.../AoaShim.kt` (raw byte pump, compile-only, untested without the RC).
- `transport/aoa_mux.dart`: incremental channel demux. The diagnostic TCP relay
  forwards versioned records; CONNECT `relayVideo=false` skips camera/FPV forwarding.
  Unknown channels and discarded bytes remain visible. See the operator guide
  for record format and older-app compatibility.
- `transport/aoa_identity.dart`: the one place for AOA strings; description/version/uri/serial are
  PLACEHOLDERs. `res/xml/accessory_filter.xml` must be kept in sync by hand.
- `link/LinkSession`: receive-only; packet/CRC counters, last-seen, health, 2000-entry packet log.
- `safety/SafetyGate`: position + altitude checked against the geofence; zones are SAMPLE data.
- `duml` `DumlFramer` gained `badFrames` / `onBadFrame` (additive) for CRC-error accounting.
- Nothing in the app sends control; `write` is rejected by the simulated and replay transports.

Run (Flutter at `~/development/flutter/bin`):
```
cd app/awto_dji_app && flutter pub get
flutter test && flutter analyze
flutter build apk --debug       # Android; needs the SDK at ~/Android/Sdk
```

**There is no on-screen connect form** - the app is driven by Android intents
(CONNECT/DISCONNECT/GIMBAL/SEND), not a UI. See
[`../docs/phone-bridge-operator-guide.md`](../docs/phone-bridge-operator-guide.md) for
driving it end to end: phone/ADB setup, intents and their extras, the PC-side relay
and command proxy, and known gotchas.

### `packages/duml` — done and verified
Pure Dart. `dart test` passes, including byte-for-byte reproduction of a real
captured DJI packet and the reference CRCs.

- `DumlPacket.encode()/decode()` — the wire format, both checksums.
- `DumlFramer` — reassembles whole frames from the AOA byte stream, resynchronising
  on the SOF after corruption.
- `OsdGeneral` — decodes the Flight Controller telemetry push (position, altitude,
  velocity, attitude). Offsets are from the public dji-firmware-tools dissector; the
  deeper flight-state/GPS-count fields are left out until confirmed against a capture
  from this aircraft.

## Status / honest limits

- **Reading the bird** (telemetry) over DUML is well-trodden and the decoder is ready
  to validate against a real capture.
- **Sending flight control** (takeoff, virtual-stick) over DUML has **no public
  precedent** for the Phantom 3. The exact command packets and any handshake DJI GO
  uses are not publicly documented. The codec can carry such packets, but their
  contents are unverified and are not implemented here.

## Next step

Wire the AOA transport shim and read live telemetry from the aircraft into the Dart
`DumlFramer`/`OsdGeneral` — the first real "direct" milestone — before any attempt at
control. That needs a capture from the actual RC to lock down endpoints and confirm
the telemetry offsets.
