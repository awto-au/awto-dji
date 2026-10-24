# Air side survey: FPGA-stream contact, chip/die ID reads, upgrade path

Firmware: `P3X_FW_V01.11.0020` (2017-07-05) plus P3X 01.01.0006, P3S 01.01.0008, P3C 01.08.0100, P3SE 01.01.0000, P3XW 01.00.0010.
Reproduce: `python3 scripts/re/air_survey.py` (log `tmp/logs/air_survey.log`, about 1 minute). Symbols: `docs/symbols/air_modules.tsv`.
Scope (CLAUDE.md): interoperability only. No key values read, no auth/signing bypass, no flight-restriction work. Firmware treated as untrusted data (static analysis only).
Tags: **V** verified in bytes/code (address cited), **I** inferred, **U** unknown.
Ground side (C1/m1400) is a separate survey: not covered here.

## Module table (P3X V01.11.0020)

Addresses: Cortex-M modules = runtime address; m0100 sys = runtime address (base `0x0E600000`); m1500 = 8051 code address; others = file offset.

| Module | Role | Arch (basis) | FPGA-stream contact | Chip/die ID read | Upgrade-path role | Evidence |
|---|---|---|---|---|---|---|
| m0100 (55 MB) | camera, Ambarella A9SE | container: sys RTOS 8.9 MB, lnx Linux 3.8.0 4.8 MB, rfs UBIFS 26 MB, rom_fw 11 MB, dsp_fw 3.7 MB (V: amba_fwpak) | **yes (I for FPGA end)**: USB host driver `68013.ko` to the FX2LP, DM368 stream control, rpmsg video/update channels | **yes, not a chip UID**: ATSHA204 SN + board-number check vs A9 NAND copy; SD-card SN logged; authorized-MAC list. No FPGA/Cyclone ID read | **orchestrator** (UEG): checks packet, sends every module's image | see "m0100" below |
| m0101 | camera loader (SD updater) | ARM Cortex-A9, ThreadX/IAR (V: string `0x64be4`) | no | no | SD-card updater: CRC32 check, model-name check (`0x4ce4`), NAND program, reboot | strings `0x4c5c-0x5fe4` |
| m0305 | A3 FC loader | Cortex-M (STM32F4 by option-byte address) linked at `0x20000000` (I: base), SP `0x1000e4e8` | no | no UID/IDCODE. Reads option byte `0x1FFFC001` into RAM (`0x20007d0c`): protection state (V) | loader for m0306 | const scan |
| m0306 | A3 flight controller | Cortex-M4 STM32F4, base `0x08020000` | no (reaches m0900 over CAN per dataflow.md) | **yes**: STM32F4 UID read `0x0808527a`; word 0 used in a 10-byte record built at `0x080596ea` (callers `0x08059798`, `0x08059b3e`). Strings: `m8 uid not received` (`0x0802867b`), `IMU SN ERROR`, `[set uuid]` | updated via DUML | disasm (V structure, U consumer) |
| m0400 | gimbal | Cortex-M STM32 base `0x08008000` | no | no UID literal. Get-Version-like handler `0x08016254` reads flash page `0x080C0000` (outside image) | updated via DUML | table `0x0801d4ac` ids 1,7,8 |
| m0800 | video encoder, DaVinci DM368 Linux | `Salted__` openssl 3DES blob with the publicly documented packaging password, **decrypted 2026-10-24** (`m0800-dm368-provenance.md`) | **unknown** (strongly suspected: stream source, see "Stream path") | unknown | target of UEG fw-id 12 (DUML Update Transmit) | header bytes |
| m0900 | Lightbridge MCU, STM32F103 | Cortex-M3 base `0x08008000` | **yes**: SPI2 FPGA regs, USART3 DUML, upgrade handshake (fpga-bringup.md, fpga-upgrade-path.md) | **yes**: STM32 UID `0x080127be`, DUML request `0x0904` -> reply `0x0954`. No FPGA ID read | handles Enter Loader/Confirm/Finish for receiver 0x13; no Update Transmit handler | existing docs; const scan agrees |
| m1100 / m1101 | battery 1 / 2 | non-ARM; m1100 likely TI MSP430 (I: `31 40` = `mov #imm,SP`) | no | unknown (not disassembled) | DUML target | arch scan |
| m1200-m1203 | ESC 0-3 (identical bytes, sha256 `940e4dd1c38f`) | not identified (U) | no | unknown | DUML target | arch scan |
| m1500 | **FX2LP firmware** "IG810 LB2_68013_TX" (2.7 KB) | Cypress FX2LP 8051 `.iic` (V) | **yes, direct**: synchronous slave-FIFO bridge, see "m1500" | **no**: no REVID (`0xE60A`) or I2C/EEPROM regs; descriptor `iSerialNumber=0` | loaded into RAM by A9 Linux via `fxload`; UEG fw-id 11, USB transfer | 8051 image decode |
| m1700 | vision module, camera MCU | Cortex-M base `0x0800C000` (I: best string-pointer fit) | no | camera-module ID only (`Camera ID`, `Factory: sunny/chicony/foxconn`, `EFL`), not MCU UID | DUML target | strings `0x75b-0x7f9` |
| m1701 | vision module, sonar | Cortex-M base 0 | no | no | DUML target | const scan |
| m1900 | air FPGA container (4 MiB, 2.06 MB used) | FPGA bitstream, compressed, no MCU code | is the stream engine (I) | see "m1900" | target of UEG fw-id 10 | mistral-cv |

