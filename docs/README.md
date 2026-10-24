# Documentation index

Analysis and planning docs for the awto-dji project (talking to a DJI Phantom 3 Professional
directly, for a device the operator owns). Grouped by topic; start with `../HANDOVER.md` for
the current state and next steps, and `../CLAUDE.md` for agent onboarding.

## Protocol & control plane (the practical path)
- [usb-test-matrix.md](usb-test-matrix.md) — per-port bench evidence, open USB tests, and a cached-descriptor watcher for cable/power correlation.
- [fx3-usb-modes.md](fx3-usb-modes.md) — ground USB firmware's alternate bulk interfaces, GPIO/configuration mode selection, and the currently verified PC serial path; PC bulk access remains unverified.
- [duml-protection.md](duml-protection.md) — separates APK SIMPLE XOR, ATSHA204 component authentication, RC master/slave connection and unresolved aircraft-radio protection; traces the XOR inputs.
- `protocol-verification.md` — DUML wire format verified byte-exact against a real packet.
- `control-plane-re.md` — reverse the MCU control plane, not the FPGA; external corroboration.
- `cpu-reversing-proof.md` — **the proofs in MCU code** (binding-ID handler, role machine,
  ATSHA204=auth, WiMAX telemetry); status table of each claim.
- `id-entry-point.md` — where/how the Master-ID enters the FPGA (MCU GPIO control, UART data).
- `link-security.md` — pairing by ID, scrambler≠cipher, the "nothing hidden" principle.
- `what-is-actually-secret.md` — 3-tier secrecy inventory; **LAYER CAVEAT** (MCU-layer
  cleartext is not over-the-air proof).

- `usb-tools-test-2026-10-23.md` — Windows USB tooling test: no DJI PC tool for the P3; Assistant 2 rejects it; dji-firmware-tools reads the controller; capture + decoder.
- `p3-usb-observations-2026-10-23.md` — what the P3 controller and aircraft do on USB: line settings, DUML replies, the aircraft's one-way log stream, DTR/RTS sensitivity.

## Telemetry & video
- [pc-video-preview.md](pc-video-preview.md) — corrected AOA envelope parsing, PC extraction/FFmpeg checks and saved-capture limitations; supersedes the earlier no-demux-header claim.
- `video-and-link.md` — what talks to the phone; OSD is client-rendered, not burned at the
  aircraft; video/telemetry mux; data-vs-burned-OSD tests.

## Firmware & hardware
- `firmware-overview.md`, `binary-analysis.md`, `kernel-analysis.md`, `code-provenance.md`,
  `license-compliance.md`.
- `fpga-images.md`, `fpga-interfaces.md`, `fpga-emulation-plan.md`, `bitstream-to-verilog.md`,
  `m2001-decomp-findings.md` — FPGA bitstream RE. The earlier m2001 Mistral decode is void (#114); `fpga-images.md` has the family verdicts, `m1900`/`m2000`/`m2002` appear encrypted.

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
- `m0900-can-channels.md` — the two CAN DUML links (0x412/0x413 camera/gimbal, 0x414/0x415 receiver type 30 only) and the correction that FC-type traffic goes out USART1, not CAN; `scripts/re/m0900_can_channels.py` asserts it.
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
- [aoa-live-test-2026-10-23.md](aoa-live-test-2026-10-23.md): first real-hardware test of `awto_dji_app` against the RC's USB-A (phone) port via genuine AOA - real bytes flow, some frames pass CRC outright, confirms the raw stream is multiplexed (DUML + video/other); new debug TCP relay (`../app/awto_dji_app/lib/debug/tcp_relay.dart`, `../scripts/re/aoa_relay_server.py`) for fast native-Python decoder iteration
- [apk-vs-dissector-gap-report-2026-10-23.md](apk-vs-dissector-gap-report-2026-10-23.md): 723 real cmdset/cmdid facts from the dynamically-unpacked DJI GO 4 enum vs the public dissector - cmdset 10 (vision/EYE) badly under-documented upstream (49 missing IDs), a real JoyStick command-ID mismatch caught, firmware-upgrade and flight command sequences named; data in `data/apk-dynamic-cmdset-ids.tsv`, `data/cmdset-gap-report.tsv`, tools `../scripts/re/extract_apk_cmdset.py`, `../scripts/re/compare_cmdset_gaps.py`
- [known-telemetry-and-commands.md](known-telemetry-and-commands.md): current-state reference - which of the 723 catalogued commands actually have a working decoder/send-struct today vs name-only; keep this updated, don't let it go stale
- [dji-app-protocol-pipeline.md](dji-app-protocol-pipeline.md): pipeline for decompiling other DJI apps and diffing their DUML commands against ones already confirmed - what's automated (`../scripts/re/apk_memscan.py`, `extract_duml_classes.py`, `compare_duml_apps.py`) vs what needs the operator (consent/sign-in click-through); candidate app list; known regex-extractor limitation (decompile-style noise, not real protocol differences) validated against dji.go.v4 vs dji.pilot
