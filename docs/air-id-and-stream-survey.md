# Air side survey: FPGA-stream contact, chip/die ID reads, upgrade path

> **APK evidence correction, 2026-10-25:** the firmware-address findings below
> are independent of app identity. The old GO 4 checklist is superseded by analysis
> of classic GO 3.1.8; see the [2026-10-25 P3 evidence audit](dji-go-p3-evidence-audit-2026-10-25.md).
> Searches that found no FPGA ID reader are bounded negatives, not proof that no
> component or protocol path can read one.

Firmware: `P3X_FW_V01.11.0020` (2017-07-05) plus P3X 01.01.0006, P3S 01.01.0008, P3C 01.08.0100, P3SE 01.01.0000, P3XW 01.00.0010.
Reproduce: `python3 scripts/re/air_survey.py` (log `tmp/logs/air_survey.log`, about 1 minute). Symbols: `docs/symbols/air_modules.tsv`.
Scope (CLAUDE.md): interoperability only. No key values read, no auth/signing bypass, no flight-restriction work. Firmware treated as untrusted data (static analysis only).
Tags: **V** verified in bytes/code (address cited), **I** inferred, **U** unknown.
Ground side (C1/m1400) is a separate survey: not covered here.

## Module table (P3X V01.11.0020)

Addresses: Cortex-M modules = runtime address; m0100 sys = runtime address (base `0x0E600000`); m1500 = 8051 code address; others = file offset.

