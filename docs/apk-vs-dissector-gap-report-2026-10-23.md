# APK vs public dissector: cmdset/cmdid coverage comparison, upgrade + flight command sequencing

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
  versions over years; this is one version's snapshot for one product. Those `dissector_only`
  rows are mostly newer-product commands this P3-era APK never defines, not real gaps in the
  tool. The vision-system result inverts that pattern, which is why it stands out as
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
  unlabelled/`Other`), or a genuine naming collision. Needs a live capture of DJI GO 4 actually
  flying (not available this session - aircraft was stationary) or arm64 native analysis to
  resolve, not a Java-enum read.

## Firmware upgrade command sequence (real IDs, `CmdSet.COMMON` / cmdset 0)

**V**, from the dynamically-unpacked enum (`dji-analysis.md` section 0 scope):

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
| 15 | UpgradeSelfRequest | app-initiated self-upgrade-check path |

Matches the dissector's own General cmdset labels for 0x07/0x08/0x09 (`'Enter Loader'`,
`'Update Confirm'`, `'Update Transmit'` - **V**, cross-checked) and this repo's own earlier
m0900 firmware-upgrade-path finding (`docs/fpga-upgrade-path.md`: "m0900 handles 0x07/0x08/0x0A
only; no 0x09 handler" - note that doc's "0x0A" is a different numbering context, not yet
reconciled with this table - flagged, not resolved here).

## Flight command sequence (structural facts only - names, IDs, rough order; no payload bit layouts)

Scope note: this is the same category of information the public dissector already documents in
detail (command existence, names, rough grouping) - not new exploit material, and this repo's
stated scope explicitly keeps geofence/flight-restriction logic out of catalogued detail. Listed
here because it's needed for `awto_dji_app`'s own interoperability work on the owner's aircraft.

**I**, inferred from command names + typical DJI app flow + dissector cross-reference, real IDs
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

## Files

- `docs/data/apk-dynamic-cmdset-ids.tsv` - all 723 (cmdset, cmdid) facts from the dynamic unpack.
- `docs/data/cmdset-gap-report.tsv` - full apk_only/dissector_only diff per cmdset.
- `scripts/re/extract_apk_cmdset.py`, `scripts/re/compare_cmdset_gaps.py` - reproduce both.