## m0100 (camera SoC)

### Stream-related (a)
- V: Linux modules `68013.ko` (alias `usb:v0547p1002`, `usb_bulk_msg` writes, netlink message thread) and `rpmsg_trans.ko` (channels `dji_app`, `dji_sock`, `dji_usbdrv`, `dji_test`; files `/tmp/update_data`, `/tmp/video_data`). Loaded by `/usr/local/share/script/usersetting_s2.sh`.
- V: `cam_server` reads the FX2LP version from `/sys/bus/usb/devices/1-1/manufacturer` with format `enc V%u.%u.%u.%u`; `m1500` carries the manufacturer string `enc V1.1.2.0` (8051 `0x862`). Same VID/PID `0547:1002` in `68013.ko`, `cam_server` (`fxload -t fx2 -d 0547:1002`) and the m1500 device descriptor (`0x800`).
- V: `cam_server`/`viz_tracking` receive H.264 / liveview-YUV buffer addresses from the RTOS (`recv h264 codec addr`, `/dev/mem`) and serve them over UDT. This is the phone-over-Wi-Fi/USB-net path, not the Lightbridge path (I).
- V: RTOS strings `dm368 68013 unlink!` (sys `0x55ac0`), `DjiAgingIfDM368Ok: 68013 unlink 368` (`0x55e94`), test help `connect usb to A9 / connect usb to DM368` (`0x76fd4`), `DjiMsgStUsbSwitchStatusSet` (`0x0e844980`), `DjiUegDm368StreamControl` (`0x0e8423d0`).
- I: the FX2LP USB port is switched between the A9 (control, firmware load) and the DM368 (video). DM368 side not checkable (encrypted).

### Upgrade engine (UEG) (c)
- V: firmware table `0x0edba638`, 33 entries x `0xBC`. Entry fields: `+0x00` id, `+0x84` receiver type, `+0x88` index; path string at `+0x42` (`P<name>Fw3.bin`).
- V: ids/receivers from the table: 1765 id 9 -> type 9 (m0900); **FPGA id 10 -> type 19 (0x13)**; **68013 id 11 -> type 15**; DM368 id 12 -> type 8; gimbal id 13 -> 4; camera loader id 15 -> type 1 index 1. Confirms the receiver numbering used in fpga-upgrade-path.md (name table at `0x0e6712b4`, type = index + 1).
- V: step functions per entry: version, entry, confirm, transmit, finish, reboot. Transmit cell: `DjiUegFwMsgTransmitSend` (`0x0e89e018`, generic DUML) for 15 entries including **FPGA (cell sys file `0x7bae34`)**; `DjiUegFwUsbTransmitSend` (`0x0e89ec48`) only for 68013 (cell `0x7baef0`).
- V: handlers named `DjiUegFpgaFinishHandle` (`0x0e8998a8`) and `DjiUegFpgaCleanUpHandle` (`0x0e8a00e8`) are table cells of the **68013** entry (wrapper passes id 0xb), not the FPGA entry. Cleanup restarts DM368 streaming (retry 20 x 500 ms, string `Start Streaming Fail!`), sets USB switch, writes A9 GPIO pair `0x30/0x2f` (role U).
- I: UEG step names map to DUML 0x0f check / 0x07 Enter Loader / 0x08 Confirm / 0x09 Transmit / 0x0a Finish / 0x0b Reboot (firmware-overview.md table).
- V: checks before sending: packet header MagicCode / Manufacturer / ProductName / version triple (`0x0e8a7dd8`), per-file CRC and MD5, "rotating motors" refusal, "Author Level Is Low", SD card SN printed in log lines (`0x80788`). No chip-unique ID is sent to any module in these strings.
- U: how the FPGA-addressed (type 19) Update Transmit packets leave the camera. Camera DUML channels: `DjiMsgChannelInit` (`0x0e861988`) = UART channels + IPC channel; route table for type 19 not traced. m0900 has no Transmit handler and drops type 19 (fpga-upgrade-path.md).

