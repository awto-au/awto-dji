# What we can actually pull from the bird right now (2026-10-24)

> **2026-10-25 evidence update:** `dji.pilot` is classic DJI GO. The [2026-10-25 P3 evidence audit](dji-go-p3-evidence-audit-2026-10-25.md)
> reconfirms selected gimbal, signal, version and OSD structures in firmware-era
> GO 3.1.8. Structural V remains distinct from a live P3 result; GO 4
> catalog membership alone does not prove a P3-supported command.

Current-state reference, not a provenance doc (see `apk-vs-dissector-gap-report-2026-10-23.md`
for how the 723-name catalog was extracted). This is "what works today" - update it as
decoders are added/confirmed, don't let it go stale.

## Confirmed decoded telemetry (push, arrives automatically once connected - not polled)

| Name | cmdset/id | Decoder | Fields | Confidence |
|---|---|---|---|---|
| OSD General | 0x03/0x43 ("GetPushCommon") | **Canonical source now `docs/schema/duml/osd_general.yaml`** (awto-dji#33) - generates both `app/packages/duml/lib/src/generated/osd_general.dart` (`OsdGeneral`, re-exported from `telemetry.dart`) and `scripts/re/duml_generated/osd_general.py` | lat, lon, relative height, vgx/vgy/vgz, pitch/roll/yaw, **+2026-10-24: motorUp/motorBlocked/compassError/imuPreheated/motorFailedCause/imuInitFailReason/flycVersion** (Dart only - not yet in the Python target, see schema `targets`) | **U, not V**, for the push itself not showing up live - checked 2026-10-24 against the full session capture (~44MB, ~2.5h): 0x03/0x43 never appears once. The offset-30+ fields ARE **V** structurally - byte-for-byte port of the real decompiled `DataOsdGetPushCommon.java` getters (dji.go.v4). That same class is *also* registered for cmdset 0x09 ("hdLink"/OSD) id 0x01 (`CmdSet.java`: both `FLYC.GetPushCommon(67,...)` and `OSD.GetPushCommon(1,...)` point at it) - `OsdGeneral.matches()` accepts either. **I, not confirmed live**: worth re-checking the capture against 0x09/0x01 before assuming this push never arrives (awto-dji#16). **Fixed 2026-10-24 during the schema migration**: the old hand-written `scripts/re/duml_telemetry.py` `_osd_general_push` had latitude/longitude swapped relative to the Dart source of truth (offset 0 is longitude, offset 8 is latitude) - exactly the cross-language drift awto-dji#33 exists to stop |
| Motor-arming interlock + gimbal health | same push, offsets 32 (flags), 38/51 (cause), 47 (flycVersion), 49 (IMU reason) | `MotorStartFailedCause`/`ImuInitFailReason` enums, `app/packages/duml/lib/src/motor_status.dart` | ~100-value cause enum incl. compass/IMU/battery/ESC errors, calibration-in-progress, `gimbalDisorder`/`gimbalPitchShock`/etc, `remoteUsbConnected` (200-255 range) | **V** structurally (byte-for-byte port of the real enum/getters); semantics not live-confirmed - see awto-dji#16 |
| Firmware/hardware version | 0x00/0x01 ("GetVersion") | `app/packages/duml/lib/src/version.dart` `CommonVersion` | hardwareVersion, firmwareVersion, loaderVersion, isProduction, isSupportSafeUpgrade | **V** structurally (byte-for-byte port of `DataCommonGetVersion`'s `getHardwareVer`/`getFirmVer`/`getLoader`/`getInfo`, dji.go.v4); not yet cross-checked against a live reply |
| Gimbal GetPushParams | 0x04/0x05 | `scripts/re/duml_telemetry.py` `_gimbal_push` | pitch, roll, yaw, err, mode | V - cross-checked live, byte6 mode confirmed via AutoCalibration test (awto-dji#16) |
| RC/OSD signal quality | 0x09/0x08 | `app/packages/duml/lib/src/rc_signal.dart` `RcSignalQuality` | aggregateQuality (0-127), isUplink, antenna1Dbm, antenna2Dbm | V - confirmed against decompiled `DataOsdGetPushSignalQuality.java` (dji.go.v4) 2026-10-24. An earlier version of this decoder read only the secondary per-antenna dBm bytes and wrongly concluded the link was strong while the real quality byte (aggregateQuality) was reporting 53/127 on the represented scale (about 42% of the numeric maximum), not a calibrated RF-performance percentage - see awto-dji#16 |

Python-side pretty-printer for all of the above plus named-but-undecoded frames:
`scripts/re/duml_pretty.py` (device+command names, decodes what's in `PUSH_DECODERS`,
falls back to hex for everything else).

## Capturing the REAL vendor app's own traffic (not just our own app's)

`scripts/re/phone_kprobe_sniff.py` - non-invasive kernel-level capture of a connected
phone's outgoing DUML commands (app -> RC), via `ftrace`/`kprobes` on the AOA gadget
driver's `acc_write()`. Confirmed working 2026-10-24 against live `dji.pilot` traffic:
CRC-valid, SIMPLE-decrypted, catalog-matched real commands (`GetBoardNumber`,
`GetParams`/DM368, `GetParamsByHash`/FLYC, `GetPushConfig`/OSD) logged into the same
`aoa_relay_frames.log` format everything else here reads.

Why kprobes and not `strace`/`usbmon`: `strace` (ptrace-based) reliably crashes
`dji.pilot`/`dji.go.v4` once past their consent flow (AppGuard anti-tamper, confirmed
this session); this phone's kernel has no `usbmon` module at all. `ftrace`/`kprobes`
use neither mechanism.

**Incoming direction (RC -> app) not solved.** Tried hooking `acc_complete_out` (the
USB-OUT completion callback, chosen because the kernel buffer is already populated at
function entry, unlike `acc_read` where the buffer is empty until the syscall
returns) - captured values were static/unchanging across many hits, inconsistent with
real telemetry. Likely an ARM DMA cache-coherency stale read, not a real capture. Open
for a future pass.

## Confirmed structured send (payload layout known, `duml_commands.py` REGISTRY)

| Name | cmdset/id | Notes |
|---|---|---|
| `gimbal.speedControl` | 0x04/0x0c | **The real app's actual interactive-control command** (confirmed 2026-10-24: `DJIFpvGimbalPitchView.java` uses this, sent on a 40ms timer while a control button is held, nothing else). Permission is bit7 of byte6 in this same packet - no separate handshake. Never tried against hardware yet - highest-priority thing to test once the aircraft is back. See `scripts/re/duml_commands.py` docstring |
| `gimbal.angle` | 0x04/0x0a | AngleControl - relative, has duration field. Payload layout V (byte-for-byte vs real `dji.pilot` decompile), but confirmed 2026-10-24 this is used for RC master/slave handoff and the third-party Mobile SDK, **not** this app's own single-pilot gimbal control - that's a distinction from the tested UI flow; the cause of the failed physical tests is not proven |
| `gimbal.absAngle` | 0x04/0x14 | AbsAngleControl - same story as `gimbal.angle`: payload layout V, but not the command the app's own gimbal UI uses |
| `gimbal.control` | 0x04/0x01 | Mode set (YawNoFollow/FPV/YawFollow). Payload layout V; also not part of the real single-pilot gimbal control path |
| `gimbal.requestCtrPermission` | 0x06/0x22 | Confirmed 2026-10-24: used for the RC master/slave handoff scenario, not interactive gimbal control - the reason it never got a reply in the recorded attempts remains unproven. `scripts/re/verify.py`'s `wait_for_permission_reply` decodes it anyway (1=Refused, 2=TimeOut, 3=Getted) for when it *is* relevant. The exact wire byte offset (byte 11, the dedicated ack-status field, not payload[0] as a "payload" concept - though numerically the same byte our parser treats as payload[0]) is now V, confirmed in `dji/midware/data/a/a/b.java` |
| `camera.requestIFrame` | 0x02/0xb3 | Forces an IDR-adjacent re-sync; does not fix the no-true-IDR issue (awto-dji#26) |
| `gimbal.autoCalibration` | 0x04/0x08 | Gimbal self-test/calibration trigger - `app/awto_dji_app/lib/link/gimbal_commands.dart`. **V, confirmed working against real hardware** 2026-10-24 (real pitch movement + mode change observed, awto-dji#16): wire frame `550e046602040074200408008c2f` (sender=APP, receiver=GIMBAL, ackType=beforeExec, payload=`[0x00]`), reproduced byte-for-byte by `GimbalCommands.autoCalibration()` and covered by `app/awto_dji_app/test/gimbal_commands_test.dart`. Now wired to a button on the app's Diagnostics screen |
| `diagnostics.getVersion` | 0x00/0x01 | `app/awto_dji_app/lib/link/diagnostics_commands.dart` - requests `CommonVersion` (above) from a given receiver (FC/gimbal/camera/RC). Payload layout of the request is just empty; not independently fired against hardware this session |

## Diagnostics screen (app/awto_dji_app/lib/ui/diagnostics_screen.dart, added 2026-10-24)

Brings across the kind of status DJI GO 4/DJI GO show: motor-arming interlock +
cause, compass/IMU flags, a derived "gimbal health" line (from the cause enum),
per-device firmware/hardware version (on request), and the gimbal self-test button.

**Deliberately left out** - no matching `Data*.java` class or catalog name found in
the dji.go.v4/dji.pilot decompiles searched this session:
- Motor test trigger (distinct from the arming-interlock *status* above, which is
  wired up).
- Camera test trigger.
`DataCommonGetDeviceStatus` (0x00/0x0c) was found and read, but its only field is a
single opaque "mode" bit with no enum/doc in the decompile - not decoded; would be a
guess, not a confirmed status.

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
  version-pinned classic GO APK (`tmp/apk/go_3.1.8/static/sources/` for this audit), or use GO 4 only as a candidate source, for the matching `Data*.java`
  class the way `telemetry.dart`/`rc_signal.dart` were built.
- The remaining ~390 names (`Set*`, `Request*`, device-specific commands) - catalogued,
  cmdset/id known, nothing else.

## To pull a specific field we don't have yet

1. `rg -n "<PushName or similar>" tmp/apk/go_3.1.8/static/sources/` (if the decompile
   exists locally - gitignored, not in this repo) to find the real `Data*.java` class
   and its byte offsets.
2. Add a small decoder following the `telemetry.dart`/`rc_signal.dart` pattern: a class
   with `cmdSet`/`cmdId` constants, `matches()`, `fromPayload()`.
3. Cross-check live before trusting it - a value that merely looks plausible is not
   confirmation (see the RC signal-quality entry above).
