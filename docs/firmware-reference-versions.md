# Firmware reference versions — per-module "latest known-good" table

Built 2026-10-24 for `fw_version_check.py` (awto-dji#32): what each live `GetVersion`
(General/0x00/0x01) reply should read if the aircraft is on DJI's last-published
firmware. Three candidate sources were checked; only the first gives real per-module
numbers with reproducible provenance.

## Sources checked

1. **Local firmware archive (used)** — `firmware/unpacked/P3X_FW_V01.11.0020_*.ini`
   and `firmware/unpacked/C1_FW_V01.06.0000_*.ini` (dji-firmware-tools unpack of the
   containers hashed in `docs/data-manifest.md`). Each module header's `version=`
   line is the string DJI shipped inside that module, for the package DJI's own
   download page still lists as current (`docs/firmware-upgrade-log-review.md:115-119`:
   dji.com Phantom 3 Pro download page, checked 2026-10-24, lists aircraft firmware
   **1.11.20**, dated 2017-07-06 — matches `P3X_FW_V01.11.0020` exactly). **V** — hash-
   verified container, real shipped string, not an inference.
2. **SD-card upgrade log** (`docs/firmware-upgrade-log-review.md`) — real device
   history, but **not usable as "latest known-good"**: its own last-completed sessions
   *downgrade* some modules and flag equal versions as "need upgrade" even after a
   successful rewrite (review doc lines 43-51). Also, its last-installed FC version
   (`2.4.20.28`) traces to package `01.10.0090` (review doc line 38), not `01.11.0020`
   — an older, different package, not a format variant of the same release. Kept here
   only as historical context, not fed into the automated comparison.
3. **Online sources** — checked 2026-10-24. DJI's Phantom 3 Pro download page
   (dji.com/downloads/products/phantom-3-pro) exposes only the aggregate container
   ("Phantom 3 Firmware 1.11.20", 2017-07-06 ZIP) and an aggregate release-notes PDF of
   the same date — **no per-module version numbers on the page**; the release-notes
   PDF itself was not fetched (DJI's historical release notes are prose bug-fix lists,
   not version tables, for every other DJI product's equivalent page seen so far — a
   judgement call, not a fetch failure). A `phantompilots.com`/`forum.phantomhelp.com`
   search turned up two unrelated firmware-complaint threads, no per-module version
   archive. **Conclusion: no online source adds a number the local archive doesn't
   already have — not pursued further.**

## Module ↔ live device mapping

Container module → the `DeviceType` this repo's AOA/serial tooling addresses it as
(`scripts/re/duml_proto.py`). Only the five devices `fw_version_check.py` has a receiver
type for are listed; other container modules (ESCs, battery, vision/sonar, FPGAs) are
out of scope for issue #32 (no direct `GetVersion` receiver wired yet).

| Device (DeviceType) | Module | `version=` (ini) | Role (ini comment) |
|---|---|---|---|
| flight_controller (3) | m0306 | `02.04.5170` | "main controller 'A3' app" |
| gimbal (4) | m0400 | `01.48.0000` | "gimbal mdl 0" |
| camera (1) | m0100 | `01.32.5432` | "camera 'Ambarella A9SE' App" |
| remote_controller (6) | C1 m1400 | `04.10.0006` | "lightbridge MCU 'LPC1765 GROUND LB2'" — matches `data-manifest.md`'s "ground radio MCU (LPC1765)" for `c1_m1400.bin` |
| ofdm_radio (9, added this session) | m0900 | `04.01.0000` | "lightbridge MCU 'STM32F103'" — the air radio MCU |

Camera cross-check: `01.32.5432` matches the **running** camera firmware string
independently read from the SD card's `CameraLogCur.log`
(`docs/firmware-upgrade-log-review.md:93`, "camera firmware 01.32.5432") — same number
from two unrelated sources (container header vs. a live boot log). **V.**

## ini version string → wire `GetVersion` format

`docs/firmware-upgrade-log-review.md:140` already documents the rule: *"DJI container
versions encode the final two byte components in the third decimal field."* i.e.
`AA.BB.CCDD` (ini) → `A.B.C.D` (wire, same 4-field dotted format `version.dart`'s
`CommonVersion` decodes) by dropping the leading zero from `AA`/`BB` and splitting the
4-digit `CCDD` into two 2-digit bytes.

| Module | ini | → wire (by the rule above) | Confidence |
|---|---|---|---|
| m0400 gimbal | `01.48.0000` | `1.48.0.0` | **V** — matches the SD log's independently-observed gimbal version (`1.48.0.0`, review doc line 53) exactly |
| m0100 camera | `01.32.5432` | `1.32.54.32` | I — no independent wire-format reading to cross-check against |
| m0306 FC | `02.04.5170` | `2.4.51.70` | I — SD log's FC numbers (`2.4.20.28`/`.50`) are from a *different* package (01.10.0090), so they neither confirm nor contradict this; no same-package cross-check exists |
| C1 m1400 RC | `04.10.0006` | `4.10.0.6` | I — no cross-check available |
| m0900 OFDM | `04.01.0000` | `4.1.0.0` | I — no cross-check available; the SD log's unidentified `[11 01]`/`[19 00]` lines are not confirmed to be this module |

**Caveat carried into the tool**: only the gimbal translation is independently
confirmed. A "mismatch" reported for FC/camera/RC/OFDM means *this translated string
differs from the live reply*, not an inspected and re-confirmed defect — treat as
"needs manual confirmation of the translation rule for this module" until it is cross-
checked the same way the gimbal number was.

## Decoder offset bug found and fixed (2026-10-24, awto-dji#32)

Before any translation-rule number can mean anything, the GetVersion *reply decoder*
itself had a bug: `CommonVersion.fromPayload` (`app/packages/duml/lib/src/version.dart`,
ported into `scripts/re/fw_version_check.py`'s `decode_common_version`) read
`hardwareVersion` at payload offset 1, one byte too early.

**V — fixed, cross-confirmed two independent ways:**
1. `o-gs/dji-firmware-tools`'s `general_version_inquiry_dissector`
   (`/mnt/2tb/git/dji-firmware-tools/comm_dissector/wireshark/dji-dumlv1-general.lua:120-160`,
   externally RE'd, unrelated to this repo's possibly-wrong-app APK decompile — awto-dji#30):
   a GetVersion *response* has **two** leading unknown bytes before `hw_version`
   (offset 0 and 1), not one — `hw_version` starts at offset 2, `loaderVersion` at
   18, `firmwareVersion`(app) at 22, the production/safe-upgrade flags dword at 26.
2. Two real captured GetVersion replies,
   `captures/sessions/2026-10-24/duml_probe.log` (first one also logged at
   `docs/identity-queries.md:18`):
   - RC/GL300C handset reply (receiver 0x0e): old offset decodes `hardwareVersion` as
     garbled `"\x10GL300C"`; the +1 offset gives clean `"GL300C"`.
   - A second, unprogrammed device (receiver 0x14, same log, line ~167-173): the +1
     offset decodes **both** `loaderVersion` and `firmwareVersion` to
     `"255.255.255.254"` — byte-for-byte the same placeholder value independently
     observed in the SD-card upgrade log's own `[19 00]` lines
     (`firmware-upgrade-log-review.md:62-64`, `v255.255.255.254 -> v1.0.8.96`). Two
     unrelated sources landing on the identical sentinel is strong confirmation.

Fixed in `version.dart`/`version_test.dart` (all 37 Dart tests pass) and
`fw_version_check.py`. Minimum payload length is now 30 bytes (was 29).

**Also fixed in `fw_version_check.py`**: the `remote_controller` entry queried
`DeviceType.remote_controller` (wire byte 0x06), which — per
`docs/identity-queries.md:7,18,22` on real RC USB-serial hardware — never replies to
any of 10 queries including GetVersion. The RC's m1400 MCU answers on wire address
0x0e (`DeviceType.osd` in this repo's enum; DJI's own naming for that address, despite
being physically the RC handset's MCU here). Changed the DEVICES mapping accordingly.

**What this does *not* resolve**: the ini→wire split-vs-unsplit question for
FC/camera/RC/OFDM. Neither real capture above is running the "latest" reference
firmware (the GL300C capture decodes to firmware "05.24.28.00", matching neither the
split nor unsplit form of ini `04.10.0006` — this aircraft/RC pairing is simply on a
different, unidentified build), so it cannot confirm or deny the translation rule for
that module. The o-gs dissector uses the **same** generic 4-byte-split struct for
every module including camera (no camera-specific override exists in
`dji-dumlv1-camera.lua`), which is mild supporting evidence for the existing
split-into-two-bytes guess (`01.32.5432` → `1.32.54.32`) — but the camera/CameraLogCur
"unsplit" strings (`1.30.5036`, `1.32.5432`) seen in the SD log are very likely read
from the Ambarella Linux camera's own self-reported ASCII string (a different
reporting path entirely — camera runs embedded Linux, not the bare-metal MCU firmware
the generic GetVersion struct was written for), not from a decoded DUML GetVersion
wire reply, so they neither confirm nor contradict the split-rule guess either way.
**FC/camera/RC/OFDM translation confidence stays at I** — no live reply from this
aircraft at the *reference* version exists yet for any of them.

## Reference table used by `fw_version_check.py`

| DeviceType | Reference (wire format) | Confidence | Source |
|---|---|---|---|
| flight_controller | `2.4.51.70` | I | m0306, `P3X_FW_V01.11.0020` |
| gimbal | `1.48.0.0` | V | m0400, `P3X_FW_V01.11.0020`, cross-confirmed vs SD log |
| camera | `1.32.54.32` | I | m0100, `P3X_FW_V01.11.0020`, container number itself V (cross-confirmed vs CameraLogCur) |
| remote_controller | `4.10.0.6` | I | C1 m1400, `C1_FW_V01.06.0000` |
| ofdm_radio | `4.1.0.0` | I | m0900, `P3X_FW_V01.11.0020` |

No module here is "verified latest and verified translation" except gimbal. The tool
reports confidence alongside match/mismatch/unknown for exactly this reason — see
issue #32.
