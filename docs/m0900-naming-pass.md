# m0900 (STM32F103 air radio MCU) naming pass: base, SRAM objects, helpers, CAN inventory (#36, #83)

Static analysis only (never executed). Tags: **V** verified, **I** inferred, **U** unknown.
Image `firmware/P3X_FW_V01.11.0020_m0900.bin` (75,796 B, SHA-256 `72156b4b...`). Names are applied from
`docs/symbols/m0900_V01.11.0020.tsv` (`addr kind name note source`) + the C block of `docs/symbols/m0900-structs.h`.

## Reproduce
- `python3 scripts/re/m0900_base_check.py` - base gate + TSV address check (also run first by the driver)
- `python3 scripts/re/m0900_ghidra_names.py` - rebuilds `re/ghidra-projects/m0900_radio/proj/` (headless, 12 s), applies names/types, writes `re/ghidra-projects/m0900_radio/m0900_dump.txt` (functions, callsites, strings, disassembly, decompilation)
- `python3 scripts/re/m0900_can_ghidra.py` - same + literal-pool scan of CAN1 / CAN SRAM objects (`tmp/m0900_can_ghidra/literal_hits.txt`)
- `python3 scripts/re/m0900_can_closure_check.py`, `m0900_can_routing_decode.py`, `m0900_can_channels.py` - CAN checks (all at the corrected base)
- Pre-script `scripts/re/ghidra/M0900Setup.java` (SRAM/PERIPH/SCS blocks), post-script `M0900Dump.java` (TSV + structs + dump). Logs: `tmp/logs/m0900_ghidra_names*.log`.

## 1. Load base is 0x08008000 - V
- `python3 scripts/re/m0900_base_check.py` prints (2026-11-02): vector[0] SP `0x20004cb8`, vector[1] Reset `0x08008201`; vectors that start like a handler 37/37 at `0x08008000` vs 1/37 at `0x08000000`; odd literals landing on `push {..,lr}` 56/83 (0.67) vs 0/93 (0.00); Reset stub at file offset `0x200` = `ldr r0,[pc]; blx r0`.
- The 2026-10-24 CAN pass loaded at `0x08000000`: every address in `dataflow.md` §7-7.11 was `0x8000` low. Corrected in place (list below). `m0900-buses.tsv`, `m0900-can-channels.md` and the symbol TSV were already at `0x08008000`.
- Old CAN-pass `vec_36 @ 0x0800b23c` was unrelated code (file offset `0xb23c` = real `0x0801323c`), hence its "unreliable" decompile; the real RX ISR at `0x0800b23c` decompiles cleanly.

Corrected addresses (old wrong-base -> real):

| old | real | name |
|---|---|---|
| `0x08000620` | `0x08008620` | `CAN_DeInit` |
| `0x08000646` | `0x08008646` | `CAN_Init` |
| `0x0800072e` | `0x0800872e` | `CAN_FilterInit` |
| `0x080008a0` | `0x080088a0` | `CAN_Transmit` |
| `0x08003298` | `0x0800b298` | `can1_tx_irq` (was `can_tx_pump`) |
| `0x0800331c` | `0x0800b31c` | `can_init` |
| `0x080033ec` | `0x0800b3ec` | `can_queue_init` |
| `0x08003468` | `0x0800b468` | `can_enqueue_and_tx` |
| `0x080034e6` | `0x0800b4e6` | `can_queue_reset` |
| `0x080034f0..f8` | `0x0800b4f0..f8` | CAN literals (`CAN1`, `can_tables`, `can_state`) |
| `0x08004142` / `0x08004274` | `0x0800c142` / `0x0800c274` | `get_board_version` / `ring_push` |
| `0x08005b00` | `0x0800db00` | `main` (was "app_init") |
| `0x080093a8` / `0x08009828` | `0x080113a8` / `0x08011828` | CAN queue setup (0x412/0x413) / `can_aux_init` (0x414/0x415) |
| `0x080098d0` / `0x080098e4` | `0x080118d0` / `0x080118e4` | `packet_send` / its `tbb` table |
| `0x0800998a` / `0x08009a8e` | `0x0801198a` / `0x08011a8e` | `duml_dispatch` / `duml_parser_feed` |
| `0x0800941c` / `0x08009876` | `0x0801141c` / `0x08011876` | `route_path_a` / `can414_send` |
| `0x08009882` | `0x08011882` | `can415_pump` |
| `0x080030a4` / `0x0800a61c` | `0x0800b0a4` / `0x0801261c` | `uart_send` / `send_usart1` |
| `0x0800c808` | `0x08014808` | `__aeabi_dmul` (94 callers) |

