# Fact-correction history

Dated changelog of fact-corrections previously narrated inline in the docs. Each entry is
phrased as "initial understanding -> corrected finding." The docs now state only the
corrected/current fact; this file preserves the history for reference.

## 2026-10-25

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
