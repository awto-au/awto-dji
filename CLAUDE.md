# CLAUDE.md — agent onboarding

Context for an agent/engineer continuing this repo. Read this, then `HANDOVER.md` (state +
next steps), then `docs/README.md` (doc index).

## What this project is

Interoperability software to control/monitor a **DJI Phantom 3 Professional directly**
(app-to-bird), for an aircraft the operator (dan@awto.au) **owns** — a Flutter app with a
pure-Dart DUML implementation, not the DJI Cloud API. There is also a Rust direct-control
core and (parked) MAVLink ground clients.

## Honesty conventions (followed throughout the docs)

- Separate **verified / inferred / needs-tooling**. The docs mark these explicitly; keep
  doing so. A notable example: MCU-layer cleartext is proven, but **over-the-air** encryption
  is NOT ruled out (see `what-is-actually-secret.md` LAYER CAVEAT). Do not restate inference
  as proof.
- Cite exact offsets / reproduction commands so claims can be re-derived.

## Firmware RE rules

- `docs/re-rules.md` (applied here) → canonical `awto-dan/docs/embedded/embedded-rules.md`. Read before Ghidra work.

## Repo layout

- `app/packages/duml/` — pure-Dart DUML codec + `tool/telemetry_scan.dart` (telemetry/ID
  scanner). `app/packages/geofence/` — safety gate. Both have passing tests.
- `rust/awto_dji_core/` — Rust protocol/client/DRC core + FFI. `ground/` — parked MAVLink.
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
