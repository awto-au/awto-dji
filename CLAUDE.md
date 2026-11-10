# CLAUDE.md — agent onboarding

Context for an agent/engineer continuing this repo. Read this, then `HANDOVER.md` (state +
next steps), then `docs/README.md` (doc index).

## What this project is

Interoperability software to control/monitor a **DJI Phantom 3 Professional directly**
(app-to-bird), for an aircraft the operator (dan@awto.au) **owns** — a Flutter app with a
pure-Dart DUML implementation, not the DJI Cloud API. Two active languages: **Dart** (the app +
DUML codec) and **Python** (RE tooling + the MAVLink↔DUML ground bridge). A Rust Cloud-API core
and the Rust ground client are **parked** in `debris/code/rust/` (wrong path for app-to-bird, no
consumer — see its `PARKED.md`).

## Honesty conventions (followed throughout the docs)

- Separate **verified / inferred / needs-tooling**. The docs mark these explicitly; keep
  doing so. A notable example: MCU-layer cleartext is proven, but **over-the-air** encryption
  is NOT ruled out (see `what-is-actually-secret.md` LAYER CAVEAT). Do not restate inference
  as proof.
- Cite exact offsets / reproduction commands so claims can be re-derived.

## Keys and RE scope

- Key analysis, recovery, derivation and reverse engineering of firmware are in scope (Dan, 2026-11-02, widened 2026-11-04). Wine/running DJI binaries is allowed.
- Public repo may hold a hash or partial section of a key, with a comment that the full key is held (where). Full keys stay out of the public repo.
- Never present key work as not done, or hide how it was done. State what was recovered, by what method, at V/I/U.
- Still out: geofence defeat, control override (`docs/SAFETY.md`).

## Docs hygiene

- Dated history and superseded results live in `docs/HISTORY.md`; analysis docs state the current result only (no superseded numbers).
- Each claim tagged V/I/U with offsets and a reproduction command; fix a doc when a finding changes it.

## Firmware RE rules

- Every RE pass (agent or human) follows `docs/re-rules.md` Process 1-6: rename-first, committed TSV + headless driver, regenerated Ghidra dumps committed, base-address gate. Agent briefs must cite it.
- `docs/re-rules.md` (applied here) → canonical `awto-dan/docs/embedded/embedded-rules.md`. Read before Ghidra work.

## Repo layout

- `app/packages/duml/` — pure-Dart DUML codec + `tool/telemetry_scan.dart` (telemetry/ID
  scanner). `app/packages/geofence/` — safety gate. Both have passing tests.
- `ground/python/` — MAVLink↔DUML ground bridge (`duml_bridge.py`, `sim_bridge.py`) + RE tooling.
- `scripts/`, `fpga/m2001/scripts/` — RE/analysis + the DUML catalog pipeline (`duml_catalog_build.py`).
- `debris/code/rust/` — **parked** Rust Cloud-API core + ground client (see `PARKED.md`).
- `docs/` — ~22 analysis docs (index in `docs/README.md`).
- `scripts/fpga/` — Mistral netlist analysis scripts. `scripts/verify_protocol.py`.

## How to work here

- Run Dart: install Flutter/Dart, then `cd app/packages/duml && dart pub get && dart test`.
- MCU RE: radare2 `-a arm -b 16 -m 0` (LPC1765/STM32F103, Cortex-M, images load at the base
  in each doc). Ghidra recommended for deeper work. Firmware is **not** in the repo — see
  `HANDOVER.md` "DATA NOT IN THE REPO" to obtain/unpack it.
- Branch/remote: `origin` = github.com/awto-au/awto-dji. Work has been kept on `main` and
  `ccr-31b4a6f2-8fofnf` (identical). Commit + push; the operator syncs other machines via pull.

## The one-paragraph model (what we believe, and how sure)

The Phantom 3 Lightbridge link is a WiMAX/LTE-family OFDM modem in an FPGA fed by an AD9363;
the FPGA is **just the datastream engine** — the IDs, pairing, telemetry and OSD all live in
the MCUs/app as **cleartext DUML** (proven in `m1400` code), with the only real crypto being
ATSHA204 component auth. So reading the ID, reading telemetry, and app-to-bird control need
no SDR/descrambler — tap the already-demodulated DUML at USB/UART. **Open:** exact PHY params
(needs Renode on `m0900`) and whether the link is encrypted over the air (needs an SDR
capture — not ruled out).
