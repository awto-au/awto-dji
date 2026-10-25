# m0306 flight controller — I/O and software inventory

Peripherals, clocks, sensors and software identity of the Phantom 3 Pro flight controller
(module **m0306**, firmware `P3X_FW_V01.11.0020`). Derived from the AES-decrypted module
(`scripts/re/xv4_decrypt.py`, key/scheme in that file; container hashes in
`docs/data-manifest.md`) in a Ghidra 11.4 project plus plain string/word scans.

Tags: **V** verified in this firmware, **I** inferred, **U** unknown / needs-tooling. The
project's honesty convention (`CLAUDE.md`) applies: exact baud/CS/prescaler values that the
firmware computes at runtime are marked **U**, not guessed.

## MCU

- **STM32F427** (Cortex-M4F), image base `0x08020000`, reset vector `0x08021964`, initial
  SP `0x2002ff00`. **V** (vector table of the decrypted module).
- The F42x/43x line clocks to 180 MHz max. The firmware carries ST's `RCC_GetClocksFreq`
  readback (named `rcc_get_clocks_freq` @ `0x0806d5f0`): it decodes `RCC_CFGR[SWS]` and, for the
  PLL case, computes `SYSCLK = PLLsrc / PLLM * PLLN / (2*(PLLP+1))`, then derives HCLK/PCLK1/PCLK2
  through the AHB/APB prescaler table — the standard ST formula. **V** (decompiled). The concrete
  SYSCLK/PLL word is written in `SystemInit` from runtime-loaded constants and is **U** here
  (not recovered); the HSE crystal value is not a plaintext constant in the readback pool.

## Peripheral usage (which blocks the firmware drives)

STM32 code reaches a peripheral through a base pointer in a literal pool (`ldr rN,[=BASE]`), so
the count of literal-pool words equal to each peripheral base is a usage proxy. Reproduce:
`python3 scripts/re/fc_io_inventory.py <m0306_decrypted.bin>`. **V** (every row below is a real
base-address word in the image); the *role* column is **I** unless noted.

| Peripheral | Base | pool refs | Role (I unless noted) |
|---|---|---:|---|
| **TIM2** (32-bit) | 0x40000000 | 63 | free-running microsecond time-base / timestamp counter (dominant timer; used pervasively) |
| GPIOA/B/C/D | 0x40020000.. | 8/10/4/9 | pin banks for sensor CS, bus AF, strobes |
| GPIOE/F/G/H/I | 0x40021000.. | 3/3/1/3/1 | more pin banks |
| **CAN1** | 0x40006400 | 4 | **V** primary inter-MCU link (FC ↔ gimbal/centre board; the 0x41x CAN IDs of `m0900-can-channels.md`) |
| **CAN2** | 0x40006800 | 2 | second CAN bus |
| FLASH_IF | 0x40023c00 | 3 | internal-flash program/erase (param save) |
| FSMC | 0xA0000000 | 3 | external memory bus — only 3 base loads, no init path found; likely minimal/unused (**I**) |
| USB OTG_FS | — | — | **V** USB device on PA11/PA12 AF10 (see pin map) — DJI Assistant 2 / upgrade + sim link to FC. (The two base-word loads to the OTG_HS base `0x40040000` don't match a USB init path and are likely spurious; the pins prove OTG_FS.) |
| TIM1/3/4/5/6/7/8/9/10/11/12/13/14 | — | 1–2 each | motor PWM out (TIM1/TIM8 adv.), misc time-bases |
| USART1/2/3, UART4/5/7/8, USART6 | — | 1 each | serial links (GPS, RC/DBUS, OSD, debug — individual mapping **U**) |
| SPI1/2/3/4/5/6 | — | 1 each | sensor buses (**I**: IMU/baro on SPI; exact CS **U**) |
| I2C1/2/3 | — | 1 each | sensor buses (**I**: compass on I2C) |
| ADC1-3 | 0x40012000 | 1 | analogue (**I**: voltage/current/temp) |
| SDIO | 0x40012c00 | — | **V** SD/eMMC data logger — pins PC8/9/10/11/12 (D0–D3, CK) + PD2 (CMD) @ AF12 (`sdio_bringup` 0x08039f92) |
| IWDG | 0x40003000 | 1 | independent watchdog |
| SYSCFG/EXTI | 0x40013800 | 1/1 | pin interrupt mux (sensor DRDY/strobe) |
| PWR, CRC, RCC, BKPSRAM | — | 1–2 | core services |

Notes: this count is literal-pool base loads; a block accessed only through an already-held
pointer (e.g. passed into a generic `hal_*` driver) can show few pool refs yet be used a lot —
so "1" means "present and initialised", not "barely used". USB_OTG_**FS** (`0x50000000`) has **no**
base word; the FC's USB is OTG_HS. Exact per-UART baud, SPI CS lines/clock, and TIM PSC/ARR are
runtime-computed through DJI's `hal_*` layer and are **U** from the static image (would need a
live trace or deep per-driver decompilation).

