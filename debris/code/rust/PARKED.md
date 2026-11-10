# Parked: Rust Cloud-API core (2026-11-10, Dan)

Moved here from `rust/awto_dji_core` and `ground/rust`.

- **What:** a Rust "direct-control core" (`awto_dji_core`: `protocol`/`client`/`drc`/`ffi`) plus a `ground/rust` fly client. Per its own `src/lib.rs` it is **DJI Cloud API / Enterprise** control — MQTT, Dock / Pilot 2 RC, DRC stick control with a dead-man timer, a C-ABI FFI.
- **Why parked:** this project controls the Phantom 3 **directly, app-to-bird (DUML)**, **not via the DJI Cloud API** (the Phantom 3 is not an Enterprise aircraft and has no Cloud API — see `../../../CLAUDE.md`). The Rust core is the wrong path for the goal, has **no live consumer** (no `dart:ffi` / `awto_dji_core` reference in the app or ground), and was untouched since its initial commit 2026-10-22.
- **Active languages going forward:** **Dart** (the Flutter app + pure-Dart DUML codec) and **Python** (RE tooling + the MAVLink↔DUML ground bridge). See `../../../docs/integrated-system-architecture.md`.
- **Recoverable:** tracked in git; un-park by moving back if a Cloud-API / Enterprise use case appears.
