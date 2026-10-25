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
| FSMC | 0xA0000000 | 3 | external memory bus (**I**: data-logging flash / black-box) |
| USB_OTG_HS | 0x40040000 | 2 | USB device (**I**: DJI Assistant 2 / upgrade + sim link to the FC) |
| TIM1/3/4/5/6/7/8/9/10/11/12/13/14 | — | 1–2 each | motor PWM out (TIM1/TIM8 adv.), misc time-bases |
| USART1/2/3, UART4/5/7/8, USART6 | — | 1 each | serial links (GPS, RC/DBUS, OSD, debug — individual mapping **U**) |
| SPI1/2/3/4/5/6 | — | 1 each | sensor buses (**I**: IMU/baro on SPI; exact CS **U**) |
| I2C1/2/3 | — | 1 each | sensor buses (**I**: compass on I2C) |
| ADC1-3 | 0x40012000 | 1 | analogue (**I**: voltage/current/temp) |
| SDIO | 0x40012c00 | — | (fc_io abs-ref scan showed 43 offset refs: SD/eMMC logging, **I**) |
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
- **HAL: DJI's own, not ST.** **V** — no `stm32f4xx_hal_*`, `_ll_`, `stdperiph`/SPL or
  `system_stm32` strings anywhere; drivers are DJI `hal_*` (`hal_compass_add`, `comm_imu_init`).
  The one clear ST borrow is the RCC clock-readback library (above).
- **Sensor fusion / estimation: DJI FDI-AHRS.** **V** — `FDI ACC/AHRS/BARO/GPS/CTRL` subsystems
  with turn-on events, impact/vibration detection. **No** Kalman/EKF, Madgwick or Mahony strings;
  the attitude/nav estimator is DJI's in-house FDI ("fault detection & isolation" + AHRS), not a
  named open filter. Earlier docs' mention of Butterworth-type filtering stands as the signal
  conditioning; the estimator itself is proprietary. (Absence of a string ≠ absence of the math,
  so "no Kalman" is **V for the name**, **I for the method**.)
- **No borrowed open-source flight-control code.** **V** (absence) — zero
  Betaflight/Cleanflight/MultiWii/Baseflight/iNav/ArduPilot/PX4 strings. The FC is DJI-original.
- **Compiler/toolchain: U.** No `GCC`/`ARMCC`/`IAR`/`Keil` build-ID string survives in the
  stripped image.

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

Ghidra side (clock readback decompile): `scripts/re/ghidra/fc_clk.py` on the project built by
`scripts/re/ghidra/fc_setup.py`.
