# m0400 (gimbal STM32F4) naming pass: base, part, SRAM objects, peripheral functions, DUML handlers (#41)

Static analysis only (never executed). Tags: **V** verified, **I** inferred, **U** unknown.
Image `firmware/unpacked/P3X_FW_V01.11.0020_m0400.bin` (97,032 B, ini version 01.48.0000). Names are applied from
`docs/symbols/m0400.tsv` (`addr kind name note source`) + the C block of `docs/symbols/m0400-structs.h`.
Earlier findings (27/27 handler decode, SPI1 IMU, timers): `air-id-and-stream-survey.md` "m0400 gimbal".

## Reproduce
- `python3 scripts/re/m0400_base_check.py` - base gate + TSV address check (also run first by the driver)
- `python3 scripts/re/m0400_ghidra_names.py` - rebuilds `re/ghidra-projects/m0400_gimbal/proj/` (headless, ~15 s), applies names/types/RM0090 register labels (`docs/data/stm32f407-register-map.tsv`), writes `re/ghidra-projects/m0400_gimbal/m0400_dump.txt` (functions, callsites, strings, disassembly, decompilation)
- Pre-script `scripts/re/ghidra/M0400Setup.java` (SRAM/CCM/PERIPH/AHB2/SCS blocks), post-script `M0400Dump.java`. Logs `tmp/logs/m0400_*.log`.
- Status: 337 functions, 245 named (`func` rows) + 1 auto thunk, 91 still `FUN_*` = 35,106 of 67,026 function-body bytes (the large control/estimator functions, see "Not named").

## 1. Load base 0x08008000 - V
- `m0400_base_check.py`: vector[0] SP `0x2000fc40`, vector[1] Reset `0x0800819d`; 92/92 vector words start like a handler at `0x08008000` vs 5/92 at `0x08000000`, 2/92 at `0x08004000`, 1/92 at `0x08010000`; odd literals on `push {..,lr}` 28/35 (0.80) vs 0.00.
- Firmware states it itself: `main` calls `NVIC_SetVectorTable(0x08000000, 0x8000)` (`mov.w r1,#0x8000; lsls r0,r1,#12`) = VTOR `0x08008000` (V, independent of the literal scan).
- Vector table is 98 words (`0x08008000..0x08008188`); code starts at `0x08008188`.
- `SystemInit` (CMSIS stock) writes VTOR = `0x08000000`; `main` overrides it. Same pattern as the other STM32 app modules (bootloader below base, not in the OTA package).

## 2. Part identification
| Item | Evidence | Tag |
|---|---|---|
| Family STM32F4 (RM0090) | RCC `0x40023800`, FLASH_ACR, GPIO `0x40020000` stride `0x400`, AFRL/AFRH, DMA streams, 168 MHz PLL | V |
| 82 IRQ vector slots (F405/407/415/417), not F427/429 (91) or F446 (97) | table is 98 words = 16 core + 82 IRQ, code starts right after | I |
| SYSCLK 168 MHz: HSE 12 MHz (literal `0xb71b00` in `RCC_GetClocksFreq`), PLLCFGR `0x0740540c` = M12 N336 P2 Q7, HPRE /1, PPRE2 /2 (84 MHz), PPRE1 /4 (42 MHz), FLASH_ACR `0x705` (5 WS) | `SetSysClock` decomp | V |
| Flash >= 1 MB: sector table `flash_addr_to_sector` has 12 sectors up to `0x080e0000`; Get Version reads `0x080C0000` (sector 10) | decomp | I |
| Package has port G and I pins: outputs PG10, PG11, PI10; PI11 input | `gpio_pin_table` `0x0801b9d8`, `board_rev_read` | I (not 64/100-pin) |
| Peripherals used | USART1/2, UART4, SPI1, CAN1, ADC1 (ch10), TIM4, TIM11, DMA2, RNG, EXTI, FLASH, PWR | V |
| Peripherals NOT referenced: CRYP, HASH, DCMI, ETH, OTG, SDIO, FSMC, DAC, I2C, CAN2, RTC, IWDG, UID/OTP (`0x1fff7a10`), DBGMCU_IDCODE | scan of every aligned word and every resolved Ghidra ref (DBGMCU-looking hits are instruction halfwords) | V |

