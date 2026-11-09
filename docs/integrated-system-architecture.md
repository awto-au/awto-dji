# Integrated system architecture + consolidation plan

> Goal (Dan, 2026-11-10): combine the accumulated pieces into **one integrated system** with a
> cleanup plan. Tracks awto-dji #102 (full-system sim) as the umbrella; touches #77, #89, #2.

## Current state — the fragmentation

Three parallel DUML/protocol implementations + several fakes/bridges across four trees:

| Concern | Dart (`app/`) | Python (`ground/python/`) | Rust (`rust/`, `ground/rust/`) |
|---|---|---|---|
| DUML protocol | `packages/duml` (richest: packet, crc, catalog, camera, gimbal, motor, rc, `generated/`) | `protocol.py` (60 L) + `duml_bridge.py` | `awto_dji_core/src/protocol.rs` (321 L) |
| Fake / sim target | `simulated_transport` (telemetry-only), `replay_transport`, `capture_loader` | `sim_bridge.py` (MAVLink point-mass) | `broker.rs`, `ground/rust/.../fly.rs` |
| Transport / link | `transport/*` (aoa_mux, aoa, link, replay, simulated) | MAVLink clients | DRC client/ffi |
| RE / sim surface | — | — | `fpga/m2001` Verilator emit (#89), planned Renode (#2) |

Problems: 3 protocol sources of truth drift; 2+ fakes model the bird differently; FPGA work split `fpga/` vs `ground/fpga/`; two Rust trees; no single interface the clients share, so "sim vs real" isn't swappable.

## Target — one system, layered, swappable-fidelity target

```
 CLIENTS        Dart app        Rust DRC core        MAVLink ground (QGC)
                   │                  │                     │
 LINK IFACE   ── common link interface: DUML command pipe + telemetry stream ──
                   │                                        │
 BRIDGE                                         MAVLink <-> DUML (one bridge)
                   │
 TARGET       pluggable, same interface, rising fidelity:
   (fidelity)   • real bird        — USB/AOA transport
                • software fake     — behavioral DUML responder (#102 phase-0, #77)
                • gate-level FPGA   — Verilator emit (#89) via Renode co-sim bridge
                • full system       — real MCU firmware in Renode (#2) ↔ FPGA ↔ MCU
```

Two pillars:
1. **One canonical protocol.** Single source of truth (a DUML spec/catalog), from which each language binding is generated or derived — no three hand-maintained copies. The Dart `duml/generated` + `catalog` is the closest to a spec today; promote that (or a language-neutral spec it emits from) to canonical.
2. **One target interface** (the existing `LinkTransport`: `bytes` in, `write` out, `state`). Every target — real, fake, FPGA, full-system — implements it, so any client runs against any target by swapping one object. Clocks ideal, slow subsystems behavioral, until a reason to raise fidelity (the #102 mixed-fidelity rule).

## Consolidation plan (incremental, each step shippable)

1. **Declare the canonical protocol** and stop forking it. Pick the Dart catalog/`generated` as the spec; make Python/Rust bindings generated or thin wrappers over it (or a shared `.proto`-like catalog). Delete the hand-copied divergent bits. (Blocks drift; biggest win.)
2. **One target interface.** Formalise `LinkTransport` as THE boundary; make `sim_bridge` and the fakes implement it (or sit behind it) so Dart/Python/Rust clients attach identically.
3. **One fake bird.** Merge `simulated_transport` (telemetry) + a command-responder (#102 phase-0) + the capture-corpus seeding (#77) into a single behavioral target. Retire the duplicate point-mass logic in `sim_bridge` (keep only its MAVLink translation, behind the bridge).
4. **One FPGA tree.** Fold `ground/fpga/` into `fpga/`; the Verilator emit (#89) becomes a target behind the interface via the Renode co-sim bridge.
5. **One Rust tree / clear roles.** Resolve `rust/awto_dji_core` vs `ground/rust`: core = protocol+DRC, ground = MAVLink client; no protocol copy in both.
6. **Full-system target.** Real firmware in Renode (#2) + FPGA co-sim, presented through the same interface — the #102 end state.

## Non-goals / keep
- Keep the DUML vs MAVLink **layering** (DUML app↔bird; MAVLink ground↔bridge) — one bridge translates; don't collapse them.
- Keep per-language clients; unify the **protocol** and the **target interface**, not the UIs.

## Open decisions (need Dan)
- Canonical protocol: promote Dart catalog as the spec, or author a language-neutral spec both generate from?
- How aggressive now: declare canonical + one interface first (low risk), or also merge trees (`ground/fpga`→`fpga`, the two Rust trees) in the same pass?
