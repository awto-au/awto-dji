# Fact-correction history

Dated changelog of fact-corrections previously narrated inline in the docs. Each entry is
phrased as "initial understanding -> corrected finding." The docs now state only the
corrected/current fact; this file preserves the history for reference.

## 2026-10-25

- **RC's own micro-USB port (`2ca3:0008`) identity:** initial understanding was open between
  three hypotheses — m1400's own USB peripheral, a second Cypress FX2/FX3 bridge chip (DJI
  reuses FX2LP elsewhere), or an LPC boot-ROM/ISP mode -> **resolved**: the manufacturer/
  product/serial descriptor strings (`DJI  CONFIF  `, `DJI    CONTROLLER`, `0001A0000000`) and
  `VCOM`/`MSCM` class tags are literal constants inside m1400's own compiled image, ruling out
  a second bridge chip; answering a real DUML GetVersion rules out a bare boot-ROM mode. Matches
  the aircraft FC's identical `VCOM`/`MSCM` pattern — both MCUs run their own on-chip USB stack
  independently. (`docs/ground-upgrade-path.md` §Q5, `docs/fc-usb-port.md`)
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