## Sensors (driver strings)

- **IMU / gyro+accel:** InvenSense **MPU-6500** (`mpu6500_oversample`; `gyro_data_type` param). **V**.
- **Compass:** **HMC5883** and **IST8303/IST8310** (`__init_hmc5883`, `__init_IST8303`,
  `COMPASS_IST8303/IST8310`), attached via `hal_compass_add`. **V**.
- **Barometer:** present (`STD_BAROMETER`, FDI BARO events); part number not in strings. V (presence).
- **GPS:** present (FDI GPS events, `GPS_Ready`). V (presence).

## Software identity

- **RTOS: Micrium µC/OS-III.** **V** — `uC/OS-III Idle Task`, `... Stat Task`, `... Tick Task`.
- **Register library: ST Standard Peripheral Library (SPL / StdPeriph).** **V** — by *code
  structure*, the decisive evidence, not strings. Five independent SPL fingerprints across four
  different library modules (each in its own address cluster, i.e. its own linked `.o`):

  | SPL function | address | why it's SPL (not HAL / not LL) |
  |---|---|---|
  | `RCC_AHB1/2/APB1/2PeriphClockCmd` + `...ResetCmd` | 0x0806d716–d7ca | generic `fn(uint32 mask, FunctionalState NewState)` RMW on `RCC->*ENR/*RSTR`. HAL uses per-peripheral `__HAL_RCC_*_CLK_ENABLE()` macros; LL splits into two arg-less `LL_*_Enable/DisableClock` — neither has a masked `(mask,NewState)` call. |
  | `RCC_GetClocksFreq` | 0x0806d5f0 | one call fills a 4-field `RCC_ClocksTypeDef` via `APBAHBPrescTable[]`. HAL splits this into separate `HAL_RCC_GetHCLK/PCLK1/PCLK2Freq()` getters. |
  | `CAN_Init` / `CAN_DeInit` | 0x0803ae02 / 0x0803addc | MCR INRQ→INAK handshake then `BTR = SJW<<30 \| BS1<<16 \| BS2<<20 \| (presc-1)` from a `CAN_InitTypeDef`; DeInit via `RCC_APB1PeriphResetCmd(CAN1RST/CAN2RST)`. HAL's `HAL_CAN_Init` takes a `CAN_HandleTypeDef` and returns `HAL_StatusTypeDef`. |
  | `USART_Init` | 0x0803b5d8 | calls `RCC_GetClocksFreq`, then the BRR integer-divider using the SPL `25 * apbclock` magic constant with the OVER8 fractional path. HAL/LL use different `UART_DIV_SAMPLING*` macros, no `25×`. |
  | `GPIO_Init` / `GPIO_PinAFConfig` | 0x0806396c / 0x08063a54 | 16-pin loop over `MODER/OSPEEDR/OTYPER/PUPDR` with the `GPIO_InitTypeDef` field order {Pin,Mode,Speed,OType,PuPd}; standalone 3-arg `GPIO_PinAFConfig(GPIOx,src,AF)`. HAL folds AF into `HAL_GPIO_Init` and its struct is {Pin,Mode,Pull,Speed,Alternate}; LL differs again. |

  This also fits the timeline: the P3 FC codebase is ~2014, before ST's LL library existed.
  **Correction to earlier notes:** the register library is *not* "DJI's own raw HAL" and *not*
  LL/HAL — it is ST SPL. The `hal_*` strings (`hal_compass_add`, `comm_imu_init`) are DJI's
  *application-level* sensor/driver abstraction sitting **on top of** SPL, a separate layer from
  the MCU register library. (No `stm32f4xx_hal_*`, `_ll_`, `stdperiph` or `assert_param` strings
  survive — but that only means a release build with `USE_FULL_ASSERT` off, so string absence
  proves nothing either way; the function structure above is what settles it.)
