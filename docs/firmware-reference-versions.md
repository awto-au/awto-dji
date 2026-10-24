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
