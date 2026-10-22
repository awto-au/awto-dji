# Handover — state of work & next steps

This is the pick-up point for another agent/engineer (e.g. on the Selwyn machine). It says
what is built, what is proven vs open, what tooling/data you need, and the prioritized next
steps. Read `CLAUDE.md` first for scope/safety and conventions, then `docs/README.md`.

## Goal

Software to talk to a **DJI Phantom 3 Professional directly** (app-to-bird), for an aircraft
the operator owns — a Flutter app + pure-Dart DUML, not the DJI Cloud API. Interoperability
only (see safety scope in `CLAUDE.md`).

## What is built (code)

| Path | What | State |
|---|---|---|
| `app/packages/duml/` | pure-Dart DUML codec (CRCs, packet, framer) + **telemetry scanner** (`tool/telemetry_scan.dart`) that surfaces the Master-ID/SN and decodes OSD from a capture | tests pass (14) |
| `app/packages/geofence/` | pure-Dart public-airspace safety gate (no-fly/altitude) | tests pass (9) |
| `rust/awto_dji_core/` | Rust direct-control core (protocol/client/DRC + FFI for Flutter) | builds |
| `ground/python`, `ground/rust` | MAVLink ground-station clients | PARKED (app-to-bird first) |

Dart SDK: a bundled one was used from a Flutter checkout in scratch; install Flutter/Dart on
Selwyn to run `dart test` / `dart run`.

## What is established (model) and how solid it is

The link is **non-secret at the data layer**; the FPGA is just the modem (datastream engine);
the ID and telemetry are **cleartext DUML**; the whitening is (almost certainly) the standard
WiMAX scrambler. Proven in MCU code on the ground side:

| Claim | Status |
|---|---|
| ID is CPU-placed cleartext data | **proven in code** — Connected Master Id Set `m1400:0x2bca` / Get `0x2b10`, cleartext DUML ↔ RAM `0x100005e8`; dispatch `0x5c76`→`0x56e4`; role machine `0x9bd0` |
| FPGA = just the datastream (GPIO control, UART data, no SPI) | **proven** on `m1400`; corroborated by o-gs teardown |
| "Encrypt" in firmware = ATSHA204 component auth, not link crypto | **proven** — `m1400:0xf880` cluster; no AES/TEA in either MCU |
| WiMAX link params tracked + emitted as telemetry | **proven** — fmt `0x25abc`, reporter `0x256cc` |
| PHY params (AD9363 freq/BW/sample-rate) | **open** — config is runtime-computed; needs Renode capture on `m0900` |
| **Data is unencrypted OVER THE AIR** | **NOT proven** — MCU-layer cleartext ≠ air-layer; FPGA could encrypt. Needs an SDR capture. See `what-is-actually-secret.md` LAYER CAVEAT |

## Tooling status (what you need on Selwyn)

- **radare2** — used for all MCU disassembly (`-a arm -b 16 -m 0`). Ghidra would resolve
  ADR/xrefs far better; recommended for deeper tracing.
- **Project Mistral** (Cyclone-V bitstream RE) — was built in scratch; clone+build on Selwyn.
- **Renode** — NOT available in the cloud env; **required** to emulate `m0900` and capture the
  AD9363 SPI config (the open PHY-params proof). Install on Selwyn.
- **SDR** (e.g. wideband 2.4 GHz) — **required** for the definitive over-the-air tests
  (encryption question + whitening/Berlekamp-Massey). Physical hardware.
- dji-firmware-tools (`dji_xv4_fwcon.py`) — to unpack firmware modules.

## DATA NOT IN THE REPO (important)

Firmware images, the Mistral build, and all unpacked/decompiled artifacts (routes/`.bt`,
`m2001_analysis/`, etc.) lived in the cloud container's **ephemeral scratch** and are **not**
committed (binaries/licensing). To reproduce on Selwyn:

1. Obtain the P3 firmware (`P3X_FW_V01.11.0020`) and the C1 RC firmware (`c1_*`) — DJI xV4
   containers. See `docs/code-provenance.md` / `docs/firmware-overview.md`.
2. Unpack with dji-firmware-tools `dji_xv4_fwcon.py` → per-module `.bin` (m0900 air STM32,
   m1400 ground LPC1765, m2001 ground Cyclone-V FPGA, etc.).
3. For FPGA work: de-pack `m2001` and run Mistral (`mistral-cv decomp 5CEBA4U19C8 m2001.depack.bin out.bt`).

All the analysis docs cite exact offsets so you can re-derive against your own unpack.

## Next steps (prioritized)

1. **Capture DUML from your own aircraft** (usbmon on the ground USB, or the MCU UART at
   256000 8N1) and run `app/packages/duml/tool/telemetry_scan.dart` → read the live Master-ID,
   SN, and telemetry. Validate OSD fields against a DJI `.SRT` sidecar. *No hardware beyond a
   USB tap.* This unblocks the whole app-to-bird path.
2. **Extend the telemetry decoders** (battery `0x0b`, GPS, flight-status, home-point
   `0x03/0x44`, version/SN `0x00/0x01`) from the o-gs dji-firmware-tools dissector; mark each
   "confirm against capture".
3. **Renode-emulate `m0900`** to capture the AD9363 SPI register writes → decode vs UG-570 →
   exact freq/BW/sample-rate (closes the PHY-params item).
4. **Over-the-air SDR capture** → (a) settle the air-encryption question, (b) run
   Berlekamp-Massey on an all-0s / repetitive-telemetry capture to recover the scrambler
   (`known-plaintext-plan.md`, `alternative-approaches.md`).
5. Build out the Flutter app-to-bird UI on top of `app/packages/duml` + `rust/awto_dji_core`.

## Reproduce the key MCU proofs (with your own `c1_m1400.bin`)

```
r2 -a arm -b 16 -m 0 -qq -c 'pd 48 @ 0x56d8' c1_m1400.bin   # RC cmd_id dispatch
r2 -a arm -b 16 -m 0 -qq -c 'pd 40 @ 0x2bca' c1_m1400.bin   # Connected Master Id SET
r2 -a arm -b 16 -m 0 -qq -c 'pd 36 @ 0x2b10' c1_m1400.bin   # Connected Master Id GET
r2 -a arm -b 16 -m 0 -qq -c 'pd 85 @ 0x9bd0' c1_m1400.bin   # role state machine
```
