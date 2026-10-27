# Code provenance — compilers, RTOSes and libraries in the firmware

Going past `strings`: disassembly and structural analysis to find what DJI built *on*.
Short version — the premise is right: DJI did **not** write this from scratch. The
Linux SoCs are a full GNU/open-source stack, and even the **flight controller runs a
third-party RTOS (µC/OS)**.

## Tools used (in the analysis env)

- `dji_xv4_fwcon.py` — unpack the `xV4` package into modules.
- `strings` + targeted grep — toolchain/library name fingerprints.
- **radare2 5.5.0** — disassembly; read Cortex-M vector tables to identify the chip and
  the RTOS context-switch handlers. (Load raw image with `-a arm -b 16 -m <base>`; bases
  from the dji-firmware-tools README: FC `0x08020000`, `air_router_stm32f103` `0x08008000`.)
- `binwalk` — signature/entropy scan of the big camera image.
- **Ghidra 12.2 DEV is installed** (`/home/dan/tools/ghidra_12.2_DEV`, shim at
  `~/.local/bin/ghidra`), with native 8051 and ARM support; `support/analyzeHeadless` for
  headless runs (used for `m1500`, `scripts/re/m1500_fx2_disasm.py`). radare2 + the
  vector-table method remains enough for Cortex-M provenance checks that don't need full
  decompilation.

## Compiler provenance