Unchanged (real already): `can_rx0_handler` `0x0800b23c`; m0400 (gimbal) and m0306 (FC) addresses in `dataflow.md` §7.10-7.11 belong to other chips.

## 2. Corrections to earlier names (V)
- `exti_cb1_*`, `exti_cb_table*` are TIM3 / TIM2 interrupt callbacks (`tim3_irq` vector 45, `tim2_irq` vector 44; base `0x40000400` / `0x40000000`), not EXTI. Only `exti1_cb_ptr` (vector 23, EXTI1) is EXTI.
- `duml_parser_init` argument order is `(parser, frame_cb, buf, bufsize)`.
- `fpga_link_payload_descramble` XOR key is not always zero: see section 5.
- Duplicate TSV rows removed (`cmd_exec_key07_set00`=`duml_enter_loader` 0x08012320, `cmd_exec_set13_cmd08`=`duml_update_confirm` 0x080123b8, `duml_req_0904`=`duml_cmd_0904` 0x080110f2).

## 3. SRAM objects (V unless tagged) - type/size applied in Ghidra
Layouts in `docs/symbols/m0900-structs.h`. Full list: `kind=ram` rows of the TSV.

| address | size | type | name | role | tag |
|---|---|---|---|---|---|
| `0x20000014` | 0x7b | `UartIo` | `uart_io` | per-port busy flags + 6 byte rings (USART1/2/3 tx,rx) at +3,+0x17,+0x2b,+0x3f,+0x53,+0x67 | V |
| `0x20000090` | 0xc | `CanState` | `can_state` | tx_idle flag, tx/rx queue counts | V |
| `0x200015d0` | 0x68 | `CanTables` | `can_tables` | rx[13] then tx[13] `CanQueue*` | V |
| `0x20002330` | 0x1c | `CanQueue` | `can412_tx_q` | StdId 0x412 TX, ring 512 B at `0x20001f30` | V |
| `0x2000234c` | 0x1c | `CanQueue` | `can413_rx_q` | StdId 0x413 RX (filter bank 0), ring 512 B at `0x20002130` | V |
| `0x20002538` | 0x1c | `CanQueue` | `can414_tx_q` | StdId 0x414 TX, ring 64 B at `0x200024b8` | V |
| `0x20002554` | 0x1c | `CanQueue` | `can415_rx_q` | StdId 0x415 RX (filter bank 1), ring 64 B at `0x200024f8` | V |
| `0x20002368` / `0x20002378` | 0x10 / 0x140 | `DumlParser` / u8[] | `can413_parser(_buf)` | DUML parser for 0x413 | V |
| `0x20002570` / `0x20002580` | 0x10 / 0x40 | `DumlParser` / u8[] | `can415_parser(_buf)` | DUML parser for 0x415 (64 B frame cap) | V |
| `0x20002620` / `0x20002630` | 0x10 / 0x140 | `DumlParser` / u8[] | `usart1_parser(_buf)` | DUML parser for USART1 | V |
| `0x20001ce8`, `0x20001df8` | 0x10 (+0x100 buf) | `DumlParser` | `relay_parser_rf`, `relay_parser_usart3` | parsers in `fpga_uart_to_fc_relay`; rings `0x20000144` (RF) and `0x2000007b` (USART3 RX) | V |
| `0x20000144` | 0x14 | `ByteRing` | `rf_rx_ring` | 0x1c-B payloads from `fpga_link_payload_descramble` | V |
| `0x200001d0..0x200009cf` | | u8[] | `usartN_tx/rx_dma_buf` | DMA buffers: USART1 tx 0x100 rx 0x200, USART2 tx 0x100 rx 0x200, USART3 tx 0x100 rx 0x100 | V |
| `0x200000dc` | 8 | `TickState` | `tick_state` | 5/20/100 ms flags + counter (SysTick 1 ms: LOAD 71999 at 72 MHz) | V |
| `0x200000e8` | 0xc | `StatusState` | `status_state` | status word (cs0 cmd 0xf1 payload), tick, last sent | V |
| `0x200016c4` | 0x78 | `AssocEntry[20]` | `assoc_table` | keyed ID table, aged every 25 ticks, sent as cs0 cmd 0xf9 | V |
| `0x2000009c` | 8 | `DinDebounce` | `din_debounce` | debounce of a board-dependent input (boards 4/5 PA2, 6/2 PC13, 7 PA11); role U | V/U |
| `0x200000d8` | 1 | u8 | `board_version` | board straps; gates CAN/UART routing | V |
| `0x20001b00` | 24 | u8[24] | `radio_session_key` | random 3DES key (radio_state_s+0x4c) | V/I |
| `0x20001b18` | 8 | u8[8] | `link_xor_key` | XOR key of `fpga_link_payload_descramble` (radio_state_s+0x64) | V |
| `0x2000175c` | 0x1b | u8[27] | `link_rx_record` | last good link frame fields | I |
| `0x200019b8` | 0xfc | u8[252] | `radio_cfg_page_s` | flash page `0x7b00` copy or board default | V |
| `0x20002770` | 0xdc | u32[55] | `rand_ring` | lagged-Fibonacci `rand` state | I |