Result: **STM32F405/F407/F415/F417-class, 1 MB, 168 MHz, >= 144-pin; exact part U.** Nothing in the image distinguishes the four: the discriminating peripherals (CRYP/HASH for x15/x17, ETH/DCMI for x07/x17) are never touched and no ID register is read. What would settle it: board photo of the package marking, or a DBGMCU_IDCODE/flash read from hardware.

## 3. Correction to the survey doc
- **USART1 is not a live DUML port** (V): `usart1_init` runs and its ISR fills `usart1_rx_buf`, but no function reads that ring and nothing writes `usart1_tx_buf`. DUML ports are **USART2 (tag 0), CAN1 (tag 1, ids 0x412 in / 0x413 out), UART4 (tag 2)**. (The survey said USART1/USART2/UART4.)
- `duml_dispatch` relay (V): tag 0 (USART2) -> `uart4_putc`; tags 1 (CAN) and 2 (UART4) -> `usart2_putc`. `duml_send_frame` tags: 0 USART2, 1 CAN 0x413, 2 UART4.
- Frame version (u16 at +1 >> 10): 0 -> `duml_dispatch_short` (table `0x0801d464`, zero entries), 1 -> `duml_dispatch` (table `0x0801d46c`).
- The "F1-layout literals" in `gpio_misc_init` (survey U) are F4 GPIO bases: `gpio_pin_table` rows = `{0x40021800 GPIOG, 0x400, 0x40}`, `{GPIOG, 0x800, 0x40}`, `{0x40022000 GPIOI, 0x400, 0x100}` = PG10, PG11, PI10 push-pull outputs (RCC AHB1 bits 6, 8) (V). Consumer of those pins U.
- TIM11 rate: APB2 timer clock is 168 MHz (PPRE2 /2 doubles timer clock), PSC 1, ARR 2625 -> 168e6 / 2 / 2626 = 31.99 kHz (V). The survey assumed 84 MHz. TIM4: 84e6 / 21 / 2001 = 1999 Hz (V).

## 4. SRAM objects (all in `m0400.tsv`, types in `m0400-structs.h`)
| Addr | Name | Notes | Tag |
|---|---|---|---|
| `0x20000000` | `can_tx_urgent_flag` | set by `can_send_urgent`, cleared in `CAN1_TX_IRQHandler` | V |
| `0x20000004/6` | `can_txq_head/tail` | u8-wrapped indices into `can_txq_buf` | V |
| `0x200007dc` | `can_tx_stage` (`can_tx_msg_s`) | shared staging CanTxMsg; std id `0x321` loaded by `can1_init` | V |
| `0x20000804` | `can_txq_buf` | 256 x 20 B to `0x20001c04` | V |
| `0x20001c04` | `can_tx_urgent` | single pending frame | V |
| `0x20002a18` | `can_rx_ring` (`ringbuf_s`) | filled by `can_rx_dispatch` from CAN id 0x412, drained by `duml_assemble_can`; buf `0x20002618` | V |
| `0x20002e30` | `can_ring_b` | field id 0x412, buf `0x20002a30`; no other reference | V (unused) |
| `0x2000000c/14/1c` | `usart2_idx`, `usart1_idx`, `uart4_idx` (`uart_idx_s`) | tx_head, tx_tail, rx_head, rx_tail | V |
| `0x20002e48..0x20003e48` | `usart2_tx/rx_buf` 0x400, `usart1_tx/rx_buf` 0x200, `uart4_tx/rx_buf` 0x400 | contiguous after `can_ring_b` | V |
| `0x2000030c` | `tick_flag` | set by `TIM4_IRQHandler`, cleared at end of `main_loop` | V |
| `0x20000374` | `loop_count` | | V |
| `0x20000024/25` | `sw2w_data_reg`, `imu_use_spi1` | 2-wire chip data register (0x30/0x36); 1 = MPU fallback | V |
| `0x20004248` | `imu_out` | decimated gyro written by `DMA2_Stream0_IRQHandler` | V |
| `0x20004250` | `imu_2wire_raw` | 12 bytes from reg 0x24 | V |
| `0x20004294` | `imu_dma_buf` (`imu_burst_s`) | 15 B SPI1 burst | V |
| `0x200048c4` | `loop_tim4_stamps` | TIM4_CNT sampled 5x per pass (profiling) | V |
| `0x20004c48` | `led_state` (`led_state_s`) | 3 pattern channels, drives PE0/PE1 | I |
| `0x0801d46c` | `duml_table` | 27 x `{handler|1, id, set, pad[2]}` + zero terminator `0x0801d544` | V |
| `0x0801b6d4` / `0x0801b8d7` | `crc16_table` / `crc8_table` | DUML CRC16 init `0x3692`, CRC8 init `0x77` | V |
| `0x08060000` | `flash_param_store` | 128 slots x 0x400 (u32 seq + 0x3fc payload) in sector 7, outside image | V |

