# What we can actually pull from the bird right now (2026-10-24)

Current-state reference, not a provenance doc (see `apk-vs-dissector-gap-report-2026-10-23.md`
for how the 723-name catalog was extracted). This is "what works today" - update it as
decoders are added/confirmed, don't let it go stale.

## Confirmed decoded telemetry (push, arrives automatically once connected - not polled)

| Name | cmdset/id | Decoder | Fields | Confidence |
|---|---|---|---|---|
| OSD General | 0x03/0x43 | `app/packages/duml/lib/src/telemetry.dart` `OsdGeneral` | lat, lon, relative height, vgx/vgy/vgz, pitch/roll/yaw | V - offsets from public dissector |
| Gimbal GetPushParams | 0x04/0x05 | `scripts/re/duml_telemetry.py` `_gimbal_push` | pitch, roll, yaw, err, mode | V - cross-checked live, byte6 mode confirmed via AutoCalibration test (awto-dji#16) |
| RC/OSD signal quality | 0x09/0x08 | `app/packages/duml/lib/src/rc_signal.dart` `RcSignalQuality` | antenna1Dbm, antenna2Dbm | **I** - inferred from value-range only, not decompiled source. Pending verification (background decompile of `dji.pilot` running 2026-10-24, see awto-dji#16/#26 threads) |

Python-side pretty-printer for all of the above plus named-but-undecoded frames:
`scripts/re/duml_pretty.py` (device+command names, decodes what's in `PUSH_DECODERS`,
falls back to hex for everything else).

## Confirmed structured send (payload layout known, `duml_commands.py` REGISTRY)

| Name | cmdset/id | Notes |
|---|---|---|
| `gimbal.angle` | 0x04/0x0a | AngleControl - relative, has duration field |
| `gimbal.absAngle` | 0x04/0x14 | AbsAngleControl - absolute, explicit axis-invalid flags |
| `gimbal.control` | 0x04/0x01 | Mode set (YawNoFollow/FPV/YawFollow) |
| `gimbal.requestCtrPermission` | 0x06/0x22 | **Reply must be checked** - `scripts/re/verify.py`'s `wait_for_permission_reply` decodes it (1=Refused, 2=TimeOut, 3=Getted); `duml_cli.py` alone does not |
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
