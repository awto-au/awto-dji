# License-compliance review

Two parts: (A) the open-source components inside the DJI firmware and DJI's resulting
obligations, found by scanning the unpacked modules; and (B) this repository's own
license hygiene.

## A. DJI Phantom 3 firmware — open-source inventory

Fingerprints from `strings` over the unpacked `P3X_FW_V01.11.0020` modules. Counts are
match frequency, i.e. a strong/weak presence signal.

| Module | Role | Open-source found | License class |
|---|---|---|---|
| `m0100` | Camera SoC (Linux core) | Linux kernel, glibc, **busybox**, OpenSSL, wpa_supplicant, zlib, libjpeg, dropbear, + ThreadX | GPLv2 / LGPL / permissive / (ThreadX = commercial) |
| `m0101` | Camera loader | ThreadX (Express Logic) | commercial RTOS — no OSS obligation |
| `m0800` | DM368 video encoder | GNU / GPL present (small Linux) | GPLv2 |
| `m1900` | Lightbridge air FPGA | one stray BSD string | negligible |
| `m0900` | Lightbridge MCU (STM32) | **none** — bare-metal Thumb-2 | proprietary |
| `m0306`/`m0305` | A3 flight controller | **µC/OS** (Micrium RTOS) — see code-provenance.md | commercial RTOS — no OSS obligation |
| `m0400` | Gimbal | **none** | proprietary |
| `m1700` | Vision positioning | **none** | proprietary |

Takeaways:

- **The flight-critical stack is proprietary *application* code — but not from scratch.**
  Disassembly (see `code-provenance.md`) shows the A3 flight controller runs the **µC/OS**
  commercial RTOS (Micrium); the gimbal and STM32 radio MCU are bare-metal on vendor
  libraries. No GPL obligation (µC/OS/ThreadX were commercial at the P3 era), but the
  code is clearly built on third-party foundations, not written entirely in-house.
- **The camera and video-encoder SoCs are Linux** and therefore carry real obligations:
  - **GPLv2** — Linux kernel and busybox → DJI must provide corresponding source
    (including their kernel modifications, e.g. `mach-ambarella`, and the busybox
    config/applets).
  - **LGPL** — glibc → source + ability to relink.
  - **Permissive** (OpenSSL, wpa_supplicant = BSD, zlib, libjpeg = IJG, dropbear) →
    attribution / license-text notices; no source obligation.
  - **ThreadX** is a commercial RTOS (Express Logic), licensed by DJI; no public-source
    obligation. Its presence alongside Linux is the AmbaLink dual-OS design.
- **Observed compliance gap:** DJI lists Linux 3.10 + busybox at
  [dji.com/opensource](https://www.dji.com/opensource), but their kernel archive
  currently returns **0 bytes** (see `scripts/check_gpl_sources.sh`). busybox downloads;
  the kernel does not. glibc and the permissive components are not individually listed.
  So, as of this review, DJI's published offer for the Phantom 3 is **incomplete** — the
  kernel source is effectively unavailable from DJI (though mirrored elsewhere, since
  GPL source is freely redistributable; see `firmware-overview.md`).

This is an observation from the binaries, not a legal opinion.

## B. This repository

**Repo license:** GPL-3.0 (`LICENSE`).

**No third-party or vendor material is committed.** Only our own source and docs are
tracked — no DJI firmware, APK, `.so`, kernel tarball, or extracted module is in the
repo. All such files live outside it (analysis env only). Verified with `git ls-files`.

**Our packages and their dependencies:**

| Component | Declared | Runtime deps | Dep license | GPL-3.0 compatible? |
|---|---|---|---|---|
| `app/packages/duml` (Dart) | GPL-3.0-only (SPDX note) | none (pure Dart) | — | n/a — clean |
| `app/packages/geofence` (Dart) | GPL-3.0-only (SPDX note) | none (pure Dart) | — | n/a — clean |
| `ground/python`* | GPL-3.0-only | pymavlink | LGPL-3.0 | yes |
| `ground/rust`* | GPL-3.0-only | mavlink | MIT / Apache-2.0 | yes |

\* parked, not yet committed. Dev-only `test` (Dart) is BSD-3-Clause, GPL-compatible.

All dependencies are GPL-3.0-compatible: LGPL-3.0 and MIT upgrade cleanly into GPLv3,
and Apache-2.0 is one-way compatible with GPLv3. Nothing pulls a GPL-incompatible
license (no SSPL, no proprietary, no Apache-only-with-GPLv2 conflict since we are v3).

**Status: compliant.** Tidy-ups applied/left as options:
- Added `SPDX-License-Identifier: GPL-3.0-only` notes to the Dart `pubspec.yaml`s.
- If the ground packages are committed later, their stated licenses already match.
- Optional: add a short `THIRD-PARTY-NOTICES` once runtime deps ship, listing pymavlink
  (LGPL-3.0) and mavlink (MIT/Apache-2.0) with their license texts.