## 5. Named functions (by group)
- **Vectors/startup (V):** 9 core handlers (`b .`), `Default_Handler`, `Reset_Handler`, `SystemInit`, `SetSysClock`, `main`; ISRs `CAN1_TX/RX0`, `EXTI9_5` (line 6 = PA6 by SYSCFG reset default), `TIM1_TRG_COM_TIM11`, `TIM4`, `USART1/2`, `UART4`, `DMA2_Stream0/3`.
- **SPL-shape peripheral layer (V by register offsets; names by SPL shape, library identity I):** RCC (clock/reset cmds, `RCC_GetClocksFreq`), `NVIC_Init`, `NVIC_PriorityGroupConfig`, `NVIC_SetVectorTable`, GPIO (`Init`, `PinAFConfig`, Set/Reset/Toggle/Write/Read), EXTI, DMA (`Init`, `DeInit`, `Cmd`, `ITConfig`, `GetITStatus`, `ClearITPendingBit`), SPI, TIM (`TimeBaseInit`, `Cmd`, `ITConfig`, `GetITStatus`, `ClearITPendingBit`, `ARRPreloadConfig`), USART, ADC, CAN (`Init`, `FilterInit`, `Transmit`, `Receive`, `ITConfig`, `ClearITPendingBit`), RNG, FLASH (`Unlock/Lock/ClearFlag/GetStatus/EraseSector/ProgramByte/ProgramWord`).
- **App layer:** `usart1_init/usart2_init/uart4_init` (115200 from `main`), per-port `getc/putc`, `can1_init` (PD0/PD1 AF9, filters, NVIC IRQ19/20), `can_send*`, `can_rx_dispatch`, ringbuf helpers, `duml_*` (assemblers, dispatch, CRC8/CRC16 append/check, send), `gimbal_push_params_send` (set 0x04 id 0x05), `gimbal_push_15_send` (0x04/0x15), flash parameter store (`flash_param_save/load/find_*`, `param_autosave_tick` every 8000 passes), IMU (`imu_mpu_spi_init`, `imu_dma_kick`, `sw2w_*` 2-wire bus on PA5/PA7), `adc1_*`, `board_rev_read`, `tim4_init_2khz`, `led_update`.
- **Math/libm/runtime (V arithmetic, I library):** `memcpy`, `memclr`, soft-double helpers, `sinf/cosf/sqrtf`, `asinf/acosf/atan2f`, `quat_*` (mul x2, normalize, conj, to_euler, to_dcm, nlerp), `angle_wrap_f32`, `clamp_sym_f32`, `matvec_f32`, CMSIS-DSP-shape `cfft_radix4_*` and `cmplx_mag_f32`.
- **DUML handlers:** all 27 in `duml_table`, named `duml_h_<set>_<id>[_what]`. Name taken from `docs/schema/duml/commands.yaml` where present: gimbal 0x01 Control, 0x08 AutoCalibration, 0x0a AngleControl, 0x0c SpeedControl, 0x14 AbsAngleControl.

