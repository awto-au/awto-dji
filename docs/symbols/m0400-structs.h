/* m0400 gimbal MCU (STM32F4, image P3X_FW_V01.11.0020_m0400) struct types, issue #41.
   Applied by scripts/re/ghidra/M0400Dump.java to `ram`/`table` rows of m0400.tsv carrying type=<name>.
   Tags: V verified in decompile/disassembly, I inferred. Companion: docs/m0400-naming-pass.md */
/* @ghidra-begin */
#pragma pack(push, 1)
typedef struct ringbuf_s { unsigned int head; unsigned int tail; unsigned int mask; unsigned int can_id; unsigned char *buf; unsigned char flag; unsigned char pad[3]; } ringbuf_s;
typedef struct uart_idx_s { unsigned short tx_head; unsigned short tx_tail; unsigned short rx_head; unsigned short rx_tail; } uart_idx_s;
typedef struct can_tx_msg_s { unsigned int std_id; unsigned int ext_id; unsigned char ide; unsigned char rtr; unsigned char dlc; unsigned char data[8]; unsigned char pad; } can_tx_msg_s;
typedef struct duml_h_entry_s { void *handler; unsigned char id; unsigned char set; unsigned char pad[2]; } duml_h_entry_s;
typedef struct imu_burst_s { unsigned char status; unsigned char accel[6]; unsigned char temp[2]; unsigned char gyro[6]; } imu_burst_s;
typedef struct led_ch_s { unsigned int pattern; unsigned char period; unsigned char repeat; unsigned char phase; unsigned char out; } led_ch_s;
typedef struct led_state_s { unsigned char pad0; unsigned char enable_mask; unsigned char pad2[2]; led_ch_s ch[3]; unsigned int tick; } led_state_s;
typedef struct gpio_pin_ent_s { unsigned int port; unsigned int pin; unsigned int rcc_ahb1; } gpio_pin_ent_s;
#pragma pack(pop)
/* @ghidra-end */
