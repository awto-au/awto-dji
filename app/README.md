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
- Data is a **raw byte stream** over the accessory file descriptor.
- **DUML** frames ride on that stream (SOF `0x55`, header CRC-8, body CRC-16).

## Layers

```
 Flutter UI (Dart)
   │
 packages/duml  ── pure Dart, no native code, unit-tested off-device
   │   framing + CRC8/CRC16 + packet build/parse + telemetry decode
   │
 AOA transport  ── the ONE small native shim (~60 lines): open the DJI
   │               accessory, pump bytes to/from Dart. No logic here.
   │
 DJI RC (USB host) ──radio──> Phantom 3 Professional
```

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
