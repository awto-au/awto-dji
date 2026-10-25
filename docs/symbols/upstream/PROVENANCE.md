# Upstream symbol map (vendored for cross-reference)

`P3X_FW_V01.07.0060_m0306.map` is the IAR linker "Publics by Value" symbol map for the Phantom 3
flight controller, firmware **V01.07.0060** (one revision below the **V01.11.0020** this repo
analyses), from:

- **o-gs/dji-firmware-tools**, path `symbols/P3X_FW_V01.07.0060_m0306.map`
  <https://github.com/o-gs/dji-firmware-tools> — licence **GPL-3.0**.

This repo is GPL-3.0-only, so redistribution with attribution is licence-compatible. The file is
**upstream's work, not ours**; it is kept here only as an authoritative cross-reference for naming.

These are original DJI build symbols (e.g. `system_init`, `OS_StatTaskInit`, `hal_compass_add`,
`api_ctrl_mode_status_request_handler`, `flyc_params`). Addresses are for V01.07.0060 and differ
from our V01.11.0020 image — match by **name/structure**, not address. Our own `docs/symbols/
m0306*.tsv` are independently derived against V01.11.0020; where a name matches this map it is an
independent confirmation (our control-authority handler names do), and names here that we had not
assigned (`kctrl_init_*`, `ctrl_navi_*`, `cmd_mission_waypoint_*_rcv`) are adoption candidates once
located in our image by their string refs.

Notable toolchain/RTOS facts this map settles:
- **Compiler/linker: IAR** (`__iar_program_start`) — resolves the earlier "compiler: U".
- **RTOS: Micrium uC/OS-III** (`OS_StatTaskInit`, `OS_CPU_SysTickHandler`, ...) — matches our finding.
- `SystemInit` @ 0x08022596 / `system_init` @ 0x080203F4 (clock bring-up) in the V01.07.0060 image.

## wm220_0306_v03.02.35.05_m0306.map

Phantom 4 flight controller symbol map (MCU = Microchip ATSAME70Q21, Cortex-M7 - NOT an STM32; flash @0x00400000 2MB, SRAM @0x20400000 384KB), same source/licence (upstream file
`symbols/wm220_0306_v03.02.35.05_20170525.pro.map`). Kept for the cross-product code-sharing
comparison in `docs/prior-art.md` (P3 FC vs P4 FC share 202 identical symbol names). Upstream's
work; renamed locally for brevity.

## Cross-chip maps (for the shared-pattern comparison in prior-art.md)

Same source/licence (o-gs/dji-firmware-tools, GPL-3.0); vendored for the cross-chip pattern check:
- `C1_FW_V01.06.0000_m1400_ground-LPC.map` — ground radio, NXP LPC1765 (shows crc8_table, param_buf, uC/OS OS_CPU_*).
- `P3X_FW_V01.11.0030_m0400_gimbal.map` — gimbal STM32 (crc8/crc16_table, gimb_user_param_* with restore-defaults).
- `P3X_FW_V01.07.0060_m0900_air-radio.map` — air radio STM32F103.
The camera A9 map (`P3X_FW_V01.08.0080_m0100_part_sys`, ~22k lines, ThreadX `_tx_*`, `DjiMsg*`) is
referenced by URL rather than vendored due to size.
