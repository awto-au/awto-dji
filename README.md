# awto-dji

Interoperability software to talk to a **DJI Phantom 3 Professional directly** (app-to-bird),
for an aircraft the operator owns — a Flutter app with a pure-Dart DUML implementation (not
the DJI Cloud API), a Rust direct-control core, and the reverse-engineering analysis that
backs it.

## Start here

- **[CLAUDE.md](CLAUDE.md)** — agent/engineer onboarding: what this is, scope & safety, how to work.
- **[HANDOVER.md](HANDOVER.md)** — current state, what's proven vs open, tooling/data you need, next steps.
- **[docs/README.md](docs/README.md)** — index of the ~22 analysis docs.

## Layout

| Path | What |
|---|---|
| `app/packages/duml/` | pure-Dart DUML codec + `tool/telemetry_scan.dart` (telemetry / Master-ID scanner); tests pass |
| `app/packages/geofence/` | pure-Dart public-airspace safety gate (no-fly/altitude); tests pass |
| `rust/awto_dji_core/` | Rust direct-control core (protocol/client/DRC + FFI) |
| `ground/` | MAVLink ground-station clients (parked — app-to-bird first) |
| `docs/` | reverse-engineering analysis & plans |
| `scripts/` | protocol verification + FPGA netlist analysis |

## The model in one line

The P3 Lightbridge link is a WiMAX-family OFDM modem in an FPGA; the FPGA is just the
datastream engine, while IDs, pairing, telemetry and OSD live in the MCUs/app as **cleartext
DUML** (proven in `m1400` code) — the only real crypto is ATSHA204 component auth. Reading the
ID, reading telemetry, and app-to-bird control need no SDR. **Open:** exact PHY params (Renode
on `m0900`) and whether the link is encrypted over the air (needs an SDR capture — not ruled
out). See `HANDOVER.md`.

## Scope

Interoperability for an owned aircraft: no geofence defeat, no extraction of secret key
values, structural analysis only. See `CLAUDE.md`.

## License

GPL-3.0-only (see `LICENSE`). Analysis cites public sources (o-gs/dji-firmware-tools, ADI
UG-570, etc.); firmware/bitstream binaries are **not** included — see `HANDOVER.md`.
