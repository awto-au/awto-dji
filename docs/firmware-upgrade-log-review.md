# Camera SD-card firmware upgrade log review

Reviewed 2026-10-24 from the attached camera card, without changing its files or
starting an upgrade. The user supplied the same log as pasted text.

Tracking: [issue #24](https://github.com/awto-au/awto-dji/issues/24).
The public issue contains the review scope only; detailed device/log evidence
remains in the local working tree.

## Evidence and provenance

Stable partition ID:
`/dev/disk/by-id/usb-Ambarell_A9_DSC_EVK_Platf_0001-0:0-part1`,
observed mounted at `/run/media/dan/8765-4321`.

- Card file: `MISC/LOG/P3X_FW_LOG_AB.txt`, 73,682 bytes.
- SHA-256: `ba4e138007ac1376cee9f7e209889e6f2b5e2e4c92be343904ad742382e1ccc8`.
- The 73,680-byte user attachment is an exact byte prefix; the card adds CRLF.
- Preserved originals: `captures/sessions/2026-10-24/sdcard-review/`.
- Machine-readable session inventory:
  [sdcard-upgrade-review-2026-10-24.json](data/sdcard-upgrade-review-2026-10-24.json).

The file combines historical sessions with dates from 2016 through 2023 and
undated `remo-con disconnect` entries. It is not a current per-command error log.
The bracketed counters reset across boots/resumes. RTC-derived dates and filesystem
timestamps must not be treated as reliable dates for the undated latest attempts.

## Verified findings

There are **41 boot sessions: eight packet-level successes, 32 cancellations at
version checking, and one final session without a terminal outcome**. No explicit
`Packet upgrade failed` result appears. Cancellation during version checking does
not by itself show a failed flash.

| Package | Detected sessions | Observations |
|---|---:|---|
| 01.09.0060 | 10 | Initial FC application transition 2.4.15.5 → 2.4.20.18; later equal-version cancellations |
| 01.10.0090 | 16 | Includes three resume records within sessions; the last three boot sessions use this package |
| 01.11.0020 | 12 | Several completed changes and subsequent version-check cancellations |
| 01.11.0030 | 3 | Package reports vlink 01.11.0030 ↔ 01.11.0020; do not assume identical package/module versions |

The last two **completed** sessions each end with packet-level success, after
rewriting camera, radio, ESC, FC, gimbal and other modules. The first of those
changes the FC application `[03 06]` from **2.4.20.50 → 2.4.20.28** and the four
ESCs `[12 00–03]` from **1.13.0.0 → 1.11.0.0**. This is evidence of downgrading
those modules, despite the log using the word “upgrade.”

Those sessions flag equal versions as `need upgrade`, even after successful
rewrites. This suggests a forced/recovery/update-policy path; the exact cause
requires tracing its firmware flag and version checks. It is not proof that each
module was faulty or that an update remains active now.

The gimbal `[04 00]` reports **1.48.0.0** in the latest checks and a successful
rewrite in each of the last two completed sessions. That does not prove physical
gimbal motion or correct control-command semantics.

Repeated `[11 01]` messages report **1.8.0.0 → 2.0.0.33, firmware ... not support**.
Earlier sessions show the same message alongside packet-level success; treating
this line alone as the failure cause would be unsupported. Investigate that
module's applicability/version policy.

`[19 00]` repeatedly reports **255.255.255.254 → 1.0.8.96**; one late attempt
temporarily says `device not detected`. Its placeholder-like version and detection
semantics need review; this is not enough to diagnose an FPGA fault.

The final session stops at counter **17782**, `Waiting for user confirm...`.
There is no subsequent timeout, flash-start, success or failure line in the
preserved file. This is an incomplete record, not evidence that flashing started.

## Card state and beeping

At inspection, the root contains only `DCIM`, `MISC`,
`System Volume Information` and the empty `0x40003000.dji` logging marker.
There is **no root firmware .bin, P3X_FW_DEBUG, P3X_FW_DEBUG_2 or P3X_FW_LOOP**.
No update file or flag was added, removed or renamed in this review.

The operator reported persistent beeping during gimbal-command testing. Its source
and cause remain unresolved. No causal link between this historical upgrade log,
command rejection and the current beeping is established. Gimbal testing has
stopped pending status/error review.

DUML provides per-command reply return codes and subsystem status pushes, rather
than a single universal error-log command. The live gimbal `04/0a` reply retained
in `captures/sessions/2026-10-24/app-live-logcat.txt` decodes to status byte
`00`; the bounded `04/14` oscillation test recorded no matching acknowledgements
and no meaningful pitch excursion (144 samples, −4.0° to −3.8°). Neither result
identifies the beeping source. Review GO's `Ccode`, gimbal push/check-status and FC
check-status decoders against time-aligned captures before further motion tests.

## Diagnostic logging confirmation

`MISC/LOG/CameraLogCur.log` now exists and reports **42,466 bytes**. Its readable
prefix contains Ambarella startup output, camera firmware **01.32.5432**, and an
RTC startup of **2014-01-01 00:00:00**. This confirms actual diagnostic output is
present at the traced path with the marker installed; it does not isolate the
marker as the only possible activation path.

A sequential read copied **32,768 bytes**, then returned **EIO**. Only that prefix
is preserved as `sdcard-review/CameraLogCur-readable-prefix.log`; it is explicitly
incomplete. The cause could involve the media/export/storage path and is not
diagnosed here. No repair, remount, formatting or retry loop was performed.

## Follow-up

- Trace equal-version `need upgrade` policy and the DEBUG/DEBUG_2/LOOP gates.
- Establish module-specific meanings for `[11 01]`, `[19 00]` and status `[05]`.
- Read current component versions independently; historical final versions do not
  guarantee the currently running set.
- Correlate beeping with current gimbal/FC/battery/RC status and command replies.
- Investigate the camera log EIO before assuming the preserved prefix is complete.
- Keep firmware flashing and marker changes outside this read-only review.

## Is the aircraft on the latest firmware?

As checked on 2026-10-24, DJI's
[Phantom 3 Professional download page](https://www.dji.com/downloads/products/phantom-3-pro)
lists **aircraft firmware 1.11.20**, dated 2017-07-06. The repository already has
the `P3X_FW_V01.11.0020` reference package/modules. That establishes availability
locally, not installation on the aircraft.

The last completed SD history entry uses **1.10.0090**, which is older. The
`1.11.0030` entries elsewhere in the history do not establish a newer public DJI
release; their package origin and version linkage remain unresolved.

The phone currently has **GO 4 4.3.64** (`dji.go.v4`) installed. DJI's P3 Pro page
lists the original **DJI GO** (Android 3.1.83 at inspection), so GO 4's application
version is not an aircraft-firmware confirmation or a verified P3 reference UI.
Shared legacy protocol classes in GO 4 do not establish command applicability
to this aircraft.

Live Common/GetVersion queries were attempted for camera, FC, gimbal and RC.
The accessory reader had already failed with **EIO at 02:04:29 phone time**,
and USB functions had returned to `adb`; no new version replies were obtained.
Therefore **the currently running aircraft/RC version set is not confirmed**.
No upgrade was initiated. Compare again after restoring the accessory link.

See [component-version-comparison-2026-10-24.json](data/component-version-comparison-2026-10-24.json)
for the last completed historical module versions compared with local 1.11.20
module headers. DJI container versions encode the final two byte components in
the third decimal field; camera versions use their special decimal convention.
