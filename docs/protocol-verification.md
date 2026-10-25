# DUML protocol — open-source assertion audit (Phantom 3 Professional)

Every claim this project relies on, checked against primary sources rather than
repeated on trust. Reference: [`o-gs/dji-firmware-tools`](https://github.com/o-gs/dji-firmware-tools)
(GPL-3), which ships Phantom 3 firmware symbols and whose CRC-16 seed is commented
`# P3/P4/Mavic` — i.e. it is a P3-authoritative source, not a newer-drone proxy.

The checks are reproducible: `scripts/verify_protocol.py` run against a clone of the
reference. Last run: 13/13 structural checks pass.

## Verified (PASS)

| Assertion | How verified | Result |
|---|---|---|
| Frame starts with SOF `0x55` | reference + captured packet | PASS |
| DUML v1 header is 11 bytes | `sizeof(DJICmdV1Header)` | PASS |
| `ver_length_tag`: bits 0-9 length, bits 10-15 version | reference getters + captured packet | PASS |
| Header CRC-8: reflected poly `0x8C`, seed `0x77`, first 3 bytes | 200 random vectors vs reference; captured byte[3]=0x33 | PASS |
| Packet CRC-16: reflected poly `0x8408`, seed `0x3692`, over len−2 | 200 random vectors vs reference; captured tail `74 24` | PASS |
| Seed `0x3692` is the Phantom 3 seed | reference comment `v = 0x3692 # P3/P4/Mavic` | PASS |
| `cmd_type` byte: encrypt bits 0-2, ack bits 5-6, response bit 7 | reference bitfield getters | PASS |
| Device types: APP=2, CAMERA=1, FLYCONTROLLER=3, GIMBAL=4, REMOTE_RADIO=6, PC=10 | `COMM_DEV_TYPE` | PASS |
| Command sets: GENERAL=0, CAMERA=2, FLYCONTROLLER=3, RADIO=6 | `CMD_SET_TYPE` | PASS |
| OSD General telemetry = cmd_set `0x03`, cmd_id `0x43` | flyc dissector dispatch table | PASS |
| OSD leading layout: lon f64@0, lat f64@8, relHeight i16@16, vgx/vgy/vgz i16, pitch/roll/yaw i16 | flyc dissector offsets | PASS |
| Captured RC packet `55 0d 04 33 0a 06 eb 34 40 06 01 74 24` decodes as PC→RC, cmd_set 6/id 1, ack-after-exec, version 1 | reproduced byte-for-byte by the Dart codec | PASS |

## Corroborated (supported, confirm against a live capture)

| Assertion | Evidence | Note |
|---|---|---|
| OSD `longitude`/`latitude` are **radians** (convert ×180/π) | P3 firmware symbol `aLatLonRadiConC` ("Lat/Lon Radians Conversion"); π constants in the FC (`dbl_just_pi`, `dbl_pi_half`) | Dissector types the field as a bare `double`. Radians is well-supported but the unit isn't stated on the wire — a live value settles it (Sydney lat ≈ −0.591 rad vs −33.87°). |
| The connection is AOA (controller = USB host, phone = accessory, `DJI`/`T600`) | DJI app manifest: `usb.accessory required`, `com.android.future.usb.accessory`, `accessory_filter.xml` = `<usb-accessory model="T600" manufacturer="DJI"/>`, no `device_filter` | Read from DJI GO 4; `T600` is the P3/Inspire-1 identity. Confirm the P3 RC enumerates the same with `lsusb`. |

## Does NOT apply to the Phantom 3 (common cross-wiring to avoid)

| Claim seen in the wild | Reality for P3 |
|---|---|
| "The RC is USB bulk endpoints `0x01`/`0x81`, VID `18d1:4ee7`→`2ca3:1021`" | That is the **DJI RC 2** (Mini 4 Pro), from `rusty407/dji-rc2-linux-joystick`. The P3 uses **AOA**, not host-side bulk. Do not reuse those endpoints/IDs. |
| "Just use a `usb_serial` Flutter plugin" | Those are phone-as-host FTDI/CDC. P3 is phone-as-accessory (AOA). Wrong transport. |

## Unproven (no public precedent — not implemented)

| Claim | Status |
|---|---|
| Flight control (takeoff, virtual-stick, e.g. flyc cmd_id `0x29` "Joystick") can be sent to a Phantom 3 over DUML from a third-party app | **Unverified.** No public project sends flight commands to a P3 over DUML and flies it. The command *names* exist in the dissector, but the payload formats, required session/authority state, and any handshake are not publicly documented. The app's own control+geofence logic lives in native libraries (`libmain.so`, `libSDKRelativeJNI.so`, `libFlyForbid.so`), which this project does not reverse-engineer. The authoritative route for control is the DJI Mobile SDK v4 (which supports the P3) or a verified on-hardware capture. |

## Cross-checked against the DJI binary (APK)

Not just the third-party reference — the following were read directly out of the DJI
app (`dji.go.v4`, the newest app that still carries the P3 midware classes). Class
names are obfuscated, but the protocol identifiers survive, and they match the
open-source assertions.

| Open-source assertion | Found in the DJI APK | Where |
|---|---|---|
| Transport is USB Accessory (AOA), P3-specific | `dji/midware/usb/P3/UsbAccessoryService` with `handleNewMethod`/`handleOldMethod` (the two AOA open paths), `native_getUsbAccessoryAttachedString`, `com.dji.accessory.USB_ACCESSORY_ATTACHED` | `libSDKRelativeJNI.so`, classesN.dex |
| `T600` accessory = Phantom 3/4 RC | string `"Phantom 3 or 4 Remote Controller"`; `productType=`, `P3C` upgrade components | classesN.dex |
| Packets carry a command set | `setCmdSet`, `cmdset=0x` | classesN.dex |
| Telemetry is an "OSD push" family | `DataOsdGetPushCommon` (+ `DataOsdGetPushHome`, `…DevicesState`, `…Config`, …) | classesN.dex |
| OSD fields: lon, lat, height, velocity x/y/z, pitch/roll/yaw, GPS count, flight state | getters `getLongitude`, `getLatitude`, `getHeight`, `getXSpeed`, `getYSpeed`, `getZSpeed`, `getPitch`, `getGpsNum`, `getFlycState` | classesN.dex |
| Frames are CRC-checked | `checkCrc`, `crc16` (e.g. `fullBuffer crc16=fail=`) | classesN.dex |
| P3 has its own protocol namespace | `dji/midware/data/config/P3/*`, `dji/midware/data/manager/P3/*` | classesN.dex |

What the APK does **not** expose in cleartext: the CRC seed/polynomial and the exact
field byte-offsets (those are in compiled logic, and are the ones already proven via
the reference + the captured packet above), and any flight-control payload format
(the "unproven" row stands). The DUML *structure* is corroborated from both the
open-source reference and the vendor binary; they agree.

## Why we don't RE the app for the protocol

The DJI app's DUML/flight logic is in obfuscated native `.so` files, interleaved with
no-fly enforcement (`libFlyForbid.so`). Extracting control from those binaries is
impractical and entangled with safety enforcement. The benign
protocol *structure* above is fully recoverable from the open-source reference and is
all this codec needs.