| Module | Toolchain evidence | Compiler |
|---|---|---|
| `m0100` camera (Linux) | `GCC: (`, `__gnu_`×1142, `__aeabi_`×482, `libgcc`×93 | **GNU GCC** |
| `m0800` video encoder (Linux) | **resolved 2026-10-25 (issue #20):** `Salted__` blob decrypts with `openssl enc -d -des3 -md md5 -k Dji123456` — password published by the `o-gs/dji-firmware-tools` wiki, independently re-found and reproduced here (`scripts/re/m0800_decrypt.py`). Decrypted `encode_usb` binary's own build paths name **TI DaVinci DVSDK `dm368_4_02_00_06`** (Codec Engine, XDAIS, LinuxUtils/CMEM/EDMA3, TI's own h264enc/mpeg2enc codecs, Ittiam AAC). Kernel modules `cmemk.ko`/`edmak.ko` declare `author=Texas Instruments`, `license=GPL`. See `docs/camera-linux-console-access.md` "m0800 decrypted". | **GNU GCC (TI DVSDK toolchain) + DJI app code (`encode_usb`) on top** |
| `m0101` camera loader | `IAR` | **IAR** (with ThreadX) |
| `m0306` FC, `m0900` radio, `m0400` gimbal | stripped raw `.bin`, no compiler comment | ARM EABI (Cortex-M); not identifiable from strings |

## Chips (from Cortex-M vector tables)

- **`air_router_stm32f103` (m0900)** — Cortex-M3 (STM32F103): initial SP `0x20004cb8`, reset into app
  at `0x08008200` (bootloader occupies `0x08000000`–`0x08008000`).
- **`m0306` A3 flight controller** — Cortex-M4, **STM32F427** (`docs/dataflow.md` §7.9
  external corroboration, `o-gs/dji-firmware-tools` wiki pinout for the P3X FC board;
  this repo's own firmware-only pass could only narrow to the F42x/F43x line — SRAM size
  below). Initial SP `0x2002ff00`: image has a real vector table at file offset 0 (SP word
  + reset/NMI/HardFault/SVCall/PendSV/SysTick vectors, all absolute addresses
  `0x0802xxxx`–`0x0802cxxx`), app loaded at **`0x08020000`** — confirmed by decoding the
  PendSV handler (`0x0802c79f`, file offset `0xc79e`, decodes to `cpsid i` under this base
  — a context-switch prologue) and the SysTick handler (`0x08029de3`, file offset `0x9de2`,
  decodes to `push {r4,lr}; bl <tick-incr>; bl <scheduler>` — a sane ISR, not garbage).
  Decoding the same bytes under `0x08000000` instead gives non-sensical instruction streams
  at both handlers — rules out that base. `0x2002ff00` sits 256 B below `0x20030000`, the
  exact top of SRAM1 on the F42x/F43x line (192 KB SRAM1 `0x20000000`–`0x2002FFFF` + 16 KB
  SRAM2 to `0x20033FFF`); F405/407/415/417 (128 KB, top `0x20020000`) and F413/423 (320 KB,
  top `0x20050000`) don't fit. SVD: `awto-dan/docs/embedded/reversing/stm32/svd/
  STM32F429.svd` (register-compatible stand-in — F427 doesn't differ from F429 outside
  LCD-TFT, not referenced anywhere in this image). **Debug symbols: none** — no ELF magic,
  no `.debug_*`/`.symtab`/`.strtab`, no map-file/source-path strings anywhere in the 885 KB
  image (same check, same result, as `m0900`) — manual RE only, same as every other MCU
  module here. **Full Ghidra pass** (issue #40): 2745 functions / 122,341 instructions,
  project archived `re/ghidra-projects/m0306_flight_controller.tar.gz`
  (`scripts/re/m0306_ghidra_disasm.py`). Peripheral map (literal-pool xrefs, confirmed live
  by tracing to real register writes, not just presence): **CAN1** (`0x40006400`) and
  **CAN2** (`0x40006800`) both genuinely initialised — GPIO AF9 pin config
  (`GPIO_PinAFConfig`-pattern calls at `0x080353e6`/`0x080353f6`), RCC clock-enable
  dispatch (`0x0803addc` → one of a `0x0806d5f0`-`0x0806d7ca` per-peripheral enable-bit
  cluster), bit-timing (BTR-pattern) register writes at `0x080351d0` (CAN1) and `0x08035484`
  (CAN2) — unlike `m0900`'s dead `SPI1` dispatcher (control-plane-re.md), this is live code
  on both CAN instances. Also referenced: **USART1/2/3, UART4/5, USART6** (one shared
  init dispatcher at `0x0803bc94` iterating all six), **GPIOA-I**, **I2C1/2/3**, **TIM1/
  TIM8** (motor-PWM-capable timers), **RCC**. **Not referenced anywhere**: SPI1/2/3, ADC,
  DMA1/2, FSMC/FMC — this FC does not appear to use SPI or DMA at all (contrast `m0900`,
  which drives the AD9363 and FPGA over SPI).
- **`m0400` gimbal MCU** — STM32F4 family, RM0090 map (V for family, I for exact part).
  - V: initial SP `0x2000fc40`; 98 vector slots (F4 = 82 IRQs; F1 high-density = 60).
  - V: RCC `0x40023800` and FLASH_ACR `0x40023C00` literals in clock-init `0x08011220`;
    USART1 `0x40011000` literal in IRQ37 ISR `0x08011724`. F1 USART1 `0x40013800`: no literal.
  - V: `docs/embedded/reversing/stm32/svd/STM32F407.svd` (awto-dan) agrees on RCC/FLASH/USART1 bases.
  - I: exact part F405/F407/F415/F417 (1 MB flash, from the `0x080C0000` read). Not resolved:
    no DBGMCU_IDCODE or UID read in the image.
  - Details and tooling: `docs/air-id-and-stream-survey.md` ("m0400 gimbal: firmware reversing").

## RTOS / library provenance — the key findings

| Module | Third-party code found | How |
|---|---|---|
| **`m0306` A3 flight controller** | **µC/OS-III** (Micrium RTOS) + **CMSIS startup** + **ST StdPeriph-pattern drivers** | `uC/OS-III Idle Task`/`Stat Task`/`Tick Task` strings (refines the earlier generic "µC/OS" to the specific **III** generation); PendSV (`0x0802c79f`) + SysTick (`0x08029de3`) handlers populated = preemptive scheduler. **CMSIS**: startup fn `0x0802258c` is a textbook `SystemInit()`-style HSE→PLL→FLASH-latency bring-up (HSE `ON`/wait-ready, `RCC_PLLCFGR` write, `FLASH_ACR` wait-states+prefetch/cache enable, `PLLON`/wait-ready, `RCC_CFGR` `SW`→PLL + wait `SWS`) — same boilerplate CMSIS device-support file ships for every STM32F4 part. **StdPeriph pattern**: the RCC clock-enable calls (`0x0803addc` etc.) dispatch through a cluster of near-identical bit-set/clear wrappers (`0x0806d5f0`-`0x0806d7ca`, one per peripheral) — the same `RCC_xxxPeriphClockCmd(periph, state)` shape already identified in `m0900` (control-plane-re.md), not the newer HAL's `__HAL_RCC_*_CLK_ENABLE` macro-inlined form. No DJI `hal_*` sensor-abstraction strings found in `m0900`/`m0400`, but `m0306` has its own (`hal_compass_add` etc.) — a DJI-internal sensor HAL layered *above* the StdPeriph/CMSIS base, not a vendor middleware. |
| `m0101` camera loader | **ThreadX** (Express Logic RTOS) + IAR | strings |
| `m0100` camera | **Linux**, glibc, busybox, OpenSSL, wpa_supplicant, zlib, libjpeg, dropbear, ThreadX | strings (see license-compliance.md) |
| `air_router_stm32f103` (m0900) | none named — small bare-metal (likely ST StdPeriph/CMSIS + custom) | disासm + strings |
| `m0400` gimbal | none found: no ST StdPeriph/HAL/CMSIS/RTOS names, no assert or source-path strings (V). FunctionID/FLIRT not run (U) | strings + Ghidra literal xrefs (issue #41) |

**Conclusion.** The flight-critical A3 controller is DJI *application* code running on the
**µC/OS** commercial RTOS — so even here DJI stands on third-party foundations. The camera
and video SoCs are wholesale GNU/Linux/open-source. Only the smallest MCUs (radio,
gimbal) look like bespoke code on the silicon vendor's libraries. The "unreadable" bare-
metal images aren't from-scratch magic; they're stripped release builds on a standard
ARM toolchain + a licensed RTOS.

## License note

µC/OS and ThreadX were **commercial** RTOSes at the P3's era (Micrium per-product
licensing; Express Logic ThreadX likewise), so they carry **no open-source source
obligation** — but their presence confirms third-party code. (Both later went open —
µC/OS under Apache-2.0 in 2020, ThreadX as Azure RTOS under MIT in 2023 — but the P3
firmware predates those, so the commercial terms applied when it shipped.) This updates
the `m0306` row in `license-compliance.md` from "proprietary, none" to "proprietary app
on µC/OS (commercial RTOS)".
