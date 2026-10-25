# Documentation index

Analysis and planning docs for the awto-dji project (talking to a DJI Phantom 3 Professional
directly, for a device the operator owns). Grouped by topic; start with `../HANDOVER.md` for
the current state and next steps, and `../CLAUDE.md` for agent onboarding.

**`SAFETY.md`** — the single source for all safety, flight-gating, geofence/NFZ, RF-power and
repair-scope rules. Technical docs link here and do not repeat them. **`HISTORY.md`** — dated log
of fact-changes (docs state current facts only).

## Protocol & control plane (the practical path)
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
- `video-and-link.md` — what talks to the phone; OSD is client-rendered, not burned at the
  aircraft; video/telemetry mux; data-vs-burned-OSD tests.

## Firmware & hardware
- `firmware-overview.md`, `binary-analysis.md`, `kernel-analysis.md`, `code-provenance.md`,
  `license-compliance.md`.
- `fpga-images.md`, `fpga-interfaces.md`, `bitstream-to-verilog.md` — FPGA bitstream RE.
  `fpga-images.md` has the family verdicts and per-chip emulator availability; `m1900`/`m2000`/`m2002` appear encrypted. The earlier m2001 Mistral decode is void (#114): retired to `debris/m2001-decomp-findings.md`, `debris/fpga-emulation-plan.md`.
- `fpga-air-vs-ground.md` — which FPGA image is air vs ground: m1900 = air, m2000/01/02 = ground, V at package + MCU-routing + DJI's own in-firmware `FPGA.A`/`FPGA.G` name table; open sub-questions (#9 board role, which rev per RC, m2001 family) + a cheapest-first prove-it plan.

## RF / SDR / recovery strategy
- `minimal-recovery.md` — eliminate the complex FPGA; recover only the small DJI-specific bits.
- `alternative-approaches.md` — cheapest routes to the ID + whitening.
- `known-plaintext-plan.md` — all-0s / repetitive-telemetry known-plaintext for the scrambler.
- `rf-sdr-and-repair.md` — SDR tooling and RF notes.

## Active task
- `renode-task.md` — **TASK**: build Renode from source, emulate `m0900`, capture the AD9363 config (closes the PHY-params open item).
- `phy-params.md` — result slot + capture method for the above. Tooling in `../renode/` is **built and validated**; the capture is blocked only on the `m0900` firmware image (not in repo).

- `prior-art.md` — positioning vs existing DJI RE (o-gs/dji-firmware-tools): what we reuse (extraction, decryption, the param-table/defaults dump = `dji_flyc_param_ed.py`), what's new here (SPL ID, I/O pin map, control-authority, sim/RC-loss, Linux→FC, FPGA), and that upstream already ships an `m0306` symbol map worth cross-checking (GPL-3.0, compatible).
- `stm32-reversing-process.md` — the repeatable STM32 checklist (Ghidra, SVD, SPL/HAL/LL ID, string-anchored naming, param tables) distilled from reversing m0306.
- `lpc-reversing-process.md` — the NXP/LPC parallel (m1400): what's the same (xV4, string-anchoring, V/I/U), what's different (no DJI AES wrapper, LPCOpen/IAP not SPL, legacy-SPI0 gotcha, no Ghidra project built yet), and the open SVD/tooling gaps.

## System data flow and buses (m0900-derived)
- `naming-map.md` — **adopted** canonical names for every module (`side_role_chip`, e.g. `air_fc_stm32f427`, `air_router_stm32f103`, `gnd_fx3_cyusb2014`) and bus (`medium_side_roleA_roleB`, e.g. `uart_air_router_fc`, `can_air_primary`), each tagged V/I/U.
- `dataflow.md` — video / telemetry / control planes as Mermaid; where DUML is injected, forwarded, consumed in `m0900`; control + telemetry sequences; unknowns list. Every edge tagged verified / inferred / unknown.
- `board-connections.md` — P01007.06 connection diagram from firmware + wiki (**not a schematic**); what a real schematic would confirm.
- `fc-message-path.md` — m0306 (FC) message handling: it's AES-encrypted (decrypt with scripts/re/xv4_decrypt.py), its byte entry points (CAN1/2, USARTs), the DUML CRC16 validator, and why the (set,id) command map needs a Ghidra-scale trace next.
- `data/m0306-param-defaults.tsv` — all 834 FlycExportParam fields with flash min/max/default (`scripts/re/fc_param_table.py --defaults`): bauds, flight limits, failsafe actions, SDK/API control profile.
- `fc-replacement-plan.md` — plan for a clean-room replacement FC app the stock loader will accept (no signature; loader preserved = low brick risk), whose first job is a DUML read_memory command to dump the resident bootloader; components (STM32 HAL + FreeRTOS + operator framework + ported DUML + CAN PD0/PD1), an FC Sim built first, acceptance checklist (0x77557755 marker), and a motors-off/no-flight safety gate.
- `security-and-activation.md` — consolidated reference for the distinct gates: DJI product activation (the real firmware motor gate, DJI-software-driven), ATSHA204 component auth (anti-counterfeit crypto MAC, on-device but demonstrated effect = client authorization by Ethernet MAC; flight-block unverified), device identity (UID/SN), firmware integrity (no signature), and RF link (unkeyed). Summary table of what each gates and whether it is a hardware or DJI-software block.
- `fc-auth-enforcement-trace.md` — traces what the FC activation check and the A9 ATSHA204 MAC/SN checks' callers do on failure (issue #45): FC activation is a true motor-start block (V, addresses re-derived for V01.11.0020); the A9 MAC/SN check gates ≥1 on-device A9 feature (I/U which), with no path found to the FC or flight/boot.
- `atsha204-repair-note.md` — repair note for a failed ATSHA204 component-auth chip on an owned board: what it is (anti-counterfeit SHA-256 component auth; primary on the camera/A9 m0100 via DjiEncryptCheckA9Mac/CheckSN vs the A9 NAND copy, also on the RC m1400 get_mac/sha204p_*; not safety/regulatory/link-encryption), and the stub process (replace the chip, or patch the get_mac-result branch since the firmware has no signature). Dual-use/safety caveats noted.
- `fc-bootloader.md` — m0306 FC boot/upgrade: a separate factory-fixed "Loader" (app at 0x08020000 leaves 128KB loader region; no loader in the OTA package), the DUML cmdset-0 streamed-reflash protocol (RequestUpgrade→TranslateData→RestartDevice, flash erase/write/CRC result codes), and the app is single-image but the decompiled RAM updater m0305 has two-slot validate+boot logic and bank2 awareness (A/B-capable at the loader level); m0305 is a full RAM-resident flash driver + option-byte writer + DUML-over-CAN receiver.
- `fc-io-inventory.md` — m0306 FC I/O + software inventory: STM32F427 peripheral usage (TIM2 µs time-base, CAN1/2 inter-MCU link, UARTs/SPIs/I2C, USB_OTG_HS, FSMC), sensors (MPU-6500 IMU, HMC5883/IST8303 compass, baro, GPS), and software identity (µC/OS-III, DJI own `hal_*` not ST HAL, FDI-AHRS fusion, no open-source FC code). Reproduce with `scripts/re/fc_io_inventory.py`.
- `autonomy-onboard-plan.md` — architecture + safety plan for an onboard-Linux autonomy agent driving the stock FC with setpoints: component map, the verified-capture rule for control semantics, the watchdog/authority/geofence safety model, and the A–E work order.
- `linux-to-fc-path.md` — whether the camera A9 Linux and the DM368 Linux can reach the FC: yes, via netlink→rpmsg→camera RTOS DUML router (type 3 → UART ch0) or DM368 ttyS1; neither Linux originates FC traffic in stock firmware.
- `fpga-pinout-model.md` — each FPGA's external buses derived from the chips around it (FX2/FX3 slave-FIFO settings, m0900/m1400 SPI+GPIO, UART DUML, AD9363), with I/O estimates and how to confirm on hardware.
- `ground-fx3-m1601.md` — GL300C ground USB (Cypress FX3, `m1601`): iPhone iAP2 and Android AOA roles, DMA channels, the UART DUML session, and the `55 CC <type> <len>` RC->phone chunk header (`0x5749` DUML, `0x574A` video); tools `scripts/re/fx3_m1601.py`, `scripts/re/aoa_chunk_decode.py`.
- `m0800-dm368-provenance.md` — m0800 (air DM368) decrypted and compared with public TI DVSDK 4.02 / linuxutils / U-Boot / UBL / mainline 2.6.32.17 sources; what is unchanged TI code and what DJI modified (`scripts/re/ref_string_diff.py`).
- `m0900-can-channels.md` — the two CAN DUML links (0x412/0x413 camera/gimbal, 0x414/0x415 receiver type 30 only) and the correction that FC-type traffic goes out USART1, not CAN; `scripts/re/m0900_can_channels.py` asserts it.
- `data/m0900-buses.tsv` — clock tree, SPI2, USART1/2/3, CAN1 rates with arithmetic and code addresses; unused buses listed.

## Provenance
- `code-provenance.md`, `license-compliance.md`, `data-manifest.md` — the downloaded inputs (firmware/APK/tools) with SHA-256s; **none of the bytes are stored here** (copyright/size) — re-fetch + verify.

## Upgrade paths, USB ports & app protocol
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
