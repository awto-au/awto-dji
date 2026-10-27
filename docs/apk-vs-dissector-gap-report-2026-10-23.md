# APK vs public dissector: cmdset/cmdid coverage comparison, upgrade + flight command sequencing

> **Applicability correction, 2026-10-25:** the 723-row inventory is GO 4 4.3.64
> shared middleware, not the capabilities of one P3 aircraft. Its IDs remain useful;
> product applicability, inferred command sequences and global negative findings
> are superseded where noted below. See the [2026-10-25 P3 evidence audit](dji-go-p3-evidence-audit-2026-10-25.md).

Status tags: **V** verified here, **I** inferred, **U** unknown. Scope: see `apk-analysis.md`
section 0 for the dynamic-unpack scope decision this builds on - numeric protocol facts only,
never DJI's code. Sources: `docs/data/apk-dynamic-cmdset-ids.tsv` (723 rows, from the
dynamically-unpacked `dji.midware.data.config.P3.CmdSet` enum, DJI GO 4 v4.3.64) and the public
`o-gs/dji-firmware-tools` Wireshark dissector (GPL-3.0, `/mnt/2tb/git/dji-firmware-tools`).
Reproduce: `python3 -I scripts/re/extract_apk_cmdset.py` then
`python3 -I scripts/re/compare_cmdset_gaps.py` (log `tmp/logs/compare_cmdset_gaps.log`, output
`docs/data/cmdset-gap-report.tsv`).

## Headline: cmdset 10 (Mono/Binocular / "EYE" / vision system) is badly under-documented upstream

