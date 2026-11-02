# m0306 (STM32F427 flight controller) naming pass: base gate, driver, DUML table, ISRs, SPL, uC/OS-III (#40, #83)

Static analysis only. Tags: **V** verified (decompile/string/register evidence), **I** inferred, **U** unknown.
Image `firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin` (905,728 B, decrypted; not in repo, see `HANDOVER.md`).
Names are applied from `docs/symbols/m0306*.tsv` + the C block of `docs/symbols/m0306-structs.h`.

## Reproduce
- `python3 scripts/re/m0306_base_check.py` - base gate + TSV address check (run first by the driver)
- `python3 scripts/re/m0306_duml_handlers.py` - decodes the dispatch table into `docs/symbols/m0306-duml-handlers.tsv`
- `python3 scripts/re/m0306_vector_names.py` - vector table into `docs/symbols/m0306-vectors.tsv`
- `python3 scripts/re/m0306_ghidra_names.py` - rebuilds `re/ghidra-projects/m0306_flight_controller/proj/` (headless, ~40 s), applies all TSVs + structs, writes `m0306_dump.txt` (functions, callsites, strings, disassembly, decompilation)
- Pre-script `scripts/re/ghidra/M0306Setup.java` (SRAM 192 KB, CCM 64 KB, APB/AHB1, AHB2, UID, SCS blocks), post-script `M0306Names.java`.
- File precedence (later wins): `m0306.tsv` (legacy), `m0306-data.tsv`, `m0306-params.tsv` (834 `g_config`/`g_real` params), `m0306-vectors.tsv`, `m0306-duml-handlers.tsv`, `m0306-names.tsv`.
- Stall guard: no headless output AND no CPU progress for 60 s (auto-analysis is silent). Logs `tmp/logs/m0306_ghidra_names*.log`.

## 1. Load base 0x08020000 - V
- Vector[0] SP `0x2002ff00`, Reset `0x08021965`; vectors that start like a handler 27/42 at `0x08020000` vs <=3/42 at `0x08000000/4000/8000/10000/40000`.
- Odd literals landing on `push {..,lr}`: 334/1253 (0.27) vs <=0.01 for every other candidate. Reset stub at file offset `0x1964` = `ldr r0,[pc]; blx r0`.
- Image ends `0x080fd200` (fits 1 MB bank). All TSV addresses fall inside the image or SRAM/CCM.

## 2. DUML dispatch table was decoded one entry off - V
- Real layout: 65 x 8 B at `0x080ab43c` = `{u8 cmd_set, u8 cmd_id, u16 pad, u32 handler}` (key precedes its handler). Earlier reading started at `0x080ab440` as `{handler, key}`, pairing each handler with the next entry's key.
- Proof: the handler with log `timezone set:%d` is keyed 3/0x3d (SetTimeZone) only in the new layout; waypoint/hotpoint/follow-me/IOC handlers' log strings match their keys for 28 entries.
- 62 handler functions named `duml_h_<set>_<id>_<name>` (names from `duml_catalog.py` [I]; log-string names [V]). 6 handler ids have no catalog name (`..._unk` [U]). Two null slots (3/0x50, 3/0x54) are reserved ids.
- 3/0x52 appears twice with different handlers (`0x08043c44`, `0x0808cc8a`); 6/0x1c and 3/0x1c share `0x0804429e` (SetDate). Meaning of the duplicate U.
- Table is typed `DumlDispatchEntry[65]` in Ghidra (`g_duml_dispatch_tbl`).

## 3. Vector table and ISRs - V
- Vector word i: exception (i<16) or IRQ i-16 (RM0090). 54 ISRs named `isr_<NAME>`; all unused slots -> `isr_Default` `0x080219a0`.
- CAN: `isr_CAN1_TX/RX0/RX1` = `0x08035300/0803530e/08035358`, `isr_CAN2_TX/RX0/RX1` = `0x080355bc/080355c8/08035614`. Earlier notes called IRQ19-21 "RX0/RX1/SCE" and IRQ63/64 "RX0/RX1": slot numbers are TX/RX0/RX1 (SCE has no handler).
- RX ISRs read the FIFO mailbox (CAN base + 0x1B0/0x1C0) and push a 16 B record with `can_msg_queue_push` into CCM ring queues (`g_can1_rx0_q`, ... `0x10008000..0x1000848c`, struct `CanMsgQueue`).
- ~30 other ISRs are 6-byte stubs that call `g_irq_cb_table[irq].cb(irq, arg)` (`0x20018064`, 8 B/entry, `IrqCb[96]`): software-registered callbacks for USART/UART/I2C/EXTI/DMA.
- OTG_FS ISR `0x08087c3a` -> `usb_otg_fs_irq_handler` `0x08029f26` [I].

