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
- [camera-video-push.md](camera-video-push.md) - classic DJI GO camera recording settings from captured ShotParams/StateInfo pushes, field offsets, enums, model limits and remaining live comparison.
- [pc-video-preview.md](pc-video-preview.md) — corrected AOA envelope parsing, PC extraction/FFmpeg checks and saved-capture limitations; supersedes the earlier no-demux-header claim.
- `video-and-link.md` — what talks to the phone; OSD is client-rendered, not burned at the
  aircraft; video/telemetry mux; data-vs-burned-OSD tests.

## Firmware & hardware
- `firmware-overview.md`, `binary-analysis.md`, `kernel-analysis.md`, `code-provenance.md`,
  `license-compliance.md`.
- [standalone-lightbridge-ig800.md](standalone-lightbridge-ig800.md) — the retail
  standalone DJI Lightbridge (hardware family `IG800`, not the Phantom-3-integrated
  module): product history/specs from DJI's own hosted docs, full release version table,
  and firmware provenance - DJI itself never published firmware for it (confirmed from the
  Download Center's own JSON data); decrypted ground-decoder UBL/U-Boot/kernel and an
  encrypted final-version update package recovered from a 2016 forum thread instead;
  binaries in `../sources/lightbridge-ig800-firmware/`.
- `fpga-images.md`, `fpga-interfaces.md`, `fpga-emulation-plan.md`, `bitstream-to-verilog.md`,
  `m2001-decomp-findings.md` — FPGA bitstream RE. The earlier m2001 Mistral decode is void (#114); `fpga-images.md` has the family verdicts, `m1900`/`m2000`/`m2002` appear encrypted.

## RF / SDR / recovery strategy
- `minimal-recovery.md` — eliminate the complex FPGA; recover only the small DJI-specific bits.
- `alternative-approaches.md` — cheapest routes to the ID + whitening.
- `known-plaintext-plan.md` — all-0s / repetitive-telemetry known-plaintext for the scrambler.
- `rf-sdr-and-repair.md` — SDR tooling and RF notes.
- `lightbridge-phy-measured.md` — OFDM numerology, carrier map, pilots and frame timing measured from public DJI IQ captures (M100 = closest P3 proxy).
- `safety-geofence.md` — public-airspace geofence gate (safety, not defeat).

## Active task
- `renode-task.md` — **TASK**: build Renode from source, emulate `m0900`, capture the AD9363 config (closes the PHY-params open item).
- `phy-params.md` — result slot + capture method for the above. Tooling in `../renode/` is **built and validated**; the capture is blocked only on the `m0900` firmware image (not in repo).

## System data flow and buses (m0900-derived)
- `dataflow.md` — video / telemetry / control planes as Mermaid; where DUML is injected, forwarded, consumed in `m0900`; control + telemetry sequences; unknowns list. Every edge tagged verified / inferred / unknown.
- `board-connections.md` — P01007.06 connection diagram from firmware + wiki (**not a schematic**); what a real schematic would confirm.
- `fc-message-path.md` — m0306 (FC) message handling: it's AES-encrypted (decrypt with scripts/re/xv4_decrypt.py), its byte entry points (CAN1/2, USARTs), the DUML CRC16 validator, and why the (set,id) command map needs a Ghidra-scale trace next.
- `autonomy-onboard-plan.md` — architecture + safety plan for an onboard-Linux autonomy agent driving the stock FC with setpoints: component map, the verified-capture rule for control semantics, the watchdog/authority/geofence safety model, and the A–E work order.
- `linux-to-fc-path.md` — whether the camera A9 Linux and the DM368 Linux can reach the FC: yes, via netlink→rpmsg→camera RTOS DUML router (type 3 → UART ch0) or DM368 ttyS1; neither Linux originates FC traffic in stock firmware.
- `fpga-pinout-model.md` — each FPGA's external buses derived from the chips around it (FX2/FX3 slave-FIFO settings, m0900/m1400 SPI+GPIO, UART DUML, AD9363), with I/O estimates and how to confirm on hardware.
- `ground-fx3-m1601.md` — GL300C ground USB (Cypress FX3, `m1601`): iPhone iAP2 and Android AOA roles, DMA channels, the UART DUML session, and the `55 CC <type> <len>` RC->phone chunk header (`0x5749` DUML, `0x574A` video); tools `scripts/re/fx3_m1601.py`, `scripts/re/aoa_chunk_decode.py`.
- `m0800-dm368-provenance.md` — m0800 (air DM368) decrypted and compared with public TI DVSDK 4.02 / linuxutils / U-Boot / UBL / mainline 2.6.32.17 sources; what is unchanged TI code and what DJI modified (`scripts/re/ref_string_diff.py`).
- `m0900-can-channels.md` — the two CAN DUML links (0x412/0x413 camera/gimbal, 0x414/0x415 receiver type 30 only) and the correction that FC-type traffic goes out USART1, not CAN; `scripts/re/m0900_can_channels.py` asserts it.
- `data/m0900-buses.tsv` — clock tree, SPI2, USART1/2/3, CAN1 rates with arithmetic and code addresses; unused buses listed.

## Provenance
- `code-provenance.md`, `license-compliance.md`, `data-manifest.md` — the downloaded inputs (firmware/APK/tools) with SHA-256s; **none of the bytes are stored here** (copyright/size) — re-fetch + verify.
- `firmware-upgrade-log-review.md` — camera SD-card upgrade-log review (41 boot sessions); downgrade/equal-version-policy caveat for any "latest version" claim.
- [m0101-threadx-reversing.md](m0101-threadx-reversing.md) — `m0101` camera loader reversed from scratch: ARM Cortex-A9/ThreadX confirmed, full Ghidra pass, NAND partition map, SD-card firmware-update flow, cross-module link to `m0100`'s UEG layer, FPGA/switch-mux negative findings.
- `firmware-reference-versions.md` — per-module "latest known-good" table for `fw_version_check.py` (awto-dji#32): local firmware archive vs SD-log vs online sources, V/I confidence per module.

## Safety / scope
See `../CLAUDE.md` → "Scope & safety constraints". This is interoperability for an owned
aircraft: no geofence defeat, no extraction of secret key values, structural analysis only.
- [fpga-bringup.md](fpga-bringup.md): m0900 boot flow, board straps, FPGA GPIO lines, FPGA boot handshake
- [fpga-upgrade-path.md](fpga-upgrade-path.md): m0900 upgrade commands, FPGA update handshake, where the chip UID is sent
- [air-id-and-stream-survey.md](air-id-and-stream-survey.md): all air modules (+ P3S/P3C/P3SE/P3XW): FPGA-stream contact, chip/die ID reads, update-engine path (FX2LP, DM368, FPGA); symbols in `symbols/air_modules.tsv`
- [camera-linux-reversing.md](camera-linux-reversing.md): m0100 Linux userland binaries disassembled - `cam_server`'s command/control dispatcher, USB hotplug monitor (`lsusb` polling, not netlink), authorized-MAC-via-ARP check, FX2LP/Wi-Fi firmware-push paths, dev tooling (cipher test script, gdbserver, unauth'd SD-card HTTP listing), Linux-side `/proc/ambarella/uport` host/device switch; Ghidra project in `../re/ghidra-projects/cam_server_m0100.tar.gz`
- [ground-upgrade-path.md](ground-upgrade-path.md): C1 ground m1400 upgrade commands, loader marker, FPGA SPI0 path, LPC IAP chip UID, ground vs air; symbols in `symbols/c1_m1400.tsv`, tool `../scripts/re/mcu_trace.py`
- [fc-usb-port.md](fc-usb-port.md): aircraft front micro-USB (`fff0:0008`, CDC-ACM) to the STM32F427 flight controller: descriptors, VCOM/MSC modes in `m0306`, probe results (no reply yet), next steps; tools `../scripts/probe_fc_usb.py`, `../scripts/re/fc_usb_xrefs.py`
- [apk-analysis.md](apk-analysis.md): DJI GO 4 v4.3.64 APK: AOA/T600 link, DUML/cmd-set names, video path, upgrade/activation names; Java is packed (limits stated); data in `data/apk-duml-commands.tsv`, tool `../scripts/re/apk_extract.py`
- [fc-device-dll.md](fc-device-dll.md): DJI Assistant 2 For Phantom Windows native layer (`DJIDevice.dll`/`dataManager.dll`/`DJIServices/*.dll`): DUML CRC8/CRC16 constants confirmed byte-for-byte, cmdset-0 firmware-upgrade command IDs confirmed/new; data in `data/dll-duml-commands.tsv`
- [aoa-live-test-2026-10-23.md](aoa-live-test-2026-10-23.md): first real-hardware test of `awto_dji_app` against the RC's USB-A (phone) port via genuine AOA - real bytes flow, some frames pass CRC outright, confirms the raw stream is multiplexed (DUML + video/other); new debug TCP relay (`../app/awto_dji_app/lib/debug/tcp_relay.dart`, `../scripts/re/aoa_relay_server.py`) for fast native-Python decoder iteration
- [apk-vs-dissector-gap-report-2026-10-23.md](apk-vs-dissector-gap-report-2026-10-23.md): 723 real cmdset/cmdid facts from the dynamically-unpacked DJI GO 4 enum vs the public dissector - cmdset 10 (vision/EYE) badly under-documented upstream (49 missing IDs), a real JoyStick command-ID mismatch caught, firmware-upgrade and flight command sequences named; data in `data/apk-dynamic-cmdset-ids.tsv`, `data/cmdset-gap-report.tsv`, tools `../scripts/re/extract_apk_cmdset.py`, `../scripts/re/compare_cmdset_gaps.py`
- [known-telemetry-and-commands.md](known-telemetry-and-commands.md): current-state reference - which of the 723 catalogued commands actually have a working decoder/send-struct today vs name-only; keep this updated, don't let it go stale
- [dji-app-protocol-pipeline.md](dji-app-protocol-pipeline.md): pipeline for decompiling other DJI apps and diffing their DUML commands against ones already confirmed - what's automated (`../scripts/re/apk_memscan.py`, `extract_duml_classes.py`, `compare_duml_apps.py`) vs what needs the operator (consent/sign-in click-through); candidate app list; known regex-extractor limitation (decompile-style noise, not real protocol differences) validated against dji.go.v4 vs dji.pilot