- **V.** 49 real, named command IDs in this APK's vision/obstacle-avoidance cmdset (DJI's own
  name: `EYE`; dissector's label: `Mono/Binocular`, aka Vision) have **no entry at all** in the
  public dissector - the biggest gap of any cmdset, both in absolute count and ratio (49 missing
  vs only 19 the dissector has that this APK doesn't use). Examples: `GetHandGestureEnabled`/
  `SetHandGestureEnabled`, `SendTrackingUserLocation`, `DrawOperation`/`GetPushDrawState`,
  `Stabilization`/`GetPushStabilizationState`, `SetPanoramaEnabled`/`GetPushPanoramaInformation`,
  `GetPushFaceDetectionTakeOffState`, `GetPushPalmControlState`, `SetTimeLapseSubMode`. Full list:
  `docs/data/cmdset-gap-report.tsv`, filter `cmdset_value=10 AND status=apk_only`.
- **I.** Every other cmdset shows the opposite pattern - the dissector has *more* entries than
  this one APK snapshot (e.g. Flight Control: APK 114 vs dissector 191, Wi-Fi: 32 vs 64). That's
  expected: the dissector aggregates command IDs across many product generations and APK
  versions over years; this is one multi-product GO 4 version's snapshot. The `dissector_only` rows do not establish whether a command is newer, older or supported by P3; those product/version attributions require separate evidence. The vision-system result inverts that pattern, which is why it stands out as
  genuinely interesting rather than expected noise.

## Real discrepancy caught: "JoyStick" ID mismatch (not yet resolved)

- **V.** The dissector documents `0x29` (41) as `'Joystick'` in `FLYC_UART_CMD_TEXT`
  (`dji-dumlv1-flyc.lua`), with `0x2A` (42) as `'Function Control'` - the pair matches the
  well-known public DUML flight-control command shape (set flight-mode flags, then stream stick
  values).
- **V.** This APK's `CmdSet.FLYC.CmdIdType` enum has **no entry at value 41/0x29 at all** - its
  `JoyStick` constant is at decimal **142** (0x8E), a completely different wire ID.
  `FunctionControl` does match at 42/0x2A.
- **U, unresolved:** whether `JoyStick(142)` is a newer/SDK-level joystick API distinct from the
  real low-level stick command (which this APK's enum may simply not name, falling through as
  unlabelled/`Other`), or a genuine naming collision. Classic GO 3.1.8 also has JoyStick(142) and FunctionControl(42), so this is not resolved by app selection. P3 applicability needs a relevant classic-GO trace, public SDK evidence or firmware analysis; a GO 4 capture on another product cannot settle P3 behaviour.

## Firmware upgrade command inventory (real IDs, not execution order)

**V**, from the dynamically-unpacked enum (`apk-analysis.md` section 0 scope):

| id | name | role (I, from naming + dissector cross-ref) |
|---|---|---|
| 7 | RequestUpgrade | initiate upgrade for a target device |
| 64 | GetPushRequestUpgrade | device-side push: upgrade available/requested |
| 65 | ControlUpgrade | start/confirm the upgrade |
| 9 | TranslateData | firmware data block transfer (dissector: `'Update Transmit'`) |
| 10 | TranslateComplete | signal end of transfer |
| 66 | GetPushUpgradeStatus | progress/status push during flashing |
| 67 | AckUpgradeStop | stop/abort acknowledgement |
| 42 | TransferFile | generic file transfer (config/cfg files, not necessarily firmware) |
| 15 | UpgradeSelfRequest | device asks the app for self-upgrade permission (traced in `app-upgrade-sequence.md`) |

Matches the dissector's own General cmdset labels for 0x07/0x08/0x09 (`'Enter Loader'`,
`'Update Confirm'`, `'Update Transmit'` - **V**, cross-checked) and this repo's own earlier
m0900 firmware-upgrade-path finding (`docs/fpga-upgrade-path.md`: "m0900 handles 0x07/0x08/0x0A
only; no 0x09 handler" - the same COMMON command numbering context; no renumbering is implied).

## Superseded P3 flight-sequence inference (names and IDs retained)

Scope & safety: see `SAFETY.md`. Listed
here because it's needed for `awto_dji_app`'s own interoperability work on the owner's aircraft.

**Historical hypothesis only, P3 order/authority not verified.** Names cannot establish a protocol sequence. Retained for provenance, superseded as a P3 implementation recipe. Real IDs
from the APK enum (`cmdset 3`, Flight Control):

1. `SimScan`(0)/`SimGetParams`(1)/`SimParams`(2)/`SimRc`(17) - simulator path, separate from real
   flight (used for the DJI GO "flight simulator" feature already referenced elsewhere in this
   repo's docs).
2. `GetPushActiveRequest`(97) / `SetActiveResult`(98) - aircraft activation handshake (matches
   dissector's `0x62 'FlyC Activation Exec'` - **V**, ID matches: 98 = 0x62).
3. `SetHomePoint`(49) - establish RTH point, typically set once GPS lock is acquired.
4. `FunctionControl`(42) - confirmed matching the dissector's `0x2A`, which the dissector's own
   comment notes "sets `g_real.wm610_app_command.function_command`" - **I**: this is the
   arm/mode-enable gate before `ExecFly`.
5. `ExecFly`(39) - matches dissector's `0x27 'Exec Fly'` exactly (**V**, ID match). Single
   generic command; the specific action (takeoff/land/go-home/etc.) is almost certainly a
   payload sub-byte, not a separate command ID - **U**, payload layout not examined.
6. Continuous control during flight: real stick values - **U, see the JoyStick discrepancy
   above**, not confirmed which command ID this APK actually uses on the wire.
7. `NavigationSwitch`(128) / `WayPointMissionSwitch`(134) etc. - waypoint/autonomous mission
   commands, separate from manual flight.

**Not resolved this pass:** exact payload layouts for `ExecFly`/`FunctionControl` (would need the
dissector's `flyc_function_control_dissector`/equivalent payload-field definitions, not yet
cross-read) and the real stick-command ID. Next step if this is wanted: read
`dji-dumlv1-flyc.lua`'s payload dissector functions for `0x27`/`0x29`/`0x2A` directly (public,
no APK/scope concerns) rather than guessing from the APK's enum alone.

## Debug/test/diagnostic surface sweep across all 723 commands

Swept the full extracted set for debug/test/diagnostic/calibration/fault-related names.
**V, real factory/test-mode surface exists**, beyond what any earlier doc in this repo had
catalogued:

| cmdset | id | name | note |
|---|---|---|---|
| FLYC(3) | 181/182 | `FaultInject` / `GetPushFaultInject` | literal fault-injection test mechanism - simulate failures to test handling |
| HD Link(9) | 40 | `SetSdrStartLog` | trigger logging on the radio link itself |
| HD Link(9) | 22 | `GetPushDebugInfo` | generic link debug info push |
| HD Link(9) | 55 | `GetHdtvPushException` | link-layer exception/fault push |
| COMMON(0) | 240 | `GetPushLog` | shared cross-device log-push (resolves to per-device names: `1860`/`2100`/`2150`/`Rc` depending on sender devicetype) |
| EYE(10) | 1/13/14 | `GetEyePushLog`/`GetPushTrackLog`/`GetPushPointLog` | vision-system logs |
| EYE(10) | 9 | `DebugCtrlParam` | generic vision-system debug control |
| EYE(10) | 42/47 | `GetPushException`/`GetPushSensorException` | vision-system fault reporting |
| CAMERA(2) | 163/206 | `SetCalibrationControl`/`GetCalibrationControl` | camera calibration |
| CAMERA(2) | 193 | `SetLogMode` | camera-side log mode |
| GIMBAL(4) | 8/48 | `AutoCalibration`/`GetPushAutoCalibrationStatus` | gimbal self-calibration |
| RC(6) | 3/248 | `SetCalibration`/`GetFDRcCalibrationStatue` | RC stick/control calibration |
| WIFI(7) | 128 | `GetPushLog` | wifi-module log push |

**I, worth pursuing if more debug surface is wanted:** `FaultInject` is the standout - a real
factory/QA test mechanism, not a normal flight command, and the kind of thing worth decoding its
payload for (what fault categories exist, whether it's gated behind an activation/auth check).
Payload layouts for any of these: not yet examined, same "decode on demand" priority approach as
the flight-sequence work above.

## No FPGA die/chip-ID readout identified in the examined GO 4 tree (2026-10-23)

Checked whether any command dumps the Lightbridge FPGA's own die/chip ID.

- **V.** `grep -rn "ChipId" tmp/apk/dynamic/decompiled/sources/` finds exactly one DJI hit:
  `DataCommonGetDeviceSerialNumber.java`'s `DeviceIndex` enum - `BoardNum(1), ChipId(2),
  ModuleNum(3), FlycNum(4)`. Sent via `GetSerialNum` (`CmdIdCommon` value 81 = `0x51`, COMMON
  cmdset, already in our 304-command `Get*` catalog) with `receiverType = DeviceType.DM368` -
  the air-side video SoC, a different chip from the Lightbridge FPGA in this project's own
  architecture (`control-plane-re.md`'s "Air FPGA" vs the separate DM368 video chip). **Superseded inference:** a DM368 receiver does not prove which silicon ultimately supplies the value; a processor can proxy another component. The returned identifier's provenance is U. Nothing in the file mentions "fpga" (checked directly).
- **V.** The only other "chip state" command found, `general_encrypt_config`'s
  `GetChipState`/`GetModuleState` (`dji-dumlv1-general.lua` line ~570, cmd_type 1/2), is the
  ATSHA204/AT88 component-auth chip (returns "At88 chip state flags", config/data-zone lock
  bits), and
  still not an FPGA readout.
- **V.** `DataCameraGetSensorID.java` exists but queries the camera's image sensor, not the
  Lightbridge FPGA - a different "ID" command entirely, same naming-looks-relevant trap.
- **Superseded global conclusion:** the searches did not identify an FPGA die-ID query in this GO 4 tree. They do not prove that no such DUML request exists or that JTAG is the only possible route. Classic GO 3.1.8 lacks the particular `DataCommonGetDeviceSerialNumber` class found here; endpoint capabilities and the identity behind returned values remain U. Firmware-side negative searches remain bounded to their named images.

## Files

- `docs/data/apk-dynamic-cmdset-ids.tsv` - all 723 (cmdset, cmdid) facts from the dynamic unpack.
- `docs/data/cmdset-gap-report.tsv` - full apk_only/dissector_only diff per cmdset.
- `scripts/re/extract_apk_cmdset.py`, `scripts/re/compare_cmdset_gaps.py` - reproduce both.