Receiver-type jump table (31-entry `tbb`, `0x080118e4`, code-side) and dispatch tables (`0x0801a120`, `0x0801a160`) are in the TSV as `table` rows; board-code variable = `board_version`.

## 4. CAN message inventory (V unless tagged)
Bus: CAN1, PA11 RX / PA12 TX, 1 Mbit/s (BRP 3, BS1 6 tq, BS2 5 tq at PCLK1 36 MHz), `can_init` runs only on boards 2/4/5/6. CAN2 literal count in the image: 0.

| StdId | dir | board gate | frame content | who produces / consumes |
|---|---|---|---|---|
| `0x412` | TX | 2/4/5/6 | DUML byte stream, DLC = min(ring bytes, 8), IDE=0, RTR=0 | `route_path_a` 0x0801141c for receiver types 1,4,8,15 (board 7 sends these over USART1/2) |
| `0x413` | RX | 2/4/5/6 | DUML byte stream | exact-match filter bank 0 (FIFO0, 32-bit mask `0xffff`/`0xffff`, IDE/RTR must be 0) -> `can413_pump` -> `duml_dispatch` |
| `0x414` | TX | 2/4/5/6 for sending; queue exists on all | DUML byte stream | `can414_send` 0x08011876, reached only from `packet_send` for receiver type 30 |
| `0x415` | RX | queue + filter on all boards; bus init 2/4/5/6 | DUML byte stream, parser buf 64 B | filter bank 1 -> `can415_pump` -> `duml_dispatch` |

- No other StdId is sent or accepted (V): `CAN_FilterInit` has one call site (`can_queue_init`, 2 RX queues); `CAN_Transmit` has two callers (`can1_tx_irq`, `can_enqueue_and_tx`); CAN1 register-block literals: 3 in the whole image; CAN2: 0; `movt`: 0 of 64 `movw` (`m0900_can_closure_check.py`).
- Non-DUML traffic: none (V). Queue rings are written only by `can_enqueue_and_tx` (TX) and `can_rx0_handler` (RX); both sides run `duml_parser_feed` on the byte stream. DUML frame boundaries are not aligned to CAN frames; no CAN-level framing, sequence or checksum beyond the DUML CRC8/CRC16.
- Overflow (V): `ring_push` has no full check; a producer faster than the 1 Mbit/s drain overwrites unread bytes silently.
- DUML messages that m0900 itself originates toward CAN receiver types (all built by `duml_build_send` 0x08011c1e, sender type 9, sent via `packet_send`; fields = receiver type / cmdset / cmd / payload length):

| rx type (queue) | cmdset/cmd | len | producer | tag |
|---|---|---|---|---|
| 1 CAMERA (0x412) | 1/0x01 | 10 | `link_status_push` 0x0800e41a | V call, I meaning |
| 1 CAMERA (0x412) | 6/0x50 | 6 | `link_status_push` | V call, I meaning |
| 1 CAMERA (0x412) | 2/0x7c | 2 | `link_event_poll` 0x08011682 (5 senders, shared seq) | V call, I meaning |
| 4 GIMBAL (0x412) | 1/0x01 | 10 | `link_status_push` | V call, I meaning |
| 4 GIMBAL (0x412) | 4/0x01, 4/0x06 | 8 | `gimbal_rc_send` 0x08011540 (4 x 11-bit fields, 0x400 neutral, chain-scrambled with seed = seq) | V call, I meaning |
| 8 DM368 (0x412) | 9/0x03 | 5 | `radio_status_push` 0x0801029e (every 50 ticks) | V call, I meaning |
| 30 (0x414) | none originated | | only forwarded frames | V |

