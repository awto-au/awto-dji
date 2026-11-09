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
1. **One canonical protocol.** The source-attributed, multi-version data already exists but is fragmented across `docs/data/`:
   - `apk-duml-commands.tsv` (46, `evidence` col), `dll-duml-commands.tsv` (8, `source` col = literal DLL strings), `cmdset-gap-report.tsv` (357), `apk-cmdset-devicetype.tsv` (catalog.dart reads this).
   - `duml-table-matches-*.json` — the command table located across firmware **versions** (C1_FW_V01.05.0070/0072/0080…, offsets + sha256).
   Canonical step = **merge these into one versioned DUML catalog** (per command: cmdset/cmdid, name, direction, payload, device types, per-source evidence, firmware-version coverage), then **generate** the Dart/Python/Rust bindings from it. The per-source tables are the evidence inputs; the matches JSON gives version coverage. No inventing a spec, no promoting one hand-copy — reconcile what's there.
2. **One target interface** (the existing `LinkTransport`: `bytes` in, `write` out, `state`). Every target — real, fake, FPGA, full-system — implements it, so any client runs against any target by swapping one object. Clocks ideal, slow subsystems behavioral, until a reason to raise fidelity (the #102 mixed-fidelity rule).

## Consolidation plan (incremental, each step shippable)

1. **Build the one canonical catalog** by reconciling the `docs/data/` source tables (apk/dll/firmware) + the version-matches JSON into a single versioned DUML catalog (one file, per-command source evidence + fw-version coverage). Then generate the Dart/Python/Rust bindings from it and delete the hand-copied divergent bits. (Blocks drift; biggest win. The data exists — this is reconciliation + codegen, not authoring.)
   - **Done:** `docs/data/duml-catalog.json` (`scripts/duml_catalog_build.py`) + Dart binding (`scripts/duml_catalog_gen_dart.py`, tested). Workflow to add/change a command: `duml-catalog-workflow.md`. **Remaining:** Python + Rust generators, then delete the hand-copied lists.
2. **One target interface.** Formalise `LinkTransport` as THE boundary; make `sim_bridge` and the fakes implement it (or sit behind it) so Dart/Python/Rust clients attach identically.
3. **One fake bird.** Merge `simulated_transport` (telemetry) + a command-responder (#102 phase-0) + the capture-corpus seeding (#77) into a single behavioral target. Retire the duplicate point-mass logic in `sim_bridge` (keep only its MAVLink translation, behind the bridge).
4. **One FPGA tree.** Fold `ground/fpga/` into `fpga/`; the Verilator emit (#89) becomes a target behind the interface via the Renode co-sim bridge.
5. **One Rust tree / clear roles.** Resolve `rust/awto_dji_core` vs `ground/rust`: core = protocol+DRC, ground = MAVLink client; no protocol copy in both.
6. **Full-system target.** Real firmware in Renode (#2) + FPGA co-sim, presented through the same interface — the #102 end state.

## Non-goals / keep
- Keep the DUML vs MAVLink **layering** (DUML app↔bird; MAVLink ground↔bridge) — one bridge translates; don't collapse them.
- Keep per-language clients; unify the **protocol** and the **target interface**, not the UIs.

## Decisions (Dan, 2026-11-10)
- **Canonical protocol:** reconcile the existing source-attributed `docs/data/` tables (+ version-matches JSON) into ONE versioned catalog, then generate the three bindings from it. Not promote-Dart, not author-new — the data already exists with source + version attribution.
- **First pass:** steps 1-2 only (canonical catalog + formalise `LinkTransport` as THE target interface). Tree merges + one-fake-bird come after.

## Open (smaller)
- Canonical catalog format: extend one of the existing TSVs, or a new JSON schema the TSVs feed?
- Codegen tool: one generator emitting Dart+Python+Rust, or per-language?