- **Sensor fusion / estimation: DJI FDI-AHRS.** **V** — `FDI ACC/AHRS/BARO/GPS/CTRL` subsystems
  with turn-on events, impact/vibration detection. **No** Kalman/EKF, Madgwick or Mahony strings;
  the attitude/nav estimator is DJI's in-house FDI ("fault detection & isolation" + AHRS), not a
  named open filter. Earlier docs' mention of Butterworth-type filtering stands as the signal
  conditioning; the estimator itself is proprietary. (Absence of a string ≠ absence of the math,
  so "no Kalman" is **V for the name**, **I for the method**.)
- **No borrowed open-source flight-control code.** **V** (absence) — zero
  Betaflight/Cleanflight/MultiWii/Baseflight/iNav/ArduPilot/PX4 strings. The FC is DJI-original.
- **Compiler/toolchain: U.** No `GCC`/`ARMCC`/`IAR`/`Keil` build-ID string survives in the
  stripped image (see "Build metadata" below — a raw `.bin` keeps no `.comment`/symbol table).

## SPL version

Bracketed, not pinned. **F427/437 support entered SPL at V1.1.0 (Jan 2013)**, so the library is
**≥ V1.1.0**; the module carries DJI's own `BUILD Jun 19 2017` string, so it is one of
V1.1.0–V1.8.0 (the F427-capable range up to the last SPL). The **exact patch version is not
recoverable** from this image: the drivers actually present (RCC, GPIO, USART, CAN) are
byte-stable across those minor releases — the inter-version diffs are added peripheral files
(F411/F446) and I2C/DSI/RCC-PLL-min fixes that don't touch these functions — and SPL embeds no
version string (its version is a `#define` macro). Pinning it would need a function that
materially changed between versions, byte-matched against each release; low payoff. **Note:** the
version does **not** matter for naming — every SPL release has identical prototypes and
`*_InitTypeDef` layouts, so the signatures below apply regardless.

## Verified pin / bus map (from SPL callers)

With the SPL init functions identified, their callers name the hardware for free (the port, pin,
AF and peripheral are the call arguments). Decoded against the STM32F427 alternate-function map
(AF9 = CAN, AF12 = SDIO). **V** (decompiled call sites; GPIO port pointers resolved from the
literal pool):

| Bus | Pins | AF | Bring-up fn | Role |
|---|---|---|---|---|
| **CAN1** | PD0 (RX), PD1 (TX) | AF9 | `can1_bringup` 0x08035100 | **V** primary inter-MCU link (FC ↔ m0900/gimbal; the 0x41x CAN IDs) |
| **CAN2** | PB12 (RX), PB13 (TX) | AF9 | `can2_bringup` 0x080353b2 | **V** second CAN bus (CAN2EN clock set) |
| **SDIO** | PC8–11 (D0–D3), PC12 (CK), PD2 (CMD) | AF12 | `sdio_bringup` 0x08039f92 | **V** SD/eMMC flight-data logger |
| **USB OTG_FS** | PA11 (DM), PA12 (DP) | AF10 | `usb_fs_bringup` 0x0803aac4 | **V** DJI Assistant 2 / firmware-upgrade link to the FC (the pins prove OTG_**FS**, not HS) |
| **UARTs** | base + baud from a per-port descriptor | — | `usart_open` 0x080343cc via `uart_table_init` 0x08034bcc | generic open; see runtime-table note below |