## 4. Functions named by evidence
| group | examples | tag |
|---|---|---|
| runtime | `__aeabi_f2d/d2f/dmul/dadd/dsub`, `memcpy`, `irq_save_disable/irq_restore`, `sqrtf`, `isnanf/isinff` | V (bit patterns), memcpy/memclr I |
| debug log | `dbg_log_printf` (423 callers: vsnprintf, DUML-framed log sink), `_short`, `_ch`, `duml_frame_build` | V/I |
| StdPeriph | `flash_unlock/lock/erase_sector/program_word/get_status`, `nvic_init`, `nvic_priority_group_config`, `dma_deinit/clear_flag/get_flag_status`, `syscfg_exti_line_config`, `exti_*`, `adc_common_init`, `sdio_send_command`, `pwr_enter_stop_mode`, `rcc_*`, `can_init`, `usart_init`, `gpio_init` | V by register offsets |
| uC/OS-III | `OSTaskCreate` (13 args, 4 callers), `OS_TaskInitTCB`, `OS_TickTaskInit`, `OS_IdleTaskInit`, `OS_StatTaskInit` | V (strings "uC/OS-III * Task", arg shape) |
| hard fault | `hardfault_print_ufsr/bfsr/mfsr`, `hardfault_dump_tcb/context/task_info/stack/os_state/spec_regs` | V (strings) |
| safety/activation | `fc_activation_state_read` `0x08046d54`, `fc_motor_start_gate` `0x08024b46`, `fc_motor_check_activated`, `fc_motor_can_run`, `fc_auto_takeoff_state_machine` | V (`fc-auth-enforcement-trace.md`) |
| MD5 | `md5_transform` `0x08047c08` (+ `_rounds` `0x08047d5e`) | V (constants `0x6b901122`, `0xfd987193`) |
| compass | `ist8303_*` (init, read_id, set_mode, calc_cali_matrix), `compass_ist83xx_init_all` | V (log strings) |
| CAN queues | `can_msg_queue_push/pop/full`, `can1_tx_pump`, `can2_tx_pump` | V/I |

- Removed stale rows `is_prod_activated`, `check_activation_authority`, `dji_sdk_set_key` from `m0306.tsv`: addresses came from the V01.07.0060 map and land in MD5 code (already corrected in prose, `fc-auth-enforcement-trace.md`; TSV now matches).

## 5. Objects
- Typed: `g_flyc_param_tbl` `FlycExportParam[808]` (0x080ab66c, first `cfg_var_table_size_0`, last `wp_setting.action_on_rc_lost_0`), 829 param-table RAM cells (`m0306-params.tsv` u8/u16/u32), `g_irq_cb_table`, 7 `CanMsgQueue`, `DumlDispatchEntry[65]`.
- Structs applied in Ghidra: `DumlFrame`, `CtrlAgency`, `CtrlMode`, `FlycExportParam`, `DumlDispatchEntry`, `IrqCb`, `CanMsgQueue`.
- `g_isr_nesting_cnt` `0x2001cd7c` [I] (incremented in `isr_SysTick`).

## 6. Not done / U
- Task list of the app (tasks beyond tick/stat/idle/`workqueue_hi_task`) not enumerated: `OSTaskCreate` has 4 direct callers; other tasks use a different creation path (U).
- ~2500 `FUN_*` remain (flight control, nav, FDI, mission code); the 29-entry `fc_Motor_fail` check table and CAN/UART message routing are not named per entry.
- IMU/baro/GPS drivers other than IST8303 not identified; UART/ESC state objects only partly (`g_uart_port_table`).
- Dispatch handlers' payload layouts not decoded; 6 handler ids have no known command name.


## External corroboration (2026-11-02)

- Public o-gs/dji-firmware-tools wiki (community RE, independent of this repo, page edited 2017-05-03): m0306 "is loaded into memory at address 0x8020000" - matches our own base-address finding (0x08020000) exactly, independent cross-check.
- Same page: "No signatures of common libraries were found in the code" - matches this pass's own negative result on library matching (ffc91d6). Supports the owner's point that DJI likely didn't write this library code themselves; it probably came from whatever vendor SDK/BSP the firmware was built against, not a commonly-fingerprinted open-source build. Candidate vendor SDK/BSP identity is U - not pursued this pass.
