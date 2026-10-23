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
| FPGA = just the datastream (control via GPIO + SPI register file, data via UART) | **partly corrected** — `m1400` also drives the FPGA over SPI0 with the same register protocol as the air MCU (`docs/ground-upgrade-path.md`); earlier "no SPI" was wrong. No datastream crypto found in either MCU |
| "Encrypt" in firmware = ATSHA204 component auth, not link crypto | **proven** — `m1400:0xf880` cluster; no AES/TEA in either MCU |
| WiMAX link params tracked + emitted as telemetry | **proven** — fmt `0x25abc`, reporter `0x256cc` |
| PHY params (AD9363 freq/BW/sample-rate) | **mostly recovered, partly inferred** — base profile is a static 2639-record script at `m0900:0x08016660` (not runtime-computed); AD9363 is behind the FPGA on SPI2. Registers verified: BBPLL x17.92, RFPLL N=121.1, 39-entry channel table (2404-2480 MHz, 2 MHz step). **Inferred:** Fref 40 MHz, sample rate 11.2 MHz, RF BW 10 MHz. **Open:** Fref confirmation, why RX BW ends at 0.625 MHz, run-time channel hop. Not yet confirmed by a real DUML session or SDR. Issue [#2](https://github.com/awto-au/awto-dji/issues/2); `docs/phy-params.md`, `docs/symbols/` |
| **Data is unencrypted OVER THE AIR** | **NOT proven** — MCU-layer cleartext ≠ air-layer; FPGA could encrypt. Needs an SDR capture. See `what-is-actually-secret.md` LAYER CAVEAT |

## Tooling status (what you need on Selwyn)

- **radare2** — used for all MCU disassembly (`-a arm -b 16 -m 0`). Ghidra would resolve
  ADR/xrefs far better; recommended for deeper tracing.
- **Project Mistral** (Cyclone-V bitstream RE) — was built in scratch; clone+build on Selwyn.
- **Renode** — **built from source + validated** in the cloud env (1.17.0, `--no-gui`, .NET 8).
  The emulation harness for the open PHY-params proof lives in `renode/` (custom STM32F103
  platform + AD9363 SPI-tap peripheral + capture/self-test scripts; see `renode/README.md`
  and `docs/phy-params.md`). To rebuild elsewhere: `./build.sh --no-gui` after installing
  `dotnet-sdk-8.0 libc6-dev libicu-dev gcc cmake python3`. Only the `m0900` firmware is still
  needed to run the actual capture.
- **SDR** (e.g. wideband 2.4 GHz) — **required** for the definitive over-the-air tests
  (encryption question + whitening/Berlekamp-Massey). Physical hardware.
- dji-firmware-tools (`dji_xv4_fwcon.py`) — to unpack firmware modules.

## DATA NOT IN THE REPO (important)

Firmware images, the Mistral build, and all unpacked/decompiled artifacts (routes/`.bt`,
`m2001_analysis/`, etc.) are **not committed** (binaries/licensing) — same ephemeral-scratch
rule as before, but acquisition is no longer a blocker: `docs/data-manifest.md` records every
input (source, version, size, **SHA-256**) so anyone can re-fetch byte-identical files. `m0900`
has been obtained + verified this way and is already running in Renode (see PHY-params row
above). To reproduce the rest on Selwyn:

1. Obtain the P3 firmware (`P3X_FW_V01.11.0020`) and the C1 RC firmware (`c1_*`) — DJI xV4
   containers. See `docs/data-manifest.md` for exact sources/hashes, `docs/code-provenance.md`
   / `docs/firmware-overview.md` for background.
2. Unpack with dji-firmware-tools `dji_xv4_fwcon.py` → per-module `.bin` (m0900 air STM32,
   m1400 ground LPC1765, m2000/m2001/m2002 ground FPGA images, etc.).
3. FPGA work: do NOT run Mistral on `m2001` (Cyclone III/IV-format, not Cyclone V; the earlier decode was noise, #114). `m1900`/`m2000`/`m2002` are Cyclone V but appear encrypted. See `docs/fpga-images.md`.

All the analysis docs cite exact offsets so you can re-derive against your own unpack.

## Next steps (prioritized)

1. **Capture DUML from your own aircraft** (usbmon on the ground USB, or the MCU UART at
   256000 8N1) and run `app/packages/duml/tool/telemetry_scan.dart` → read the live Master-ID,
   SN, and telemetry. Validate OSD fields against a DJI `.SRT` sidecar. *No hardware beyond a
   USB tap.* This unblocks the whole app-to-bird path.
2. **Extend the telemetry decoders** (battery `0x0b`, GPS, flight-status, home-point
   `0x03/0x44`, version/SN `0x00/0x01`) from the o-gs dji-firmware-tools dissector; mark each
   "confirm against capture".
3. **Find what gates AD9363 bring-up in `m0900`** — it boots in Renode but idles with zero
   SPI transactions; either disassemble its main loop/state machine, or inject a plausible
   DUML/GPIO stimulus and re-run. Tracked in
   [awto-au/awto-dji#2](https://github.com/awto-au/awto-dji/issues/2); detail + repro steps
   in `docs/phy-params.md`. Once it's talking to the AD9363, decode the capture vs UG-570 for
   exact freq/BW/sample-rate.
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

## Joining this work (person or agent)

The **repo is the join point**, not the chat. To pick this up correctly:

1. `git clone https://github.com/awto-au/awto-dji && cd awto-dji` (or `git pull` an existing
   clone). Everything is on **`main`**.
2. Read in order: `CLAUDE.md` (scope + safety + conventions) → `HANDOVER.md` (this file) →
   `docs/README.md` (doc index). Those give the full state; you do **not** need the chat.
3. Pick a task from "Next steps" above. The active one is
   [awto-au/awto-dji#2](https://github.com/awto-au/awto-dji/issues/2) (AD9363 bring-up
   trigger); `docs/renode-task.md` has the original harness-build task, now done.
4. Firmware/binaries are not in the repo — `docs/data-manifest.md` has every input with its
   SHA-256 so you can re-fetch and verify the exact files.

**Sessions driving this work (for the operator):**
- Main analysis session: `session_01KFSY3kZtDXknaxmmHkztxv` — resume at
  `https://claude.ai/code/session_01KFSY3kZtDXknaxmmHkztxv`.
- Spawned Renode task agent: `session_017yMpBMX7BGj3PyZtJHvThK` (building Renode from source,
  committing to `main`).

Commit messages carry a `Claude-Session:` footer linking history back to the session that
made each change. A new agent just works on `main` and pushes; the operator syncs other
machines (e.g. Selwyn `/mnt/2tb/git/awto-dji`) with `git pull`.