### ID-related code (b)
- V: ATSHA204 (I2C) provisioning and check: `DjiEncryptInit` `0x0e871e94`, `DjiEncryptCheckA9Mac` `0x0e871ae0`, `DjiEncryptCheckSN` `0x0e8731cc`, `DjiEncryptSaveBothToSha204AndA9` `0x0e872740`, `DjiEncryptWriteAllBoardNumToOTP` `0x0e871140`. 9-byte ATSHA204 SN and a board number are compared with a copy in A9 NAND. Shell tests `t dji encrypt ...` exist. No key or SN value recorded here.
- V: `DjiMsgAuthorizedMac` `0x0e85f370`; `cam_server` rejects clients whose MAC is not authorized.
- V: Ambarella DSP microcode (`dsp_fw` partition) has `check_sc() ... chip_id ... efuse` log strings: SoC-internal ucode/chip match, not exported by DJI code (I). No DJI string reads an A9 unique ID.
- V: `cam_server` embeds a hard-coded FTP credential for `192.168.1.2` (Wi-Fi module firmware upload). Value deliberately not copied.
- Not found: any `fpga`/`altera`/`cyclone`/`jtag`/`idcode`/`spidev`/`uio` string in the Linux kernel partition or rootfs; no FPGA config or `.rbf`/`.sof` handling in m0100.

## m1500 (FX2LP, 8051)
- V: load records at `0x80`, `0x47f`, `0x87e` (2620 B), 5 vector stubs, final `CPUCS` write releasing reset.
- V register writes (immediates at 8051 `0x00a9`, `0x012f`, `0x0145`, `0x01f2`, `0x0208`): `IFCONFIG=0x03` (slave FIFO, synchronous, external IFCLK); `EP2CFG=0xA0` (bulk OUT 512 B quad); `EP6CFG=0xE0` (bulk IN 512 B quad); `EP2FIFOCFG=0x10` (AUTOOUT); `EP6FIFOCFG=0x08` (AUTOIN). EP1/EP4/EP8 invalidated.
- Meaning (V decode, I for peer): USB bulk OUT on EP2 lands in the slave FIFO for an external master; the external master's data written to EP6 goes out as bulk IN. A transparent USB<->FIFO bridge. The FIFO master is the FPGA per the wiki-sourced pads in fpga-interfaces.md (I).
- V: no ID content: descriptor has no serial string, no REVID read, no I2C/EEPROM register use. Device descriptor VID 0x0547 PID 0x1002.
- The `.iic` header carries PID 0x2131 (boot-time ID); runtime ID is 0x1002 (descriptor).

