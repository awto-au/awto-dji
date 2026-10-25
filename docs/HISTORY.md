# Fact-correction history

Dated changelog of fact-corrections previously narrated inline in the docs. Each entry is
phrased as "initial understanding -> corrected finding." The docs now state only the
corrected/current fact; this file preserves the history for reference.

## 2026-10-25

- **m1401 (ground radio, LPC1549 variant) analysed for the first time:** was previously noted
  only as "LPC1549 variant of m1400... not analysed further" -> a separate, richer upstream
  symbol map (`C1_FW_V01.06.0000_m1401.map`/`.idc`, o-gs/dji-firmware-tools) already vendored
  locally but not examined was found (user-prompted) to carry `get_board_version`,
  `packet_hw_receive`, `ofdm_init_instruction`, and `cmd_exec_setXX_cmdYY` handler names.
  `get_board_version` decompiled (file offset `0x11ce4`): calls a shared compare-and-log helper
  against RAM `0x2000600`; no direct caller found yet (likely a function-pointer table entry).
  Confirmed against the real re-extracted binary (same `c1.bin` verified earlier), same
  2016-03-21 build vintage as m1400. New open question: which chip family (m1400/LPC1765 vs
  m1401/LPC1549) the operator's actual GL300C uses — the live build string doesn't disambiguate,
  and neither 2016 build matches the live-reported 2017-08-28 date regardless. (`docs/
  ground-upgrade-path.md` §Q6, `docs/data-manifest.md`)
- **RC's own micro-USB port (`2ca3:0008`) identity:** initial understanding was open between
  three hypotheses — m1400's own USB peripheral, a second Cypress FX2/FX3 bridge chip (DJI
  reuses FX2LP elsewhere), or an LPC boot-ROM/ISP mode -> **resolved**: the descriptor strings
  (`DJI  CONFIF  `, `DJI    CONTROLLER`, `0001A0000000`) and `VCOM`/`MSCM` class tags are
  literal constants inside m1400's own compiled image, ruling out a second bridge chip;
  answering a real DUML GetVersion rules out a bare boot-ROM mode. Matches the aircraft FC's
  identical `VCOM`/`MSCM` pattern. **Correction, same day:** the first evidence for this was a
  grep of the wrong firmware build (`P3X_FW_V01.03.0020`'s bundled m1400 copy; its build-date
  string doesn't match the operator's `WM320_A7_LPC1 20170828/00`) -> re-grounded on the
  correct version's own IDA symbol map (`C1_FW_V01.06.0000_m1400.map`), which independently
  names the same `aDjiConfif`/`aVcom`/`aMscm` string symbols. **Resolved fully, same day:**
  re-obtained the real `c1.bin` from a live CDN URL (`dl.djicdn.com/downloads/lightbridge2/
  C1_FW_V01.06.0000.bin`), hash-verified exact, unpacked, and confirmed the same strings
  directly in the real binary at the symbol map's address (offset-adjusted). **New finding this
  surfaced:** this container's m1400 submodule (build-tagged `WM610 A7_1765 20160321/01`)
  predates the operator's live-reported build (`WM320_A7_LPC1 20170828/00`) by ~17 months — the
  container hash matches and its FPGA submodules are independently confirmed current, but DJI
  evidently updates modules independently inside one version tag, so this specific m1400 build
  is not bit-identical to what's actually running. (`docs/ground-upgrade-path.md` §Q5,
  `docs/fc-usb-port.md`, `docs/data-manifest.md`)
- **FC activation-gate addresses:** initial understanding cited `is_prod_activated` 0x08047c2c /
  `check_activation_authority` 0x08047d5e / `dji_sdk_set_key` 0x0805a964 -> corrected: those are
  from a *different build's* symbol map (V01.07.0060) and land in an unrelated MD5 routine in the
  loaded V01.11.0020 image. Re-derived for this build: activation-state read `FUN_08046d54`, fed by
  `fc_sdk_set_key` (0x08046e86), checked inside the real motor-arm logic (`FUN_08024b46` emitting
  "Product not activation,stop motor!", and the table-driven `fc_Motor_Start` path gating
  auto-takeoff). The gate-is-real conclusion is unchanged. (`docs/security-and-activation.md`,
  `docs/fc-auth-enforcement-trace.md`)
- **A9 ATSHA204 MAC/SN effect:** initial understanding = "only demonstrated effect is client/app
  authorization" -> refined: the `CheckA9Mac`/`CheckSN` result latches a persistent A9 RAM flag
  (0x109d00b8) that ≥3 other A9 functions branch on, skipping work when unauthorized, so it gates
  ≥1 on-device A9 feature path (which subsystem = I/U). Still **no** tie to the FC or flight/boot.
  (`docs/security-and-activation.md`, `docs/fc-auth-enforcement-trace.md`)
- **P4 flight-controller MCU:** initial understanding guessed a bigger STM32F4-family part ->
  corrected to Microchip/Atmel **ATSAME70Q21** (Cortex-M7). The `0x2040_0000` RAM-base
  observation was at one point withdrawn on an assumption of STM32, then shown to in fact be
  the SAM E70 signature (flash @ `0x00400000`, SRAM @ `0x20400000`, 384 KB). (`docs/prior-art.md`)
- **m0306 register library:** initial understanding described it as "DJI's own raw HAL" ->
  corrected to **ST Standard Peripheral Library (SPL / StdPeriph)**, established by code
  structure (RCC/GPIO/USART/CAN call signatures), not strings. (`docs/fc-io-inventory.md`)
- **UART base/baud:** initial understanding said the config "lives in RAM and can't be
  recovered" -> corrected: the base comes from a flash lookup table `USARTx[8]` at
  `0x803bfd8`, and the SDK/API baud is a named parameter with flash defaults
  (`api_entry_cfg.baud_rate` default **230400**, min 110, max 921600). (`docs/fc-io-inventory.md`)
- **FC slots:** initial understanding concluded "single-slot, no A/B" from the app alone ->
  corrected: the app is single-image, but the `m0305` loader/updater implements a true
  **two-slot A/B** scheme (bank-1 app `0x08020000`, bank-2 `0x08100000`), with the loader
  (sectors 0-4) excluded from the erase path. (`docs/fc-bootloader.md`)
- **ATSHA204 location:** initial understanding implied RC/`m1400`-only -> corrected: the
  primary ATSHA204 board authentication is on the **camera/A9 (`m0100`)**, with a second
  instance on the RC (`m1400`); the P3 FC (`m0306`) has no ATSHA204 code.
  (`docs/atsha204-repair-note.md`, `docs/security-and-activation.md`)
- **ATSHA204 effect:** initial understanding implied a failed/absent chip bricks the board ->
  corrected: the only enforcement RE demonstrates is **client/app authorization**
  (`cam_server` rejecting an unauthorized MAC via `DjiMsgAuthorizedMac`); whether a
  failed/absent chip halts boot or flight is unestablished (U). The real firmware-enforced
  hardware motor gate is **DJI product activation**, a separate mechanism.
  (`docs/atsha204-repair-note.md`, `docs/security-and-activation.md`)
- **Compiler/toolchain:** initial understanding recorded "compiler: U(nknown)" -> corrected to
  **IAR Embedded Workbench**, from the upstream IAR linker symbol map
  (`__iar_program_start`) for the adjacent build V01.07.0060. (`docs/fc-io-inventory.md`)
