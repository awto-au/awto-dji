# What we can actually pull from the bird right now (2026-10-24)

Current-state reference, not a provenance doc (see `apk-vs-dissector-gap-report-2026-10-23.md`
for how the 723-name catalog was extracted). This is "what works today" - update it as
decoders are added/confirmed, don't let it go stale.

## Confirmed decoded telemetry (push, arrives automatically once connected - not polled)

| Name | cmdset/id | Decoder | Fields | Confidence |
|---|---|---|---|---|
| OSD General | 0x03/0x43 ("GetPushCommon") | `app/packages/duml/lib/src/telemetry.dart` `OsdGeneral` | lat, lon, relative height, vgx/vgy/vgz, pitch/roll/yaw | **U, not V** - checked 2026-10-24 against the full session capture (~44MB, ~2.5h): this cmdset/cmdid never appears once. cmdset/cmdid matches our own APK catalog exactly, so not a wrong-id guess - not yet root-caused (awto-dji#16). Don't trust position/attitude from `ground/python/awto_dji_ground/duml_bridge.py` until this is resolved |
| Gimbal GetPushParams | 0x04/0x05 | `scripts/re/duml_telemetry.py` `_gimbal_push` | pitch, roll, yaw, err, mode | V - cross-checked live, byte6 mode confirmed via AutoCalibration test (awto-dji#16) |
| RC/OSD signal quality | 0x09/0x08 | `app/packages/duml/lib/src/rc_signal.dart` `RcSignalQuality` | aggregateQuality (0-127), isUplink, antenna1Dbm, antenna2Dbm | V - confirmed against decompiled `DataOsdGetPushSignalQuality.java` (dji.go.v4) 2026-10-24. An earlier version of this decoder read only the secondary per-antenna dBm bytes and wrongly concluded the link was strong while the real quality byte (aggregateQuality) was reporting a mediocre ~42% the whole time - see awto-dji#16 |

Python-side pretty-printer for all of the above plus named-but-undecoded frames:
`scripts/re/duml_pretty.py` (device+command names, decodes what's in `PUSH_DECODERS`,
falls back to hex for everything else).

## Confirmed structured send (payload layout known, `duml_commands.py` REGISTRY)

| Name | cmdset/id | Notes |
|---|---|---|
| `gimbal.speedControl` | 0x04/0x0c | **The real app's actual interactive-control command** (confirmed 2026-10-24: `DJIFpvGimbalPitchView.java` uses this, sent on a 40ms timer while a control button is held, nothing else). Permission is bit7 of byte6 in this same packet - no separate handshake. Never tried against hardware yet - highest-priority thing to test once the aircraft is back. See `scripts/re/duml_commands.py` docstring |
| `gimbal.angle` | 0x04/0x0a | AngleControl - relative, has duration field. Payload layout V (byte-for-byte vs real `dji.pilot` decompile), but confirmed 2026-10-24 this is used for RC master/slave handoff and the third-party Mobile SDK, **not** this app's own single-pilot gimbal control - that's almost certainly why it never produced movement here |
| `gimbal.absAngle` | 0x04/0x14 | AbsAngleControl - same story as `gimbal.angle`: payload layout V, but not the command the app's own gimbal UI uses |
| `gimbal.control` | 0x04/0x01 | Mode set (YawNoFollow/FPV/YawFollow). Payload layout V; also not part of the real single-pilot gimbal control path |
| `gimbal.requestCtrPermission` | 0x06/0x22 | Confirmed 2026-10-24: used for the RC master/slave handoff scenario, not interactive gimbal control - explains why it never got a reply all session despite being sent before every move attempt. `scripts/re/verify.py`'s `wait_for_permission_reply` decodes it anyway (1=Refused, 2=TimeOut, 3=Getted) for when it *is* relevant. The exact wire byte offset (byte 11, the dedicated ack-status field, not payload[0] as a "payload" concept - though numerically the same byte our parser treats as payload[0]) is now V, confirmed in `dji/midware/data/a/a/b.java` |
| `camera.requestIFrame` | 0x02/0xb3 | Forces an IDR-adjacent re-sync; does not fix the no-true-IDR issue (awto-dji#26) |

Send any of these: `python3 -I scripts/re/duml_cli.py send <name> [--field value...]`.
Verify-by-telemetry: `python3 -I scripts/re/verify.py <name> --watch <decoder> --field <f> --target <v>`.

## Known by name only - payload layout NOT decoded (`duml_catalog.py`, 723 names total)

- 163 names starting `Get*` (explicit queries - e.g. `GetVersion`, `GetSerialNum`,
  `GetDeviceStatus`, `GetBatteryGroupsSingleInfo`, `GetSmartBatteryCurrentStatus`,
  `GetSdrConfig`) - sendable via `duml_cli.py send <Name> --payload <hex-or-empty>`,
  CATALOG-only path, but the REPLY payload has no struct to decode it with. Empty-payload
  queries are safe by convention (see `apk-vs-dissector-gap-report-2026-10-23.md`).
- 169 names containing `Push` (passive telemetry other than the two above) - arrive
  automatically, visible as raw hex in `aoa_relay_frames.log`/`duml_pretty.py`, not
  decoded into fields. Worth decoding next if a specific field is needed: grep the
  decompiled APK (`tmp/apk/dynamic/decompiled/` if present) for the matching `Data*.java`
  class the way `telemetry.dart`/`rc_signal.dart` were built.
- The remaining ~390 names (`Set*`, `Request*`, device-specific commands) - catalogued,
  cmdset/id known, nothing else.

## To pull a specific field we don't have yet

1. `grep -rn "<PushName or similar>" tmp/apk/dynamic/decompiled/` (if the decompile
   exists locally - gitignored, not in this repo) to find the real `Data*.java` class
   and its byte offsets.
2. Add a small decoder following the `telemetry.dart`/`rc_signal.dart` pattern: a class
   with `cmdSet`/`cmdId` constants, `matches()`, `fromPayload()`.
3. Cross-check live before trusting it - a value that merely looks plausible is not
   confirmation (see the RC signal-quality entry above).