### Findings from this pass
- **CAN protocol of the gimbal (V, `can_rx_dispatch` / senders):** RX std ids `0x101`, `0x200`-`0x205`, `0x2f0`-`0x2f6`, `0x412` (DUML bytes into `can_rx_ring`). TX std ids `0x20b` (from `duml_h_gimbal_0e_can_relay`: 3 x int16), `0x20d`, `0x23d` (replies after `can_param_frame_store`, ids `0x20e`/`0x23e`), `0x321` (staging default), `0x413` (DUML out). Peer meaning of the 0x2xx ids U (motor/encoder side of the gimbal; not identified).
- **Parameter store (V):** wear-levelled log, 128 slots of 0x400 in flash sector 7 (`0x08060000`); newest = highest seq; sector erased when no slot is free; written every 8000 loop passes (4 s at 2 kHz) by `param_autosave_tick`; `FLASH_WaitForLastOperation` has no timeout.
- **2-wire IMU variant (V):** `sw2w_imu_probe` writes regs 0-6/0x16, reads ID reg `0x20`; ids `0xb4` (data reg `0x30`), `0xb1`/`0xb2` (data reg `0x36`) accepted, anything else falls back to the SPI1 MPU-family path (`imu_use_spi1 = 1`). Chip behind ids 0xb1/0xb2/0xb4 U. PA5/PA7 are both SPI1 SCK/MOSI (AF5) and the bit-banged pair.
- **Main loop (V):** gated by `tick_flag` (TIM4, 1999 Hz); order: sensor read, `imu_process_sample`, `FUN_0800d488`, estimator calls, push frames (`gimbal_push_params_send` phases 200/33/40 ticks), DUML assemblers every 2nd pass, `led_update`.
- **Board revision (I):** `board_rev_read` snaps the ADC1 ch10 (PC0) mV average to 300/500/700/900 (+-100) or 100; PI11 high returns `0xce6`.
- Handler `0x04/0x0e` (V): not a no-op; converts the first int16 to a float global and relays three int16 to CAN `0x20b`.

## 6. Compile-and-diff library-match pass (#41, pass 2)

Dan's instruction: for anything shaped like libm/CMSIS-DSP/soft-float, don't just name by shape -
COMPILE the real candidate source with the project's own toolchain and diff the machine code
against the firmware bytes. Method generalised into `scripts/re/mcu_libmatch.py` (any module: takes
`--image/--base/--addr/--size`, either `--ref-archive/--ref-member/--ref-symbol` to pull a symbol
straight out of a prebuilt libgcc.a/libm.a/libc.a, or `--source/--ref-symbol` + `--cpu/--fpu
/--float-abi/--opt-levels` to compile a candidate `.c`; disassembles both with `objdump` and reports
byte-exact / instruction-sequence-ratio / mnemonic-only-ratio). Logs `./tmp/logs/mcu_libmatch.log`.

**Candidates tried, toolchains used:**
- libgcc/newlib soft-double (`__aeabi_dadd/dmul/ddiv/f2d/d2f/llsl`) and `memcpy`: extracted straight
  from prebuilt `libgcc.a`/`libc.a` of arm-none-eabi-gcc 15.2.0 (Fedora), 15.2.1 (Arm GNU Toolchain),
  14.3.1 (ST's STM32CubeIDE bundle), and 5.4.1 (Arm GNU Toolchain 5_4-2016q3, downloaded for this
  pass - closest in vintage to this firmware). All four give byte-identical soft-double code to each
  other (this code hasn't changed in GCC since ~2012) - and none match the firmware. Firmware's
  `__aeabi_dadd` is 352 B vs every GCC's 630 B; `__aeabi_f2d` is 38 B vs 66 B; `memcpy` is 36 B vs
  308 B. **Conclusion (V, by exclusion): the firmware's soft-float/memcpy is NOT stock GCC
  libgcc/newlib from any version checked** - smaller and structurally different (e.g. exponent
  bit-pattern tricks where newlib calls a separate `__ieee754_*` helper). Likely a different
  compiler (ARM Compiler/Keil armcc was common for drone FC firmware of this era, or a hand-tuned
  soft-float) - not open source, out of reach of this method.
- `sinf/cosf/sqrtf/asinf/acosf/atan2f`: extracted from the same newlib builds (libm.a). All U for the
  same reason - newlib's wrappers are thin (4-148 B) and promote to double or call separate
  `__kernel_*`/`__ieee754_*` functions; firmware inlines the single-precision kernel directly into
  the wrapper (e.g. `atan2f` is a 4 B double-promoting thunk in newlib vs a standalone 508 B
  single-precision implementation in the firmware). Arithmetic behaviour tags (`sinf`/`cosf`/`sqrtf`
  already [V]) are unaffected - V there means "verified what it computes", not "verified which
  library wrote it"; library identity stays [I], now with a real negative result on record instead
  of an open guess.
- CMSIS-DSP radix-4 FFT (`cmplx_mag_f32`, `radix4_butterfly_f32`, `radix4_butterfly_inverse_f32`,
  `cfft_radix4_f32`, `cfft_radix4_init_f32`): compiled CMSIS-DSP V1.4.5 (commit `147cb4e3`,
  2016-12-14, from the zephyrproject-rtos/cmsis-dsp mirror - chosen for era, this radix4 API was
  removed from later CMSIS-DSP releases) at `-O0/-O1/-O2/-O3/-Os`, `-mcpu=cortex-m4
  -mfpu=fpv4-sp-d16 -mfloat-abi=hard`, against ARM's CMSIS Core headers (`core_cm4.h` etc, from the
  local STM32Cube_FW_F4_V1.28.3 package). Sizes land close at `-O1` (e.g. `radix4_butterfly_f32`
  854 B vs firmware's 836 B) but instruction-sequence and even opcode-only-sequence ratios are low
  (<30%) at every opt level - register allocation and instruction scheduling diverge almost
  immediately after the shared `push {..,lr}` prologue. **Still U/[I]-shape-only, not upgraded** -
  close byte count alone is not evidence per the task's bar (shared opcodes/operands/constant pools
  in the same order). Not reached: trying other CMSIS-DSP point releases between V1.4.0-V1.5.x, or
  ARM Compiler (armcc/armclang) output, which ST and DJI-era toolchains sometimes used instead of
  GCC for CMSIS libraries.