- Forwarded traffic (V): any DUML frame arriving on USART1/USART3/0x413/0x415 with no `duml_dispatch` match and receiver type 1,4,8,15 (0x412) or 30 (0x414); `duml_set03_id43_fwd` re-addresses FC OSD pushes (set 3 id 0x43) to type 2 then 1 (type 1 -> 0x412); `duml_set03_id42_fwd` to type 4 (0x412).
- Not CAN (V): receiver types 3,5,10,11,12,18,21,23 and 17 -> USART1; 2,6,13,14,16,20,22 -> USART3; status pushes `status_report_tick` (cs0 cmd 0xf1/0xf9) go to types 2 (USART3) and 3 (USART1).
- Peers: who answers on 0x413/0x415 and whether 0x414/0x415 are live on a real bus: **U** (needs a passive capture, `m0900-can-channels.md` §6).

## 5. Findings from the helper pass
- **DES in the air MCU (V code, I purpose).** `des_key_schedule` 0x0800cc08, `des_crypt_block` 0x0800cd4c, `des3_*`; S-box table `0x08015e5c` row 0 of S1 = 14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7 (FIPS 46-3).
- **The link XOR key is written at runtime (V).** `radio_session_key_init` 0x0800ea34 (called once from `fpga_link_rx_poll` when FPGA reg `0xE9` bits[1:0]==3, guard byte `0x2000015f`): `srand(SysTick VAL)`; 24 `rand()` bytes -> `radio_session_key` 0x20001b00; 3DES-encrypt the constant `78 65 54 87 62 23 36 47` -> `link_xor_key` 0x20001b18, which `fpga_link_payload_descramble` XORs over bytes 1..0x37. Supersedes the earlier "key always zero" result (`HISTORY.md` 2026-11-02).
- **Key material leaves the MCU (I).** `radio_status_push` 0x0801029e copies `radio_session_key` (24 B) into a 0x43-byte cs9/cmd0 message to receiver type 0xE (OSD -> `uart_send(3)` -> FPGA UART); 5 key bytes are swapped with `radio_state_s[0..4]` and relocated to the tail. Whether those frames reach the air link unmodified is U. Reproduce: `grep -n "radio_session_key" docs/symbols/m0900_V01.11.0020.tsv`; decompile in `m0900_dump.txt` (`---- radio_status_push`).
- `status_report_tick` 0x0800c34a is an m0900-originated periodic DUML report (cs0 cmd 0xf1 four-byte status word to APP and FLYC; cs0 cmd 0xf9 five-byte records of `assoc_table` to APP) (V). Ties to bits set by `status_flags_set/clear` (link CRC/lock states; bit meanings U).
- TIM2 is a 14 ms frame timer with four compare slots at 999/5999/8999/13499 us (V); TIM3 is the same period with update callback (V).

## 6. Helper functions named this pass (top 64 by caller count, new names only)
186 new function names, 45 new SRAM objects, 8 renamed (TIM/EXTI), 2 notes corrected. Soft-float/libc/libm/StdPeriph names follow ABI/SPL conventions; reg offsets verified, identity of soft-float and libm routines is I.