| Module | Role | Arch (basis) | FPGA-stream contact | Chip/die ID read | Upgrade-path role | **Flash-writer (issue #43)** | Evidence |
|---|---|---|---|---|---|---|---|
| m0100 (55 MB) | camera, Ambarella A9SE | container: sys RTOS 8.9 MB, lnx Linux 3.8.0 4.8 MB, rfs UBIFS 26 MB, rom_fw 11 MB, dsp_fw 3.7 MB (V: amba_fwpak) | **yes (I for FPGA end)**: USB host driver `68013.ko` to the FX2LP, DM368 stream control, rpmsg video/update channels | **yes, not a chip UID**: ATSHA204 SN + board-number check vs A9 NAND copy; SD-card SN logged; authorized-MAC list. No FPGA/Cyclone ID read | **orchestrator** (UEG): checks packet, sends every module's image | not itself (I) — hands off to `m0101` via the shared `DjiUeg*`/`DjiUec*` NAND-meta flag (`CamLdrEntry`/`CamAppEntry`/`CamBstEntry` strings in `m0100` match `m0101`'s own role); see "Flash-writer consolidation" | see "m0100" below |
| m0101 | camera loader (SD updater) | ARM Cortex-A9, ThreadX/IAR (V: string `0x64be4`) | no | no | SD-card updater: CRC32 check, model-name check (`0x4ce4`), NAND program, reboot | **itself (V)** — `AmbaNAND_Program`/`AmbaNFTL_ErasePart`, full NAND incl. Bootstrap/Bootloader/System Software/Linux Kernel/RootFS (`m0101-threadx-reversing.md` §2/§7) | strings `0x4c5c-0x5fe4` |
| m0305 | A3 FC loader | Cortex-M (STM32F4 by option-byte address) linked at `0x20000000` (I: base), SP `0x1000e4e8` | no | no UID/IDCODE. Reads option byte `0x1FFFC001` into RAM (`0x20007d0c`): protection state (V) | loader for m0306 | **itself (I)**, well-supported: "reads as a flash programmer, not a jump/VTOR target" (`fc-usb-duml.md` adversarial re-check #1 — zero `SCB->VTOR` hits, flash-sector-boundary table at file offset `0xa4ac`); writes `m0306`'s app flash | const scan |
| m0306 | A3 flight controller | Cortex-M4 STM32F4, base `0x08020000` | no (reaches m0900 over CAN per dataflow.md) | **yes**: STM32F4 UID read `0x0808527a`; word 0 used in a 10-byte record built at `0x080596ea` (callers `0x08059798`, `0x08059b3e`). Strings: `m8 uid not received` (`0x0802867b`), `IMU SN ERROR`, `[set uuid]` | updated via DUML | **not itself (U)**: no app-level Enter Loader/Confirm/Transmit/Finish dispatch found for receiver FLYC/self in any pass to date — genuine gap, not assumed. Real write = `m0305` (I, see above) | disasm (V structure, U consumer) |
| m0400 | gimbal | STM32F4 family (V), base `0x08008000` | no | no UID or DBGMCU read. Set 0x00 id 0x01 handler `0x08016254` reads 2 words at flash `0x080C0000` (code V, contents U, outside image) | updated via DUML | **unknown (U), genuine gap**: cmd ids `0x07-0x0d` in the "general" cmd-set — which numerically match the Enter Loader/Confirm/Transmit/Finish/Reboot convention used by `m0900`/`m1400` — are confirmed (full 27/27 Ghidra decode) to be ordinary param-get/trim/ack handlers in this build, **not** update handlers. No marker-write/IAP code and no separate loader module (unlike `m0101`/`m0305`) found for gimbal. Real-world SD log (`firmware-upgrade-log-review.md`) shows `[04 00]` version changes with "successful rewrite" during real UEG sessions — so it does happen; the mechanism is simply not visible in this static image | DUML table `0x0801d46c`, 27 entries, see "m0400 gimbal" |
| m0800 | video encoder, DaVinci **DM365** Linux (TMS320DM368 only on WM610/Inspire — `docs/camera-linux-console-access.md` "Correction" 2026-10-25) | `Salted__` openssl blob, **decrypted 2026-10-25** (`openssl enc -d -des3 -md md5 -k Dji123456`, password published by `o-gs/dji-firmware-tools` wiki, reproduced via `scripts/re/m0800_decrypt.py`) | **unknown** (strongly suspected: stream source, see "Stream path") | unknown | target of UEG fw-id 12 (DUML Update Transmit) | **now V, not U**: decrypted tree is TI DaVinci UBL/u-boot/uImage partitions (`dji/data/ubl_*.img`, `u-boot.img`, `uImage`) plus NAND flash-writer scripts `dji/etc/updatestart`/`updatefinish`, which select the right `ubl_<freq>m` clock variant and write partitions on its own Linux kernel under its own flash-writer tools (`dji/bin/mtdwritefile`/`mtderase`) — the `m0100`/`m0101`-split analogy was correct, now confirmed rather than inferred. Still routed as generic DUML Update Transmit over channel 2 (UART, 115200) by the camera's route table | `docs/camera-linux-console-access.md` "m0800 decrypted" |
| m0900 | Lightbridge MCU, STM32F103 | Cortex-M3 base `0x08008000` | **yes**: SPI2 FPGA regs, USART3 DUML, upgrade handshake (fpga-bringup.md, fpga-upgrade-path.md) | **yes**: STM32 UID `0x080127be`, DUML request `0x0904` -> reply `0x0954`. No FPGA ID read | handles Enter Loader/Confirm/Finish for receiver 0x13; no Update Transmit handler | **partial self (V/I)**: receiver-9 (self) Enter Loader writes IAP marker `OOXX` to flash `0x7400` (V, real flash write, but of a marker not the app image) then presumably reboots into the un-dumped bootloader for the actual app reflash (I/U). Receiver 0x13 (FPGA): never receives Update Transmit; writer unknown — **issue #18, unchanged, the one confirmed gap** | existing docs; const scan agrees |
| m1100 / m1101 | battery 1 / 2 | non-ARM; m1100 likely TI MSP430 (I: `31 40` = `mov #imm,SP`) | no | unknown (not disassembled) | DUML target | **unknown (U)** — no new trace found this pass; no battery firmware image identifiable in the container, nothing to disassemble | arch scan |
| m1200-m1203 | ESC 0-3 (identical bytes, sha256 `940e4dd1c38f`) | **TI TMS320F28027F "Piccolo" C2000 DSP + DRV8301 pre-driver (W, public corroboration — `o-gs/dji-firmware-tools` wiki via `dataflow.md` §7.9 / `fc-usb-port.md`)**, not this repo's own RE | no | unknown | DUML target | **unknown (U/I)** — chip now identified by public source, not firmware trace; no ESC firmware image is identifiable among this container's own module files (the UEG table has an ESC fw-id, but no disassemblable binary for it was found locally), so the write path can't be traced in code. **Real-world confirmation it happens**: the camera's own SD upgrade log (`firmware-upgrade-log-review.md`) records a completed session rewriting all four ESCs `[12 00-03]` (1.13.0.0 -> 1.11.0.0) with packet-level success. Control bus is shared UART3 + PWM1-4 (not CAN/DUML-relay at the ESC chip itself — W, same source) — if the ESC chip takes DUML-framed update bytes at all, the FC (`m0306`) must be the relay (I, architecturally consistent, not traced); the C2000's own on-chip flash would then be written via its standard SCI ROM bootloader (I, by TI-part-family analogy, not DJI-code-confirmed) | arch scan |
| m1500 | **FX2LP firmware** "IG810 LB2_68013_TX" (2.7 KB) | Cypress FX2LP 8051 `.iic` (V) | **yes, direct, full-disassembly verified (issue #31)**: synchronous slave-FIFO bridge, core never touches FIFO payload memory, see "m1500" | **no**: no REVID (`0xE60A`) or I2C/EEPROM regs; descriptor `iSerialNumber=0` | loaded into RAM by A9 Linux via `fxload`; UEG fw-id 11, USB transfer | **none (V)** — RAM-loaded via `fxload` every boot, never persisted to any flash; not a flash-write target at all | full Ghidra 8051 disassembly (32 funcs, 1353 instrs) |
| m1700 | vision module, camera MCU | Cortex-M base `0x0800C000` (I: best string-pointer fit) | no | camera-module ID only (`Camera ID`, `Factory: sunny/chicony/foxconn`, `EFL`), not MCU UID | DUML target | **unknown (U)** — no new trace found this pass | strings `0x75b-0x7f9` |
| m1701 | vision module, sonar | Cortex-M base 0 | no | no | DUML target | **unknown (U)** — no new trace found this pass | const scan |
| m1900 | air FPGA container (4 MiB, 2.06 MB used) | FPGA bitstream, compressed, no MCU code | is the stream engine (I) | see "m1900" | target of UEG fw-id 10 | **unknown (U) — issue #18, the one confirmed gap, deliberately not papered over.** `m0900` excluded (no data path, too small), `m0100`/A9 excluded (USB-only, no SPI/JTAG/config-pin driver), `m1500` excluded (full-disassembly-verified transparent FIFO pipe). Only remaining candidate is FPGA-resident logic receiving the FX2LP's FIFO output and writing its own config memory — plausible, not confirmed | mistral-cv |

## Flash-writer consolidation (issue #43)

Consolidates, cross-references and extends the piecemeal findings above into one
answer per module: which chip/code path performs the **actual nonvolatile write**,
not "receives a DUML Confirm/Finish ack". Ground-side equivalent table:
`ground-upgrade-path.md` "Flash-writer consolidation (issue #43, ground side)".
Does not re-litigate issue #18 (FPGA config-flash writer) — restated as still open.

### Two confirmed self-flash patterns among the Cortex-M modules

- **`m0900` (STM32F103) and `m1400` (LPC1765, ground, see `ground-upgrade-path.md`)
  both self-flash a *marker*, not the new image, from their own app code (V for
  both):** `m0900` Enter Loader (receiver 9) writes `OOXX` to flash `0x7400`
  (`fpga-upgrade-path.md`); `m1400` Enter Loader (receiver 0x0E) writes
  `0x55AA66CC`/`~0x55AA66CC` to flash sector 8 via real IAP erase(52)+program(51)
  calls (`ground-upgrade-path.md` "Loader marker and reboot-to-loader"). Both then
  stop feeding the watchdog and reset. **Neither app ever handles Update Transmit
  (0x09)** — confirmed absent from both dispatch tables. The actual new-image write
  is therefore **inferred to happen in the bootloader** (flash below the app base,
  `0x08000000-0x08007FFF` for `m0900`, `0x0000-0x9FFF` for `m1400`) — **neither
  bootloader is in the container**, so this is I, not V, for both chips. This is
  the same shape repeated on two independent chip families (STM32 and LPC17xx),
  which is itself evidence it's DJI's standard self-update convention, not a
  one-off.
- **`m0306` (FC) and the camera (`m0100`/`m0101`) instead use a *separate loader
  module*, not self-flash-via-marker:** `m0305` ("A3 FC loader") is a distinct
  STM32F4 image, structurally confirmed as a flash programmer (`fc-usb-duml.md`'s
  adversarial re-check: zero `SCB->VTOR` hits in either `m0306` or `m0305`, and
  `m0305`'s only `0x08020000`-valued literal sits inside an F42x flash-sector
  table, not a vector-relocation target) — it is inferred (I, well-supported) to
  be the actual writer of `m0306`'s app flash, analogous to how `m0101` is the
  confirmed (V) NAND writer underneath `m0100`'s UEG orchestration layer. In
  neither case does the "app" module (`m0306`, `m0100`) write its own flash
  directly — the separate loader does.
- **`m0400` (gimbal) fits neither pattern, and this is a genuine new negative
  result, not a gap in search effort:** the full 27/27-entry DUML dispatch decode
  (`m0400` section below) shows cmd ids `0x07`-`0x0d` of the "general" cmd-set —
  which numerically match the Enter-Loader/Confirm/Transmit/Finish/Reboot
  convention used by `m0900` and `m1400` — are ordinary parameter-get, trim-byte
  and plain-ack handlers in this build, not update handlers. No IAP/marker-write
  code and no separate `m04xx`-loader module exist in the container for the
  gimbal. Yet the camera's own historical SD-card upgrade log
  (`firmware-upgrade-log-review.md`) shows `[04 00]` (gimbal) version changes with
  packet-level success in real completed update sessions — so the gimbal
  genuinely does get reflashed by the real hardware; the code path that does it is
  simply not present/found in this app image (candidates: an un-dumped gimbal
  bootloader by analogy with `m0900`/`m1400`, or cmd ids assigned differently than
  the numeric convention suggests — neither confirmed). Stated as U, not guessed.

### `m0800` (DM368): delivery path traced without decrypting contents

Connects `air-id-and-stream-survey.md`'s own UEG routing table to its own DUML
channel-init trace (both already in this file, never cross-referenced against each
other before this pass):
- V (UEG table, "Upgrade engine" above): DM368 is a distinct UEG fw-id entry,
  Update Transmit for it uses the **generic DUML transmit** cell
  (`DjiUegFwMsgTransmitSend`, `0x0e89e018`, frame `[u8][u32 idx][u16 len][data]`) —
  not the USB/IPC path used for FPGA and 68013 (`fpga-write-path.md`'s correction:
  those two use `DjiUegFwUsbTransmitSend`).
- V (camera route table `0x0e861cc4`/`0x0e861ce4`, `fpga-write-path.md` §1):
  receiver type 8 (DM368) resolves to **channel 2**, a UART channel
  (`DjiMsgChannelInit`, first config word `0x1c200`, I: 115200 baud) — the same
  channel type 15 (68013.A) also uses for its DUML handshake (Enter
  Loader/Confirm/Finish; its bulk data still goes over USB/IPC separately).
- **Conclusion (I, from connecting the two V findings above, not independently
  re-verified against a capture):** `m0800`'s update package is staged by `m0100`'s
  UEG (parsed off the SD card, MD5-checked like every other module — see
  "Upgrade engine (UEG)" above) and delivered to the DM368 as plain DUML Update
  Transmit frames over a dedicated UART at ch2 — **not** over USB/IPC like the FPGA
  and 68013 paths. This is new: no earlier pass connected the UEG transmit-cell
  choice to the DUML channel-routing table for this specific module.
- U, and stays U: what DM368 does with the bytes once received (its own flash/NAND
  write, success confirmation back to the camera) — the module is ciphertext
  (`Salted__`, 7.99995 bits/byte entropy, `camera-linux-console-access.md`), so
  the receiving/writing code cannot be read. DM368 is itself a Linux-class SoC
  (`video-and-link.md`), so a split comparable to `m0100`(orchestrator)/`m0101`
  (NAND writer) is plausible inside it — not verifiable without the key.

### ESC (`m1200`-`m1203`): chip identified, write path not traceable in this container

- The chip is now known: **TI TMS320F28027F "Piccolo" C2000 DSP + DRV8301
  pre-driver** — **W, public corroboration** (`o-gs/dji-firmware-tools` wiki, via
  `dataflow.md` §7.9 and `fc-usb-port.md`), not this repo's own disassembly (the
  four ESC images in the container are byte-identical and architecturally
  unidentified, sha256 `940e4dd1c38f`). Control is shared UART3 + PWM1-4, not a
  CAN/DUML-relay endpoint on the ESC chip itself (same W source).
- No ESC firmware image distinguishable from the generic container blob was found
  to disassemble, so the actual flash-write code cannot be traced here — stated
  plainly rather than guessed at.
- **What is confirmed, empirically, not from code:** the camera's own historical SD
  upgrade log (`firmware-upgrade-log-review.md`) records a completed real-hardware
  session that rewrote all four ESCs (`[12 00-03]`, 1.13.0.0 -> 1.11.0.0) with
  packet-level success — the UEG mechanism really does reach and reflash the ESCs,
  whatever the exact code path. If the ESC chip receives DUML-framed bytes at all,
  the flight controller (`m0306`) is the only plausible relay (I, architecturally
  consistent with the UART3 wiring, not traced in code); the C2000 would then write
  its own flash via its standard SCI ROM bootloader (I, by TI C2000-family
  convention, not DJI-code-confirmed — no ESC image to check).

### Not re-litigated here

- **Issue #18 (air FPGA config-flash writer): still open.** `m0900` is excluded (no
  data path, too small, SPI2 handshake-only), `m0100`/A9 is excluded (USB bulk only,
  no SPI/JTAG/config-pin driver anywhere in the Linux kernel or rootfs), `m1500` is
  excluded (full 8051 disassembly, zero FIFO-memory touches). Only remaining
  candidate is FPGA-resident logic consuming its own FIFO input — plausible, not
  confirmed. Ground side has the structurally identical open gap for
  `m2000`-`m2002` (see `ground-upgrade-path.md`).