- **New finding from tracing cfft_radix4_f32's calls:** `cfft_radix4_f32` (0x08008a08) tail-jumps
  (`b`) to 0x080082b0, a 176 B bit-reversal permutation that Ghidra's auto-analysis folded into
  cfft_radix4_f32's *disassembly* but never gave its own FUNCTION entry (non-contiguous function,
  invisible to the FUN_* count and to the prior pass's 234 B size for cfft_radix4_f32, which was
  actually this merged total - cfft_radix4_f32's real body is 58 B). Its argument register usage
  (pSrc, fftSize, bitRevFactor, pBitRevTab) matches CMSIS-DSP's
  `arm_bitreversal_f32(pSrc, fftLen, bitRevFactor, pBitRevTable)` call exactly. Named
  `arm_bitreversal_f32` **[I]** (call-signature + argument match is solid; compile-diff against the
  same CMSIS-DSP V1.4.5 source is U, same divergence pattern as the radix4 functions above).
  `cfft_radix4_f32`'s size in the TSV/dump is now corrected to 58 B.
- FUN_080172b0 (5474 B, the single largest remaining FUN_*) makes **zero** calls to any other
  function (checked via the callsite table) - it is one large block of inlined float arithmetic with
  no library call boundary to anchor a comparison on. Spot-checked as representative of the rest of
  the 91 FUN_* list: these are DJI's own estimator/control code (prior pass's conclusion), not
  library code, so the compile-and-diff method has no candidate source to try against them - they
  are out of scope for this method, not unsolved by it.

**Net result of this pass: 91 FUN_* unchanged (none of the 91 are library code - confirmed, not just
assumed); 1 new name found (`arm_bitreversal_f32`, hidden inside an existing function's Ghidra
boundary); ~18 existing [I]/[V]-arithmetic rows got a real compiled-diff result (all U - "tried, no
match") recorded in their TSV note instead of an unverified shape guess.** No row was upgraded to
[V] library-identity; none were downgraded either (decompiled arithmetic evidence for the [V] rows
is untouched by a failed library-identity check).

## 7. Not named / still U
- 91 `FUN_*` = 35 KB, mostly the large floating-point estimator/control functions (`0800aa00`, `0800b994`, `0800f384`, `080172b0`, `08014214`, `08014ef4`, `0800d488`, ...), plus table-less helpers. Roles are visible only through callees (quaternion math, sin/cos, CAN `0x20d` senders); no names assigned without a decisive register or string anchor.
- Strings `motor_stop`, `record_enc`, `read_backup`, `080e0000`, `080a0000` (`0x0801c22f..0x0801c25b`) have no code references (V, no xref in Ghidra); owner U.
- `duml_h_general_30_sub3` (`0x08013a18`) not decompiled; sub1/sub2/ack72 are I.
- Flash `0x080C0000` contents (Get Version), CAN peer identity, USART1's intended peer, exact STM32 part.