| address | name | callers | tag |
|---|---|---|---|
| `0x08014808` | `__aeabi_dmul` | 94 | I |
| `0x08014258` | `__aeabi_dadd` | 57 | I |
| `0x08014c54` | `__aeabi_dsub` | 53 | I |
| `0x08015224` | `__aeabi_fmul` | 26 | I |
| `0x08011c1e` | `duml_build_send` | 25 | V |
| `0x08014e80` | `__aeabi_fadd` | 25 | I |
| `0x080094e2` | `GPIO_Init` | 22 | V |
| `0x08014a70` | `__aeabi_drsub` | 22 | I |
| `0x08008e32` | `DMA_Cmd` | 21 | V |
| `0x080098f2` | `RCC_APB2PeriphClockCmd` | 20 | V |
| `0x080143d0` | `__aeabi_ddiv` | 19 | I |
| `0x08015582` | `scalbn` | 16 | I |
| `0x0800c24c` | `ring_count` | 13 | V |
| `0x0800c294` | `ring_pop` | 13 | V |
| `0x08011c0a` | `duml_parser_put_byte` | 13 | V |
| `0x08012a3a` | `set_errno` | 12 | V |
| `0x08015194` | `__aeabi_ui2f` | 12 | I |
| `0x080128aa` | `__aeabi_memcpy` | 11 | I |
| `0x08015164` | `__aeabi_i2f` | 11 | I |
| `0x08008e58` | `DMA_SetCurrDataCounter` | 9 | V |
| `0x0800a860` | `USART_ITConfig` | 9 | V |
| `0x0800c274` | `ring_push` | 9 | V |
| `0x0801495c` | `dfp_special_case` | 9 | I |
| `0x08014f68` | `__aeabi_fdiv` | 9 | I |
| `0x0800a6f6` | `TIM_ClearITPendingBit` | 8 | V |
| `0x0800c320` | `status_flags_set` | 8 | V |
| `0x0800e5fa` | `bitrev11` | 8 | V |
| `0x08015326` | `ffp_special_case` | 8 | I |
| `0x08015434` | `__aeabi_fsub` | 8 | I |
| `0x08009038` | `FLASH_WaitForLastOperation` | 7 | V |
| `0x08012934` | `__aeabi_memcpy4` | 7 | I |
| `0x080150ec` | `__aeabi_f2iz` | 7 | I |
| `0x08008d04` | `DMA_DeInit` | 6 | V |
| `0x08008dde` | `DMA_Init` | 6 | V |
| `0x08009904` | `RCC_APB1PeriphClockCmd` | 6 | V |
| `0x0800a6de` | `TIM_GetITStatus` | 6 | V |
| `0x0800a890` | `USART_DMACmd` | 6 | V |
| `0x08012f68` | `poly_eval_double` | 6 | I |
| `0x080134b4` | `cos` | 6 | I |
| `0x0800c33a` | `status_flags_clear` | 5 | V |
| `0x0800cc08` | `des_key_schedule` | 5 | V |
| `0x0800e820` | `radio_hop_seed_update` | 5 | I |
| `0x080105d2` | `radio_state_get_6c` | 5 | V |
| `0x08011e54` | `duml_crc16_calc` | 5 | V |
| `0x080140f8` | `sin` | 5 | I |
| `0x0801473a` | `__aeabi_i2d` | 5 | I |
| `0x08009916` | `RCC_APB2PeriphResetCmd` | 4 | V |
| `0x08009928` | `RCC_APB1PeriphResetCmd` | 4 | V |
| `0x0800b4e6` | `can_queue_reset` | 4 | V |
| `0x0800b75a` | `gpiob_pb89_set` | 4 | V |
| `0x0800b776` | `gpiob_pb89_toggle` | 4 | V |
| `0x0800b7cc` | `pa1_pulse_strobe` | 4 | V |
| `0x0800ba14` | `tim2_cb_table_set` | 4 | V |
| `0x0800bc16` | `copy_bytes_src_dst` | 4 | V |
| `0x08011df8` | `duml_crc8_calc` | 4 | V |
| `0x080129dc` | `__aeabi_memclr4` | 4 | I |
| `0x08012e6c` | `__kernel_cos` | 4 | I |
| `0x08013014` | `__kernel_sin` | 4 | I |
| `0x08015124` | `__aeabi_f2uiz` | 4 | I |
| `0x08008b68` | `CAN_ITConfig` | 3 | V |
| `0x08008e48` | `DMA_ITConfig` | 3 | V |
| `0x08008e5c` | `DMA_GetCurrDataCounter` | 3 | V |
| `0x08008e7e` | `DMA_ClearITPendingBit` | 3 | V |
| `0x08008ee8` | `EXTI_Init` | 3 | V |

## 7. Open
- Meaning of the status bits, `din` pin role, `assoc_table` keys, `link_rx_record` fields (U).
- 86 functions remain `FUN_*` (mostly radio/FPGA tuning chain `0x0800e*`-`0x08010*` and libm tails).
- Passive CAN capture to confirm the inventory on a real bus (U).
