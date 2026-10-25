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