- **Issue #19 (no P3-aircraft firmware-push engine in the vendor APK) / issue #30
  (APK may be the wrong app for a P3 Pro):** consistent with everything above —
  every transmit/confirm/finish step traced in this section lives entirely in the
  aircraft's own `m0100` UEG + per-module app/loader code, driven by an SD-card
  file or a DUML session from whatever app is actually paired to this product;
  nothing here required a P3-specific push engine inside the single APK already
  examined, so its absence there doesn't indicate a missing mechanism on the
  aircraft side. Not independently re-investigated this pass.

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
- V: handlers named `DjiUegFpgaFinishHandle` (`0x0e8998a8`) and `DjiUegFpgaCleanUpHandle` (`0x0e8a00e8`) are table cells of the **68013** entry (wrapper passes id 0xb), not the FPGA entry. Cleanup restarts DM368 streaming (retry 20 x 500 ms, string `Start Streaming Fail!`), sets USB switch, writes A9 GPIO pair `0x30/0x2f`.
- V (issue #25, `scripts/re/usb_switch_trace.py`, `tmp/logs/usb_switch_trace.log`): GPIO pair `0x30`/`0x2f` role resolved — `0x0e80cb18(mode)` is the actual mux driver, writing `(mode!=0)` to both Ambarella GPIO pins via the pin-validated setter `0x0e7cdbc8` (pin id range check `<0xa1`, consistent with Ambarella's own GPIO-ID space, not a raw register address). All 6 call sites of `0x0e80cb18` are immediately followed by a call to `DjiMsgStUsbSwitchStatusSet` with the same `mode` — that function is just a mutex-protected status flag (global byte `0xef96b75`), not the driver. The umbrella caller is `DjiCmmDownloadModeCtrl` (`0x0e815164`, own string), which also stops/starts DM368 streaming (`DjiUegDm368StreamControl`) and sets a "download mode" work flag (`0x11841921`, logged as `pbWorkModeInDownload1`). `mode=1` = A9/USB-host side (used by the FPGA-update prep call at `0x0e89db04`, fw-id `0xb` gate); `mode=0` = DM368 side (used by the FPGA-update cleanup call at `0x0e8a0190`). `MCCTRL_SetUsbMode`/`MCCTRL_UsbModeSw`/`MCCTRL_UsbModLoad` (`0x0e8dd078`/`0x0e8dcf50`/`0x0e8dcfe4`) are a **separate** mechanism — they send a 4-byte message via an IPC-style queue call (`0x0e913864`) to insert/remove the A9's *own* USB host-mode driver (for the A9 to act as USB host towards the FX2LP during FPGA transfer), not a GPIO write.
- U: whether the camera-side DUML catalog name `SwitchUSB` (cmdset `0x02`/cmdid `0x04`, receiver CAMERA, also `GetUSB` cmdid `0x06`; `scripts/re/duml_catalog.py`) is wired to `DjiCmmDownloadModeCtrl` — no literal-pool/data-table reference to that function, `0x0e80cb18`, `DjiMsgStUsbSwitchStatusSet`, or `MCCTRL_SetUsbMode` was found anywhere in the sys image (checked exhaustively, not just near the known call sites); every caller found is a direct `bl` from the `t dji pano` shell handler, the FPGA-update prep/cleanup path, or two internal retry/poll loops. Not proven unreachable from DUML, just not found wired to a dispatch table in this build.
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

Full Ghidra disassembly pass (issue #31), not just the literal-byte scan below.
Reproduce: `python3 scripts/re/m1500_fx2_disasm.py` (log `tmp/logs/m1500_fx2_disasm.log`,
~4 s). Loads the `.iic` code records (addresses `0x0`,`0xb`,`0x33`,`0x43`,`0x53`,`0x80`,
`0x47f`,`0x87e`, 2748 B total) as a flat binary into Ghidra's native `8051:BE:16:default`
processor (`support/analyzeHeadless`; 8051 scripting needs PyGhidra, not present in this
Ghidra 12.2 DEV build, so the post-script is Java: `scripts/re/ghidra/Dump8051.java`),
recursively disassembles from the 5 vectors, and creates functions at every `LCALL`
target: 32 functions, 1353 instructions, covering the full 2748 B image (no dead code
found by flow-following from the entry points).

- V: load records at `0x80`, `0x47f`, `0x87e` (2620 B contiguous, `0x80..0xabc`), 5 vector
  stubs (`0x0`,`0xb`,`0x33`,`0x43`,`0x53` — each a 3-byte `LJMP`, matching FX2's reset +
  T0 + RESUME + USB + I2C/INT4 autovector slots), final `CPUCS` (`0xE600`) 1-byte write
  releasing reset (the one `.iic` record at `0xE600`, outside CODE space — a post-load
  boot-ROM poke, not 8051-executed code).
- V register writes (immediates at 8051 `0x00a9`, `0x012f`, `0x0145`, `0x01f2`, `0x0208`,
  confirmed by Ghidra disassembly, not just byte literals): `IFCONFIG=0x03` (slave FIFO,
  synchronous, external IFCLK); `EP2CFG=0xA0` (bulk OUT 512 B quad); `EP6CFG=0xE0` (bulk
  IN 512 B quad); `EP2FIFOCFG=0x10` (AUTOOUT); `EP6FIFOCFG=0x08` (AUTOIN). EP1/EP4/EP8
  invalidated (`EP1OUTCFG`/`EP1INCFG`/`EP4CFG`/`EP8CFG` cleared at `0xe610/e611/e613/e615`).
- **V, settles the stream-translation question**: of 118 `MOVX @DPTR` instructions in the
  whole image, every one with a literal DPTR (109/118) targets `0xE5xx`-`0xE7xx` (CPU/USB
  config+status registers, GPIF/autopointer registers, `SUDPTR`, `EP0BUF`) — none targets
  `0xF000`-`0xFFFF`, the EP2FIFOBUF/EP6FIFOBUF address range where AUTOOUT/AUTOIN land the
  actual bulk payload. The remaining 9 (computed DPTR, built from register arithmetic)
  were traced by hand: all resolve to either the same `0xE6xx` status-register bank (fixed
  high byte `0xE6`, low byte = a small table index) or the compiler's far-data-segment
  initializer copying C globals into general-purpose XDATA `<0x0900` (unrelated on-chip
  scratch RAM, not FIFO memory) — never `0xF000`+. The only `MOVX @Ri` (8-bit indirect,
  1 instance, part of that same far-data-init loop) is architecturally incapable of
  addressing above `0xFF`. One `MOV DPTR,#0xfda5` exists (`0x09bc`) but is a pure
  `INC DPTR`-and-compare delay-loop counter — DPTR is never dereferenced there, it's used
  purely as a 16-bit down-counter (~5*65536 iterations) for a fixed post-FIFORESET/init
  delay.
  - Conclusion: the 8051 core only does USB-side housekeeping — enumeration (standard
    `GET_DESCRIPTOR`/`SET_CONFIGURATION` via EP0, descriptor table at the device-descriptor
    offset below), endpoint/GPIF configuration at init, and EPxCS flag polling. It never
    reads or writes a single byte of the EP2/EP6 bulk-endpoint FIFO memory. All streamed
    bytes move through the FX2's dedicated AUTOOUT/AUTOIN hardware FIFO path, untouched by
    code. This upgrades "transparent FIFO bridge" from the earlier register-literal
    inference to a verified (V), full-disassembly-exhaustive result.
  - Corollary (I, structural match not byte-diffed against a specific SDK release): the
    USB ISR (`0x0043`/`0x0053` both `LJMP 0x0700`->`0x09c9`, 24 B: ack one flag bit, RETI)
    has no autovector jump table — request dispatch (the 567 B function at `0x02d7`,
    decodes `bRequest` off `0xE6B9`/`SETUPDAT`-style registers into `GET_STATUS`/
    `SET_FEATURE`/`GET_DESCRIPTOR`/etc. branches) runs from the main poll loop
    (`FUN_CODE_0892`, reached from reset), not interrupt-driven. Shape matches Cypress's
    published slave-FIFO "framework" (`fw.c`/`TD_Poll`+`DR_VendorCmnd`) structurally; only
    the init register values and USB descriptors look customized, not the control flow —
    consistent with this being the stock example firmware with config/descriptor changes,
    not custom protocol logic.
- V: no ID content: descriptor has no serial string, no REVID read, no I2C/EEPROM register
  use (confirmed: no `MOVX` anywhere touches `0xE678`-`0xE67A`). Device descriptor VID
  0x0547 PID 0x1002.
- The `.iic` header carries PID 0x2131 (boot-time ID); runtime ID is 0x1002 (descriptor).
- Full disassembly + decompilation + function list: `tmp/m1500_ghidra/m1500_dump.txt`
  (not committed — regenerate with the script above; `tmp/` is ephemeral scratch per
  HANDOVER.md).

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
- **m1500 (FX2LP)**: yes, V, full-disassembly verified (issue #31). Slave-FIFO bridge with bulk EP2 OUT / EP6 IN, auto-commit; the 8051 core configures/polls control registers only and never addresses the EP2/EP6 FIFO buffer memory (0xF000-0xFFFF) — no byte reordering, buffering, checksum or protocol translation on the 8051 side. Strongest evidence of a payload path. FIFO peer = FPGA is I.
- **m0100**: yes. `68013.ko` + `rpmsg_trans.ko` + `cam_server` carry data/commands to the FX2LP over USB; RTOS controls DM368 streaming around updates (V).
- **m0900**: yes (existing docs): SPI2 register/AD9363 access, USART3 DUML, FPGA handshakes.
- **m0800 (DM365 on P3X, decrypted 2026-10-25)**: yes, confirmed — `dji/bin/encode_usb` is the TI-DVSDK-based H.264 encoder app, autostarted by `boot.sh` (`encode_usb -a -s &`) after `usb_68013.ko` is loaded; it is the USB video source feeding the FX2LP, not merely a name-based guess (V, was I).
- m0306, m0400, m1100/m1101, m1200-m1203, m1700/m1701, m0101, m0305: no FPGA contact found.
- V (was I): aircraft video chain is DM365 `encode_usb` -> USB -> FX2LP (m1500) -> slave FIFO -> FPGA -> AD9363, confirmed through the `m0800` decrypt for the first hop; FX2LP-onward still not proven end to end.

### (b) Code that could identify the chip or die
- **m0900**: STM32F103 96-bit UID via DUML `0x0904` -> `0x0954` (V).
- **m0306**: STM32F4 UID word 0 inside a 10-byte record (`0x080596ea`); GPS M8 UID expected (`0x0802867b`); IMU SN; user UUID (V strings, U consumers).
- **m0100**: ATSHA204 SN (9 bytes) and board number verified against A9 NAND; SD-card SN; authorized MAC. Not an SoC or FPGA UID.
- **m1700**: camera-module ID, not a chip UID.
- **FPGA / Cyclone V**: **superseded absolute wording** ("no code anywhere reads"): no such reader was identified in the specific firmware regions examined here. This does not exclude unexamined code, a proxy command or a different build. Only FPGA values read are regs 0x08/0x09 in the upgrade check (fpga-upgrade-path.md). Bitstream shows no user chip-ID block (weak, see m1900).
- m1500: none. m0400: none (reads flash `0x080C0000`, contents U). ESC/battery: unknown.

### (c) Firmware-upgrade path reaching the FPGA or sending an ID
- V: UEG in m0100 runs per module: version, entry, confirm, transmit, finish, reboot. **FPGA = fw-id 10, receiver 0x13, generic DUML transmit.** FX2LP = fw-id 11, USB transmit. m0900 = fw-id 9.
- V: m0900 handles Enter Loader / Confirm / Finish for receiver 0x13 with SPI handshakes (fpga-upgrade-path.md); it has no Update Transmit handler and drops type 0x13.
- U: the path of the FPGA image bytes after the camera. Candidates: DUML over a camera UART to m0900 (but m0900 drops type 0x13), or DUML-over-USB through the FX2LP (I, unproven). Needs the camera's route table or a bus capture.
- V: no chip UID, FPGA ID or aircraft serial appears in the UEG steps; identifiers checked are packet Manufacturer/ProductName/version, file CRC/MD5, SD-card SN (log only). m0900 sends its UID only on request `0x0904`.
- V: the FX2LP image is loaded into RAM with `fxload` (Vend_Ax loader, then the SD-card image) by `cam_server`; no persistent copy needed.

## Not checkable here
- **m0800** (DM365 Linux) — **decrypted 2026-10-25**, no longer in this list for stream-source/provenance purposes (see "m0800 decrypted" in `docs/camera-linux-console-access.md`). Still not checked here: the ATSHA204 "encrypt query" *contents* themselves — `encode_usb`'s `Entry Encrypt qury mode`/`AesEncryptToFile` strings confirm the exchange exists but its on-wire protocol with the camera wasn't traced this pass. Reference: `dm3xx_encode_usb_hardcoder.py` docstring (external tool) says the binary sends an encrypt request to the camera and compares the result — consistent with, not yet verified against, the decrypted binary's own strings.
- **m1900** content: no MCU code; decode quality too low (unidentified die) to prove absence of chip-ID logic or locate the DUML/FIFO ports.
- **m0900 bootloader** (`0x08000000-0x08007FFF`), A3 and camera bootloaders: not in the modules.
- **Camera DUML route** for receiver 19 (`DjiMsgChannelInit` `0x0e861988` onwards) and fw-id gating in `DjiUegFwUpdateById` (`0x0e8a3fec`): not decompiled.
- **Consumers** of the m0306 10-byte record and of the m0400 flash page `0x080C0000`.
- **Linux userland** (`cam_server`, `rpc_trans`, `util_svc`): strings only, no disassembly. `rom_fw` and `dsp_fw` partitions: strings only.
- **ESC (m1200-m1203), battery (m1100/m1101)**: architecture not confirmed (MSP430 for m1100 is I); no disassembler available here.
- **P3SE m0100** cannot be split by `amba_fwpak`; **Wi-Fi modules** m0700/m2700 (ath9k Linux) not analysed beyond keyword strings.
- **Hardware facts**: FIFO peer of the FX2LP, USB mux topology, which board strap the owned unit has: need a schematic or logic-analyzer capture.
- **DUML Get Version (0x01) / Query Device Info (0xFF) replies** traced for m0900 only (existing docs); m0400 resolved (see "m0400 gimbal"); m0305 `0x2000a390` and m0306 `0x080baa60` still heuristic-only; reply contents not decoded.

## m0400 gimbal: firmware reversing (issue #41)

**Redo of a shallow first pass** (commit `0c4234a`: 2/27 dispatch entries, peripherals as bare
ref counts). This is the full pass: all 27 entries decoded, every GPIOA/B/C pin use traced to a
peripheral, the SPI1 bus identified to an exact register map, CAN1/ADC1/TIM1/TIM3/TIM4 confirmed
or refuted, and the DUML transport topology (3 UARTs, not 1) corrected.

Image: `firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin` (97032 B, V). Ini version `01.48.0000` (V).
Loaded at `0x08008000` (I): reset vector `0x0800819d` lands inside the image (V).
Tooling: `scripts/re/m0400_full_reversing.py` (`scripts/re/ghidra/DumpM0400Full.java`), run over
`docs/data/stm32f407-register-map.tsv` (1414 RM0090 register labels, via `svd_to_labels.py` on
`awto-dan/docs/embedded/reversing/stm32/svd/STM32F407.svd`). Full decompile of all 337 functions,
dumped at `tmp/m0400_ghidra/m0400_full_dump.txt` (not committed, tmp/ is scratch - rerun the
script to regenerate). Ghidra project re-archived: `re/ghidra-projects/m0400_gimbal.tar.gz`.
Older single-purpose scripts (`m0400_ghidra_disasm.py`, `m0400_cmd_table.py`, etc.) are superseded
by this one but left in place since they're already committed history.

### Image and library
- V: no ELF, no `.symtab`/`.debug_*`, no compiler banner, no map tokens. Stripped raw image.
- V: no ST StdPeriph/HAL/CMSIS/RTOS names, no `assert_failed` or source-path strings.
- U: FunctionID/FLIRT not run. "No names" is not "no library".
- V: Ghidra found 337 functions (18 vector-table ISRs, 27 table handlers, the rest `FUN_*`),
  with the full STM32F407 SVD register map applied (1414/1414 labels placed, 0 skipped).
  No functions from `0x0801b660` to image end `0x0801fb08` (data or unexplored, U).

### Peripheral map (F4 RM0090 bases; Ghidra literal xrefs, V unless noted)
- RCC `0x40023800` 18 refs, FLASH_IF `0x40023C00` 1 ref: both in clock-init `0x08011220`.
- GPIOA `0x40020000` 80 refs; GPIOB 4 refs; GPIOC 1 ref. All attributed below, not left as counts.
- USART1 `0x40011000` 11 refs; USART2 `0x40004400` 14 refs; **UART4 `0x40004C00`, not previously
  found** (missing from the first pass's peripheral-base list entirely - it only checked
  USART1/2/3). USART3, SPI2, I2C1, SDIO: 0 refs, genuinely unused.
- SPI1 `0x40013000` 12 refs; ADC1 `0x40012000` 7 refs; CAN1 `0x40006400` 9 refs.
- **DMA1 `0x40026000`: 2 refs, but both are a literal used to compute a DMA2 address
  (`0x40026000` + `0x410` = `0x40026410` = DMA2_S0CR) - the base-literal scan missed this because
  the compiler folded the offset into one constant that doesn't equal any scanned base exactly.
  Confirmed from the raw literal pool (V): the real DMA engine in use is **DMA2 stream 0** (RX)
  **and stream 3** (TX, `+0x48` = 3 x 0x18-byte stride), matching RM0090's SPI1 RX/TX DMA request
  table. DMA1 itself has no real reference; DMA2 was never flagged by the base-literal scan
  because its own bare base (`0x40026400`) never appears as a standalone literal - this method
  undercounts whenever the compiler computes base+offset as one constant. Note for future passes.**
- TIM1 2 refs, TIM3 1 ref, TIM4 6 refs - all three only resolved properly below (ref counts alone
  were misleading for TIM1/TIM3, see "Timers").
- **TIM2 `0x40000000`'s "40 refs" from the first pass is a false positive**, confirmed by reading
  each hit (V): every one is `vmov.f32 sN,0x40000000` (the IEEE-754 bit pattern for float `2.0`),
  or `orr`/`bic #0x40000000` (clearing/setting bit 30 of an unrelated word). `0x40000000` is both
  the TIM2 base and the encoding of `2.0f`; naive scalar matching can't tell them apart. TIM2 has
  zero real register accesses anywhere in this image.
- U: F1-layout literals (RCC `0x40021000`, FLASH `0x40022000`) do have an LDR site this time (the
  pin-descriptor loop in `0x08009a20`, entries at `0x0801b9d8`+`0xc*i`, resolve to `0x40021800`/
  `0x40022000`-ish values) but what reads them is still not resolved - flagged, not guessed.

### Part (I)
- V: 98 vector slots; F4 has 82 IRQs, F1 high-density has 60.
- V: SP `0x2000fc40` inside F4 SRAM1 range.
- I: 1 MB flash (flash read at `0x080C0000`). Exact part F405/F407/F415/F417 not resolved.

### GPIOA/B/C: every pin traced to a peripheral (new, V unless noted)
GPIOA's 80 refs are not one subsystem - they're five:
1. **USART2** (`0x40009e0c`/`0x08009ee4`): 2 pins, AF7, feeds `FUN_08009e0c`.
2. **UART4** (`0x08009be0`, base `DAT_08009cb0` = `0x40004C00` - new find, see "UARTs" below): 2
   pins, AF8.
3. **SPI1 hardware init** (`0x08010f68`): CS/CLK/MOSI/MISO pins via a config struct, plus DMA2
   stream setup (`0x0800d1ac`/`0x0800d3a4`) for stream 0 and stream 0-0x48(=stream3).
4. **Three bit-banged synchronous-serial engines, same two pins** (`0x0800e1d8`, `0x0800e358`,
   `0x0800e5c0` - "write N bits then read M bytes", "write 6 bits then read 1 byte",
   "write 6+8 bits, no read"). All three load the *same* GPIOA base from three different literal
   pool slots (confirmed, V) and always toggle **PA5** (`GPIOA_BSRR` bit 5, clock) and sample
   **PA7** (`GPIOA_IDR` bit 7, data) - i.e. one shared 2-wire bus, not three independent buses.
   `MODER` bits for PA7 are flipped output->input mid-transaction (bit pattern `0x4000`/`0xC000` =
   pin7's 2-bit field), confirming half-duplex on a single data pin. The 6-bit address field
   (loop `for uVar2 = 5..0`) matches no single IMU vendor convention cleanly on its own, but
   combined with the per-instance structure (one read-N, one read-1, one write-1) this is the
   shape of a shared clock/data pair serving **multiple chip-selected slaves** - most plausibly
   three magnetic rotary-position encoders, one per gimbal axis, sharing PA5/PA7 with separate CS
   lines (I, functional shape only - no datasheet match attempted, no specific part named).
5. **`FUN_08009a20`**: configures PA5/PA6/PA7/PA15 statically (the shared bus pins above plus two
   more, `0x40`=PA6, `0x8000`=PA15) and a 3-entry pin-descriptor loop (`0x0801b9d8` + `0xc*i`,
   3 entries) whose per-entry "peripheral" words resolve to the dead F1-layout literals noted
   above, not real F4 addresses - **this loop's target is unresolved (U)**, flagged rather than
   assumed to be the three CS lines it would need to be for the encoder-sharing story above.

GPIOB (4 refs): 2 pins, AF7, USART1's TX/RX (`FUN_08009d08`) - matches RM0090's PB6/PB7 = USART1
AF7 exactly. GPIOC (1 ref): 1 pin, analog mode, ADC1 channel 10 (`FUN_08019068`) - matches
RM0090's ADC1_IN10 = PC0 exactly.

### SPI1: identified to an exact register map - InvenSense MPU-6500/9250/ICM-20608 family (V)
`FUN_0800f01c` (IMU bring-up) writes, in order, via the SPI1-register helpers
`FUN_0800f304`(write)/`FUN_0800f2d0`(read, sets bit `0x80` = read flag):
- `0x6B = 0x80` (**PWR_MGMT_1**, DEVICE_RESET)
- `0x68 = 0x07` (**SIGNAL_PATH_RESET**, reset gyro+accel+temp paths)
- `0x6B = 0x00` (PWR_MGMT_1, clear sleep/select internal clock)
- `0x6A = 0x10` (**USER_CTRL**, `I2C_IF_DIS` - disables the I2C side, SPI-only mode; this bit
  only exists on the MPU-6500/9250/ICM-20608 family, not the older MPU-6050/3050)
- `0x1A = 0x27` (**CONFIG**, DLPF setup)
- `0x1B = 0x12` (**GYRO_CONFIG**: FS_SEL bits -> +-1000 dps)
- `0x1C = 0x08` (**ACCEL_CONFIG**: AFS_SEL bits -> +-4 g)
- `0x1D = 0x08` (**ACCEL_CONFIG2** - only present on the 6500/9250/ICM-20608 family, confirms the
  sub-family alongside the I2C_IF_DIS bit above)
- `0x37 = 0x50` (**INT_PIN_CFG**: LATCH_INT_EN + INT_ANYRD_2CLEAR)
- `0x38 = 0x01` (**INT_ENABLE**: DATA_RDY_EN)
- then reads back every register just written, plus `0x75` (**WHO_AM_I**) - the value isn't in
  static firmware (it's the chip's runtime reply), but the address matches the same family.

This is a register-address match against the public InvenSense datasheet, not a guess: 9 exact
register numbers plus the bit used to force SPI-only mode and the register that only exists on
this sub-family. Exact die (MPU-6500 vs MPU-9250 vs ICM-20608) not distinguished - all three share
this register map; WHO_AM_I's value (not present in a stripped static image) is what would settle
it.

**DMA-fed burst read (V):** `vec_72` (IRQ72, a DMA2 stream0/stream3 completion ISR) processes a
15-byte buffer at SRAM `0x20004294` as `[1 status byte][6 bytes accel XYZ][2 bytes temp][6 bytes
gyro XYZ]` - exactly MPU's `0x3A` (INT_STATUS) through `0x48` (GYRO_ZOUT_L) burst-read region.
Gyro channels are accumulated over 16 samples and divided by 16 (oversample-decimate); accel and
temp are copied through raw each time. Output lands in a second SRAM struct at `0x20004248`
(`DAT_0800d138`).

### Timers: TIM4 confirmed (2 kHz tick), TIM11 confirmed (IMU pacing), TIM1/TIM3/TIM5/TIM6/TIM7/TIM8 dead
`FUN_080115ec` is a **generic, shared timer-config helper** (writes PSC at the real RM0090 offset
`0x28` and ARR at `0x2C`; has an `if` branch for the repetition-counter field that only TIM1/TIM8
have, and skips the CCMR field for TIM6/TIM7, which lack it) - it recognizes TIM1 (`0x40010000`),
TIM8 (`0x40010400`), TIM3 (`0x40000400`), TIM4 (`0x40000800`), TIM5 (`0x40000C00`), TIM6
(`0x40001000`), TIM7 (`0x40001400`). **Only two real call sites exist in the whole image:**
- `FUN_08009b3c` -> TIM4, PSC=20, ARR=2000. Its update-event ISR (`vec_46`, IRQ30) just sets a
  flag word - no CCR/CCMR output-compare writes anywhere in its call tree. **Not a PWM generator
  on this path** - it's a ~2 kHz tick (APB1 timer clock / 21 / 2000, consistent with the same
  2 kHz implied by "oversample 16 at ~32 kHz" above) driving control-loop cadence, refuting the
  PWM hypothesis for TIM4 specifically (I, confident; other channels not checked).
- `FUN_0800f01c` (the IMU bring-up routine, see above) -> **TIM11** (`0x40014800` - the ref-count
  table misleadingly suggested this was TIM1/TIM3; it is neither, confirmed by resolving the
  actual literal). PSC=1, ARR=0xa41 (2625): at a typical 84 MHz APB2 timer clock this is ~32 kHz -
  matches the 16x-oversample/2 kHz-output arithmetic above exactly (32 kHz / 16 = 2 kHz).
- **TIM1, TIM3, TIM5, TIM6, TIM7, TIM8 appear only inside the shared helper's own comparison
  chain - never at an actual call site.** Same category as the m0900 SPI1 precedent cited in the
  task: a shared/library driver supports more peripherals than this firmware instantiates. Genuine
  negative result, not a missed search.

### CAN1: initialized, but not cross-checked against the FC bus (V for the local init, U for the cross-check)
`FUN_080095b8` puts CAN1 into init mode, programs a bit-timing constant, programs filter banks
(`FUN_0800a130`, `FUN_0800a24a`) and starts the peripheral (`FUN_0800a238(...,3,1)`). `FUN_0800a0f8`
is a generic "enable CAN1 or CAN2 RCC clock" helper (branches on which CAN base is passed); only
ever called with the CAN1 base in this image, so CAN2 is confirmed **not** instantiated on this
chip specifically (0 CAN2 literal refs either). This settles that m0400's CAN1 is live, matching
the broader finding (issues #36/#40) that the FC's CAN1/CAN2 are genuinely initialized. **Not
settled in this pass:** whether m0400's CAN1 is wired to the *same physical bus* as the FC - that
needs the FC-side doc's bus topology cross-referenced against this MCU's bit-timing constant and
filter IDs, which wasn't done here (U, explicitly - would need the FC CAN docs open side by side).

### ADC1: one channel, not per-motor current sensing (V)
`FUN_08019068` configures exactly one ADC1 channel (channel 10 = PC0, matching RM0090's analog
pin map). `FUN_08019014` oversamples 32 readings, sums them, and scales by `3300/4096` (`0xce4` =
3300 decimal) - a plain millivolt conversion against a 3.3 V/4096-count reference. One channel,
not three, **rules out independent per-axis motor current sensing** - this is a single shared
rail/voltage monitor (I: which rail is U - no label on the ADC input net in this static image).

### UARTs: three independent DUML ports, not one link + one spare (corrects the task's own framing)
The first pass assumed "USART1 is the DUML link, find out what USART2 is for." That framing was
wrong - **there are three UARTs running structurally identical DUML frame-assemblers, and a third
UART (UART4, `0x40004C00`) that the first pass's peripheral scan never even listed:**
- USART1 (GPIOB AF7), USART2 (GPIOA AF7), UART4 (GPIOA AF8) each have their own byte-at-a-time
  frame-assembly state machine (3 near-identical functions, found by their RX ISRs feeding into
  checksum+decode calls `FUN_08011a8c`/`FUN_08018c54`), each tagging its port with a different
  constant (0, 1, or 2) when it hands a validated frame to...
- **`FUN_08016ff4`**, which is both the 27-entry command dispatcher *and* a cross-port relay. It
  checks `frame[5] & 0x1f == 4` (receiver-type field == gimbal) and `frame[5]>>5 == 0` (not an
  ack-only frame): if both hold, it walks the `0x0801d46c` table and dispatches locally (the
  table's own key check against `frame[9]`/`frame[10]` is the cmd-set/cmd-id match described
  below). **Otherwise it forwards the raw, unmodified frame** to UART4's TX queue (port tag 0) or
  USART2's TX queue (port tags 1 and 2) - i.e. m0400 is a **DUML relay between its three ports**,
  not a single-link endpoint. (`FUN_08016fac`, walking the *other* table at `0x0801d464`, is
  confirmed empty/dead - same as the first pass found.)
- Which physical UART maps to which of the three port-tag values (0/1/2) was not individually
  resolved in this pass (would need tracing each RX ISR's byte source into its own frame-assembler
  instance) - U, but the relay topology itself (dispatch-or-forward, 3 ports) is V.

### DUML dispatch: full 27/27 decode (was 2/27)
- V: dispatcher/relay `FUN_08016ff4` (see above). Table `0x0801d46c`, 27 entries, 8 bytes each
  (`{u32 handler|1, u8 id, u8 set, 2 pad}`), terminator at `0x0801d544`.
- Entries (set/id -> handler, cmd-set names per `app/packages/duml/lib/src/catalog.dart`):
  - **general (0x00)**: 0x01 `0x08016254` Get Version. 0x07 `0x08016338`. 0x08 `0x08016cdc`.
    0x09 `0x08016188`. 0x0a `0x080162e4`. 0x0b `0x08016840`. 0x0c `0x08016d30`. 0x0d `0x08016bf8`.
    0x30 `0x08013fcc`.
  - **special (0x01)**: 0x01 `0x08016c78`.
  - **flight-controller (0x03)**: 0x42 `0x08016634`.
  - **gimbal (0x04)**: 0x01 `0x08016564`, 0x06 `0x0801675c`, 0x07 `0x080168ac`, 0x08 `0x08016990`
    AutoCalibration, 0x0a `0x08015a50`, 0x0b `0x08015eb4`, 0x0c `0x08015c88` GimbalSpeedControl,
    0x0d `0x08016eac`, 0x0e `0x080167e0`, 0x0f `0x08016a98`, 0x10 `0x080163c4`, 0x11 `0x08016930`,
    0x13 `0x080161e8`, 0x14 `0x08015fe0`, 0x20 `0x08016e14`, 0x21 `0x08016e30`.

**Reply-building pattern, common to most handlers (V):** when `frame[8] & 0x7f >> 5 != 0` (an ack
bit requested), the handler calls `func_0x08016518` (rebuild header, swap sender/receiver, copy
seq) then `FUN_08016d94` (patch the 10-bit length field, send). This is the same shape across
~20 of the 27 entries - not reproduced per-handler below except where behavior differs.

**flight-controller 0x42 -> `0x08016634` (V, upgraded from "unclear" to confirmed):** copies 4
floats from frame `+0xb/+0xf/+0x13/+0x17` into a global, computes their sum of squares, and resets
to the identity quaternion `(1,0,0,0)` if the norm^2 falls outside `[0.95, 1.05]`. This is a unit
*quaternion* validity check - **the FC pushes its fused attitude quaternion to the gimbal
unprompted over the FLYC cmd-set**, and m0400 sanity-checks it before using it. This is the
cross-MCU attitude-reference input the gimbal needs for horizon-lock stabilization.

**special 0x01 -> `0x08016c78` (I):** gated on a state word `!= 3`; copies a 4-byte word and a
2-byte word from the frame into a global struct, and derives 2 one-bit flags from frame byte
`+0xf` vs the struct's cached copy. Shape suggests a mode-select/handshake command, not traced to
a wire capture - functional description only, no name assigned.

**gimbal 0x01 -> `0x08016564` (I), 0x06 -> `0x0801675c` (I):** both take 3 or 4 signed 16-bit
values centered on `0x400` (1024) - a joystick/RC-style input convention (unsigned 11-bit range,
center 1024) - clamp to +-0x295 (661) or zero if out of an inner deadband window. 0x01 writes 3
values straight into a setpoint array; 0x06 additionally gates on an encoding-type byte (calls
`FUN_08019138` to decode an extended payload first) and writes 4 values through a different
remap (`-0x3df`/`-0x421` offset branches) into a separate array, clearing a "pending" flag
afterward - read as calibration/limit-table input rather than a live control value, not confirmed
against a capture.

**gimbal 0x07 -> `0x080168ac` (I), 0x0d -> `0x08016eac` (I):** 0x07 adjusts a signed byte
accumulator (clamped `[-100, 'd'(100)]`) by frame byte `+0xb`, resets to 0 if that byte is 0 -
looks like an incremental trim/offset adjust. 0x0d is a two-value enable/disable latch: frame
value `0x2ab5` sets a bit in a flags word, `0x7ef2` clears the same bit - a magic-constant
toggle, not a counter.

**gimbal 0x0a -> `0x08015a50` (V, sibling of the already-confirmed 0x0c GimbalSpeedControl):**
same mode-check/scale-by-pi/180 shape as 0x0c, same +-pi radian clamp-to-zero (not saturate), same
reply pattern. Where 0x0c clamps only two of its three axes, 0x0a clamps only its first axis
(`puVar2[0xb]`). A 4th int16 at frame `+0x11` is scaled by a second constant (`DAT_08015c74`) into
a 4th setpoint, and a raw byte at `+0x14` is multiplied by 2000 into a 5th field (bounded to
`[2000, 20000]`, replaced by 4000 if out of range) - this handler carries more state than 0x0c
(5 fields vs 3), consistent with a superset/extended control command rather than a duplicate.

**gimbal 0x0b -> `0x08015eb4` (V):** pure telemetry readback, no payload fields read from the
request at all - builds a 17-byte reply comparing two global floats (`_DAT_08015fd4+0x7c` vs
`_DAT_08015fd8+0x28`) to set a sign bit, and includes a scaled copy of one of them
(`* fRam08015fdc`). Reply-only status query, not a control command.

**gimbal 0x0f -> `0x08016a98` (V):** iterates a frame-encoded list of `(index, length)` pairs
(up to 12 indices, length <= 8), copying each indexed field from a lookup table (`0x34`-byte
stride, same table structure used by the general-0x07/0x10 handlers below) into the reply buffer -
a generic "read back these N parameters by index" command, same table-driven shape as the
general-set equivalents.

**gimbal 0x10 -> `0x080163c4` (V) and general 0x07 -> `0x08016338` (V):** near-identical
implementations of the *same* generic parameter-table copy engine (switch on a type byte -
0/4=1 byte, 1/5=2 bytes, 2/6/8=4 bytes - copying from a `0x34`-byte-stride lookup table into the
reply). general-0x07 is the broader one (handles up to 12 fields with an error code `0xe3` for an
out-of-range index >= 0xc); gimbal-0x10 is the same logic without the dispatcher-reply-gating
wrapper inlined. This is very likely a shared "get parameters by ID list" implementation reused
between the general and gimbal command sets.

**gimbal 0x11 -> `0x08016930` (I):** calls `FUN_0800dfd8` on a global and checks for return value
9 (success) vs anything else (sets an error code `0xe6` and a different status pair) - looks like
a "commit/apply pending config" acknowledgement wrapper around a state-machine check in
`FUN_0800dfd8`, not traced further.

**gimbal 0x13 -> `0x080161e8` (I):** copies a fixed 0xd8-byte (216-byte) block from one lookup
structure to another (`FUN_08008adc`, a memcpy-shaped helper), then calls two no-argument
functions (`FUN_080113ac`, `0x08010434`) before acking - reads as "reload/reset a fixed-size
config block," block contents and the two follow-on calls not traced.

**gimbal 0x14 -> `0x08015fe0` (V):** takes 3 signed 16-bit values (`+0xb/+0xd/+0xf`, in units of
0.1 degrees - scaled by `0.1 * pi/180`) and a raw byte (`+0x12`, scaled by `0.1 * 2000.0 + 1.0` as
a denominator), divides the three angle values by that denominator, and **integrates them into a
persistent position struct** (`_DAT_0801617c + 0x54/0x58/0x5c`) rather than overwriting it -
subtracting a reference triple (`_DAT_08016180`) first if a "relative mode" bit is set. This is
an incremental/rate-limited position-target update (smoothing via the denominator term), distinct
from the direct-setpoint shape of 0x0a/0x0c.

**gimbal 0x20 -> `0x08016e14` (I), 0x21 -> `0x08016e30` (I):** 0x20 copies a 4-byte value and two
single bytes from the frame into a global, no reply. 0x21 is gated on frame byte `+0xb == 0`, then
copies 3 x (4-byte + 2 bytes, with a zeroed 3rd byte appended) from the frame into a 3-entry
global array - shape matches "write 3 per-axis calibration/limit records," not confirmed against
a capture.

**general 0x08 -> `0x08016cdc`, 0x09 -> `0x08016188`, 0x0a -> `0x080162e4`, 0x0c -> `0x08016d30`
(all I):** thin ack-only handlers, each just rebuilding the reply header with a fixed length code
(0x10, 0x12, 0xe, 0x13) and, for 0x0c, copying a global word into the reply payload and clearing a
4-bit field first. No meaningful request-side payload is read on any of these four - straight
acknowledgements.

**general 0x0b -> `0x08016840` (I):** same incremental trim-byte logic as gimbal-0x07 above
(clamped `[-100,100]`, reset on 0), reusing the same global (`_DAT_08016920`/`_DAT_08016924`/
`_DAT_08016928`/`_DAT_0801692c`) - this and gimbal-0x07 are the same underlying state exposed
under two different (set, id) pairs.

**general 0x0d -> `0x08016bf8` (I):** validates a payload field (`FUN_08019b3c`, then
`FUN_08019c90` with a 0x10-byte bound) and sets an error byte `0xf4` on failure, otherwise clears
a nibble field and copies in a fresh 0x10-byte block (`FUN_08019c54`) before acking - looks like a
bounded-length config-block write with validation, mirrors 0x13's "reload a block" shape but with
an explicit length/format check this time.

**general 0x30 -> `0x08013fcc` (V):** a sub-dispatcher, not a leaf handler - branches on frame
byte `+0xb` (values 1/2/3) to three separate functions (`0x08013774`, `0x08013c54`, `0x08013a18`),
plus a 4th call (`0x080139ac`) gated on the ack-bit *and* `param_2 == 0x48` (payload length 0x48 =
72 bytes) regardless of the `+0xb` switch. Those four sub-handlers were not decompiled in this
pass (U) - flagged rather than assumed trivial, since 0x30 is structurally different from every
other entry (it's the only one with its own internal dispatch).

### Get Version -> `0x08016254` (set 0x00 id 0x01)
- V: copies 2 words from flash `0x080C0000` via `0x0800da3e(src, count, dst)` into stack.
- V: stores word[1] (flash `+4`) into reply at frame `+0x12`.
- V: writes constant `0x01300000` to a struct `+4` and `1` to `+8`. Meaning U.
- U: flash `0x080C0000` contents. Outside the image, so not in this file.

### Outbound push path (GetPushParams pitch/roll/yaw): partially traced, genuine open end
Confirmed (V): the SPI1+DMA2 IMU burst read (`vec_72`, above) writes its decimated gyro / raw
accel+temp result into SRAM struct `0x20004248` (`DAT_0800d138`). That is the only place this
pass found writing that struct.
**Not found (U, explicit negative result, not a shallow miss):** no other function in the 337-
function decompile reads the symbol `DAT_0800d138` by name. This almost certainly means the
consumer loads the same SRAM address (`0x20004248`) from a *different* literal-pool slot, which
Ghidra names independently per pool entry rather than per target address - a per-symbol text
search can't find that aliasing. What would settle it: a cross-reference pass keyed on the
absolute address `0x20004248` (e.g. a Ghidra script walking all `DAT_*` symbols and grouping by
resolved value, not by name) rather than grepping for one symbol's name. Not run in this pass.

## Superseded GO 4 checklist (historical; use the classic GO audit)
- Class/package names: upgrade (`Upgrade`, `Firmware`, `FwUpdate`), version/device info (`GetVersion`, `DeviceInfo`, `DeviceState`), activation (`Active`, `Activation`, `RealName`), module-id tables with `FPGA`, `68013`, `DM368`, `1765`.
- Native libs: DUML pack/unpack, upgrade-packet builder (`Fw3.bin` naming, `P3X_FW_V%d.%d.%d.bin`), any AES/CRC on upgrade packets.
- Upgrade flow: which command sets the app sends (0x00 general: 0x07..0x0d), whether it pushes the package over DUML/USB or only copies it to the SD card, what it logs from `PushUpgradeStatus`.
- Activation flow: what the app sends to the aircraft (UUID / real-name, `[set uuid]` in m0306) and to DJI servers; whether any chip UID is included.
- Server-side JSON for firmware lists (module ids, MD5, rollback fields).