Pin config word for these buses is `0x01000302` = `GPIO_Mode_AF`, `GPIO_Speed_100MHz`,
`GPIO_OType_PP`, `GPIO_PuPd_UP`. **DJI uses SPL correctly** — the bring-up order is the textbook
`GPIO_PinAFConfig → GPIO_Init → <periph>_DeInit → <periph>_Init` sequence.

### Why UART baud / port roles are U (runtime-table-driven)

Traced one level up: `uart_table_init` (0x08034bcc) walks a **100-byte-per-entry UART port table
whose base pointer `0x20020a24` is in RAM**, not flash. Each entry holds `{idx@0, USART base@4,
baud@8, TX pin@0xc, RX pin@0xd}`, and `uart_port_init` (0x08034c26) configures the pins and calls
`usart_open` from it. Because the table lives in RAM it is **populated at runtime** — so the USART
base, baud and TX/RX pins are *not* flash constants and cannot be read statically from this image.
The same pattern explains the GPIO caller census: most `GPIO_Init`/`GPIO_PinAFConfig` calls take
their port/pin/AF from loop iterators over descriptor tables, not literals. So *which* USART is
GPS / RC / OSD and at what baud stays **U** without either tracing the code that fills `0x20020a24`
or a live read. The buses whose config *is* a compile-time literal — CAN1, CAN2, SDIO, USB — are
the ones mapped above. SPI CS lines and TIM PSC/ARR sit behind the same runtime descriptors.

**SPL caller census** (how many call sites each identified SPL function has, from
`fc_spl_callers.py`): `GPIO_Init` 11, `GPIO_PinAFConfig` 8, `RCC_AHB1PeriphClockCmd` 13,
`RCC_APB1PeriphClockCmd` 11, `RCC_APB2PeriphClockCmd` 7, `CAN_Init` 2, `USART_Init` 1 (the single
generic open path), `usart_open` 1. Every one of these call sites is now decodable against the SPL
signature — the literal-argument ones are mapped here; the iterator-fed ones resolve only once the
runtime descriptor tables are populated.

## Build metadata (answering "is there linker info in the file?")

No. The module is a **raw loadable image** (`file`: *ARM Cortex-M firmware*, not ELF) — the product
of `objcopy -O binary`, which keeps only loadable sections. So there is **no symbol table, no
`.comment` (compiler/version), no `.note.gnu.build-id`, no linker map** — all of that lives in the
ELF and is dropped. The only in-band metadata is `.rodata` text, and there the useful item is
DJI's own **`BUILD Jun 19 2017 21:40:20`** stamp (plus DJI/Onboard-SDK version strings). No
toolchain or SPL version string exists to read; library identity and version come from code
structure (above), not metadata.

## How to reproduce

```
# decrypt the module (public DJI module key, scheme documented in the script)
python3 scripts/re/xv4_decrypt.py P3X_FW_V01.11.0020.bin m0306 m0306_decrypted.bin
# peripheral base inventory
python3 scripts/re/fc_io_inventory.py m0306_decrypted.bin
# software identity
strings -n5 m0306_decrypted.bin | grep -iE 'uC/OS|FDI (AHRS|ACC|BARO)|mpu6500|IST830|hmc5883'
strings -n5 m0306_decrypted.bin | grep -iE 'betaflight|ardupilot|px4|kalman|stm32f4xx_hal'   # empty
```

Ghidra side: `scripts/re/ghidra/fc_setup.py` builds the project; `fc_clk.py` decompiles the RCC
clock readback; `fc_lib_id.py` decompiles the RCC command family; `fc_lib_id2.py` follows the
clock-enable callers into `CAN_Init` / `USART_Init` / `GPIO_Init` / `GPIO_PinAFConfig` — the five
SPL fingerprints in the table above that identify the register library as ST StdPeriph (vs LL/HAL).
