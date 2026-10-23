# Documentation index

Analysis and planning docs for the awto-dji project (talking to a DJI Phantom 3 Professional
directly, for a device the operator owns). Grouped by topic; start with `../HANDOVER.md` for
the current state and next steps, and `../CLAUDE.md` for agent onboarding.

## Protocol & control plane (the practical path)
- `protocol-verification.md` — DUML wire format verified byte-exact against a real packet.
- `control-plane-re.md` — reverse the MCU control plane, not the FPGA; external corroboration.
- `cpu-reversing-proof.md` — **the proofs in MCU code** (binding-ID handler, role machine,
  ATSHA204=auth, WiMAX telemetry); status table of each claim.
- `id-entry-point.md` — where/how the Master-ID enters the FPGA (MCU GPIO control, UART data).
- `link-security.md` — pairing by ID, scrambler≠cipher, the "nothing hidden" principle.
- `what-is-actually-secret.md` — 3-tier secrecy inventory; **LAYER CAVEAT** (MCU-layer
  cleartext is not over-the-air proof).

## Telemetry & video
- `video-and-link.md` — what talks to the phone; OSD is client-rendered, not burned at the
  aircraft; video/telemetry mux; data-vs-burned-OSD tests.

## Firmware & hardware
- `firmware-overview.md`, `binary-analysis.md`, `kernel-analysis.md`, `code-provenance.md`,
  `license-compliance.md`.
- `fpga-images.md`, `fpga-interfaces.md`, `fpga-emulation-plan.md`, `bitstream-to-verilog.md`,
  `m2001-decomp-findings.md` — FPGA bitstream RE (Mistral); the decode gaps.

## RF / SDR / recovery strategy
- `minimal-recovery.md` — eliminate the complex FPGA; recover only the small DJI-specific bits.
- `alternative-approaches.md` — cheapest routes to the ID + whitening.
- `known-plaintext-plan.md` — all-0s / repetitive-telemetry known-plaintext for the scrambler.
- `rf-sdr-and-repair.md` — SDR tooling and RF notes.
- `safety-geofence.md` — public-airspace geofence gate (safety, not defeat).

## Active task
- `renode-task.md` — **TASK**: build Renode from source, emulate `m0900`, capture the AD9363 config (closes the PHY-params open item).
- `phy-params.md` — result slot + capture method for the above. Tooling in `../renode/` is **built and validated**; the capture is blocked only on the `m0900` firmware image (not in repo).

## System data flow and buses (m0900-derived)
- `dataflow.md` — video / telemetry / control planes as Mermaid; where DUML is injected, forwarded, consumed in `m0900`; control + telemetry sequences; unknowns list. Every edge tagged verified / inferred / unknown.
- `board-connections.md` — P01007.06 connection diagram from firmware + wiki (**not a schematic**); what a real schematic would confirm.
- `data/m0900-buses.tsv` — clock tree, SPI2, USART1/2/3, CAN1 rates with arithmetic and code addresses; unused buses listed.

## Provenance
- `code-provenance.md`, `license-compliance.md`, `data-manifest.md` — the downloaded inputs (firmware/APK/tools) with SHA-256s; **none of the bytes are stored here** (copyright/size) — re-fetch + verify.

## Safety / scope
See `../CLAUDE.md` → "Scope & safety constraints". This is interoperability for an owned
aircraft: no geofence defeat, no extraction of secret key values, structural analysis only.
- [fpga-bringup.md](fpga-bringup.md): m0900 boot flow, board straps, FPGA GPIO lines, FPGA boot handshake
- [fpga-upgrade-path.md](fpga-upgrade-path.md): m0900 upgrade commands, FPGA update handshake, where the chip UID is sent
- [air-id-and-stream-survey.md](air-id-and-stream-survey.md): all air modules (+ P3S/P3C/P3SE/P3XW): FPGA-stream contact, chip/die ID reads, update-engine path (FX2LP, DM368, FPGA); symbols in `symbols/air_modules.tsv`
- [ground-upgrade-path.md](ground-upgrade-path.md): C1 ground m1400 upgrade commands, loader marker, FPGA SPI0 path, LPC IAP chip UID, ground vs air; symbols in `symbols/c1_m1400.tsv`, tool `../scripts/re/mcu_trace.py`
- [fc-usb-port.md](fc-usb-port.md): aircraft front micro-USB (`fff0:0008`, CDC-ACM) to the STM32F427 flight controller: descriptors, VCOM/MSC modes in `m0306`, probe results (no reply yet), next steps; tools `../scripts/probe_fc_usb.py`, `../scripts/re/fc_usb_xrefs.py`
- [apk-analysis.md](apk-analysis.md): DJI GO 4 v4.3.64 APK: AOA/T600 link, DUML/cmd-set names, video path, upgrade/activation names; Java is packed (limits stated); data in `data/apk-duml-commands.tsv`, tool `../scripts/re/apk_extract.py`
- [fc-device-dll.md](fc-device-dll.md): DJI Assistant 2 For Phantom Windows native layer (`DJIDevice.dll`/`dataManager.dll`/`DJIServices/*.dll`): DUML CRC8/CRC16 constants confirmed byte-for-byte, cmdset-0 firmware-upgrade command IDs confirmed/new; data in `data/dll-duml-commands.tsv`