## m1900 (air FPGA)
- V: 4 MiB container, `0xFF` padding, used span `0x80..0x1f6ec9`, entropy 7.98; no readable strings.
- V: `mistral-cv routes` on the depacked payload gives exactly one CHIPID-related route in each of: P3X m1900, P3S m1900, ground m2001 (valid-die control): `TCLK/TDMUX -> CTRL.000.004:CLOCK_CHIPID`. The same CTRL block lines (`CLOCK_PR`, `CLOCK_RU`, `CLOCK_SPI`, `CLOCK_CRC`, `CLOCK_OPREG`, `TCKCORE`) appear in the same decodes, so this is the baseline control-block clock set, not evidence of a user chip-ID IP.
- V: no `SHIFTNLD_CHIPID` or `REG_OUT_CHIPID` route in any of the three decodes.
- Weak negative: air die is unidentified (fpga-images.md, issue #3), `routes2` reports 29,660 unresolved vs 29,796 resolved routes for the air image under 5CEFA4U19I7. Absence of chip-ID logic cannot be proven from this file.

## Cross-check of other Phantom 3 variants
| Variant | Air modules present | Result vs P3X V01.11.0020 |
|---|---|---|
| P3X 01.01.0006, P3S 01.01.0008 | m0100..m1900 incl. m1500, m1900 | m1500 byte-identical to P3X 0020. m1900 identical between these two, differs from 0020. m0100 sys has UEG USB/68013/ATSHA204 strings (names `DjiUegFpgaFinishHandle`, `MCCTRL_68013Update`, `DjiEncryptSaveBothToSha204AndA9`). Older table layout (no `P*Fw3.bin` strings). `DjiMsgAuthorizedMac` absent. m0900 (01.07.x) has **no UID literal**; m0306 (02.01.1543) has **no UID literal** |
| P3C 01.08.0100 | no m1500 / m1900 (Wi-Fi: m0700/m2700, ath9k Linux) | m0100 rootfs is the same as P3X (still carries `68013.ko`, `fxload`, `Vend_Ax.iic`), UEG table identical layout: code presence is not hardware presence. m0900, m0306 (02.04.5148): no UID literal. m0305 identical |
| P3SE 01.01.0000 | Wi-Fi, no m1500 / m1900 | m0100 not splittable by `amba_fwpak`; raw scan: `DjiUegFpgaFinishHandle` x1, `FPGA.A` x1, `MCCTRL_68013Update` x0 (differs from P3C). m0700/m2700 gunzip to Linux/ath9k, no FPGA/ID hits |
| P3XW 01.00.0010 | Wi-Fi, no m1500 / m1900 | m0100 same layout as P3X incl. authorized-MAC and fw table; m0900/m0306 no UID literal |
| P3XS RC 01.03.0020 | RC only (m1300, m1400, m1600, m1601, m2000-m2002) | no air modules; not used |

UID-read summary across variants: STM32 UID literals exist only in P3X V01.11.0020 `m0900` and `m0306` among the images checked.

## Summary

### (a) Code touching the FPGA data stream (video/telemetry/control through the air FPGA and radio)
- **m1500 (FX2LP)**: yes, V. Slave-FIFO bridge with bulk EP2 OUT / EP6 IN, auto-commit. Strongest evidence of a payload path. FIFO peer = FPGA is I.
- **m0100**: yes. `68013.ko` + `rpmsg_trans.ko` + `cam_server` carry data/commands to the FX2LP over USB; RTOS controls DM368 streaming around updates (V).
- **m0900**: yes (existing docs): SPI2 register/AD9363 access, USART3 DUML, FPGA handshakes.
- **m0800 (DM368)**: now decrypted (`m0800-dm368-provenance.md`). V: TI DVSDK 4.02 DM368 stack plus DJI `encode_usb`, which runs as USB host to a CY7C68013A (`usb_68013.ko`, USB `0547:1002`). V: raw H.264 Annex-B slices leave over USB bulk EP2 with no header (`m0800-dm368-provenance.md` §7).
- m0306, m0400, m1100/m1101, m1200-m1203, m1700/m1701, m0101, m0305: no FPGA contact found.
- I: aircraft video chain is DM368 -> USB -> FX2LP (m1500) -> slave FIFO -> FPGA -> AD9363. Not proven end to end.

### (b) Code that could identify the chip or die
- **m0900**: STM32F103 96-bit UID via DUML `0x0904` -> `0x0954` (V).
- **m0306**: STM32F4 UID word 0 inside a 10-byte record (`0x080596ea`); GPS M8 UID expected (`0x0802867b`); IMU SN; user UUID (V strings, U consumers).
- **m0100**: ATSHA204 SN (9 bytes) and board number verified against A9 NAND; SD-card SN; authorized MAC. Not an SoC or FPGA UID.
- **m1700**: camera-module ID, not a chip UID.
- **FPGA / Cyclone V**: no code anywhere reads the FPGA die ID, JTAG IDCODE or eFuse. Only FPGA values read are regs 0x08/0x09 in the upgrade check (fpga-upgrade-path.md). Bitstream shows no user chip-ID block (weak, see m1900).
- m1500: none. m0400: none (reads a flash page, meaning U). ESC/battery: unknown.

### (c) Firmware-upgrade path reaching the FPGA or sending an ID
- V: UEG in m0100 runs per module: version, entry, confirm, transmit, finish, reboot. **FPGA = fw-id 10, receiver 0x13, generic DUML transmit.** FX2LP = fw-id 11, USB transmit. m0900 = fw-id 9.
- V: m0900 handles Enter Loader / Confirm / Finish for receiver 0x13 with SPI handshakes (fpga-upgrade-path.md); it has no Update Transmit handler and drops type 0x13.
- U: the path of the FPGA image bytes after the camera. Candidates: DUML over a camera UART to m0900 (but m0900 drops type 0x13), or DUML-over-USB through the FX2LP (I, unproven). Needs the camera's route table or a bus capture.
- V: no chip UID, FPGA ID or aircraft serial appears in the UEG steps; identifiers checked are packet Manufacturer/ProductName/version, file CRC/MD5, SD-card SN (log only). m0900 sends its UID only on request `0x0904`.
- V: the FX2LP image is loaded into RAM with `fxload` (Vend_Ax loader, then the SD-card image) by `cam_server`; no persistent copy needed.

## Not checkable here
- **m0800** (DM368 Linux): decrypted with the static packaging password documented by dji-firmware-tools; provenance and DJI changes are in `m0800-dm368-provenance.md`. The component-auth parts (`setsecurity`, `at88.c`, `/etc/key.bin`) were inventoried, not analysed (no keys). Earlier note: encrypted; decrypting was thought to need key material. Stream source, ID checks and its half of the "encrypt query" with the camera are therefore unknown. Reference only: `dm3xx_encode_usb_hardcoder.py` docstring says the binary sends an encrypt request to the camera and compares the result.
- **m1900** content: no MCU code; decode quality too low (unidentified die) to prove absence of chip-ID logic or locate the DUML/FIFO ports.
- **m0900 bootloader** (`0x08000000-0x08007FFF`), A3 and camera bootloaders: not in the modules.
- **Camera DUML route** for receiver 19 (`DjiMsgChannelInit` `0x0e861988` onwards) and fw-id gating in `DjiUegFwUpdateById` (`0x0e8a3fec`): not decompiled.
- **Consumers** of the m0306 10-byte record and of the m0400 flash page `0x080C0000`.
- **Linux userland** (`cam_server`, `rpc_trans`, `util_svc`): strings only, no disassembly. `rom_fw` and `dsp_fw` partitions: strings only.
- **ESC (m1200-m1203), battery (m1100/m1101)**: architecture not confirmed (MSP430 for m1100 is I); no disassembler available here.
- **P3SE m0100** cannot be split by `amba_fwpak`; **Wi-Fi modules** m0700/m2700 (ath9k Linux) not analysed beyond keyword strings.
- **Hardware facts**: FIFO peer of the FX2LP, USB mux topology, which board strap the owned unit has: need a schematic or logic-analyzer capture.
- **DUML Get Version (0x01) / Query Device Info (0xFF) replies** traced for m0900 only (existing docs); candidate General-set tables found by heuristic scan: m0400 `0x0801d4ac`, m0305 `0x2000a390`, m0306 `0x080baa60`; reply contents not decoded.

## DJI GO 4 APK: checklist (not on disk, nothing downloaded)
- Class/package names: upgrade (`Upgrade`, `Firmware`, `FwUpdate`), version/device info (`GetVersion`, `DeviceInfo`, `DeviceState`), activation (`Active`, `Activation`, `RealName`), module-id tables with `FPGA`, `68013`, `DM368`, `1765`.
- Native libs: DUML pack/unpack, upgrade-packet builder (`Fw3.bin` naming, `P3X_FW_V%d.%d.%d.bin`), any AES/CRC on upgrade packets.
- Upgrade flow: which command sets the app sends (0x00 general: 0x07..0x0d), whether it pushes the package over DUML/USB or only copies it to the SD card, what it logs from `PushUpgradeStatus`.
- Activation flow: what the app sends to the aircraft (UUID / real-name, `[set uuid]` in m0306) and to DJI servers; whether any chip UID is included.
- Server-side JSON for firmware lists (module ids, MD5, rollback fields).
