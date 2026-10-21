# Phantom 3 firmware — how it's structured

This is the aircraft/RC software, a separate world from the phone app. Described from
the P3-focused open-source tooling (`o-gs/dji-firmware-tools`) and its P3X firmware
symbols — i.e. how the firmware is *organised and works*, not how to modify it.
Modifying firmware is signed/encrypted, out of scope, and not needed for the app.

## One package, many modules

A P3 firmware `.bin` is a container holding a separate firmware image for each
processor on the aircraft and the remote. They all talk to each other over the
internal **DUML bus** — the same protocol the phone speaks to the aircraft. Module map
for the Phantom 3 (from `dji_xv4_fwcon.py`):

| Module | Chip / role |
|---|---|
| `m0100` (FC300X / CAMLDR) | Camera SoC — **Ambarella A9SE**, runs Linux (ROMFS + UBIFS). Main camera/imaging processor. |
| `m0306` | **Flight Controller** — the flight MCU. Receives and executes flight commands, holds flight parameters and flight state. The one that matters for control. |
| `m0400` (GIMBAL0) | Gimbal controller. |
| `m0800` (DM368) | Video **encoder** on the aircraft — DaVinci DM368 Linux. |
| `m0900` (MCA1765) | **Lightbridge** MCU in the air — STM32F103. |
| `m1300` (DM365) | Video **decoder** on the ground (in the RC). |
| `m1400` (MCG1765A) | Lightbridge MCU on the ground (RC) — LPC1765. |
| `m1900` / `m2000` (FPGAA / FPGAG) | Lightbridge FPGAs, air and ground. |

So "updating the drone" actually flashes ~8 different processors, each over DUML.

## Package format and signing

- **Phantom 3 uses the `xV4` container** (`dji_xv4_fwcon.py -x` extracts the modules).
  Example from the reference: `./dji_xv4_fwcon.py -x -p P3X_FW_V01.08.0080.bin`.
- **Newer DJI products use the `IMaH` signed/encrypted format** (`dji_imah_fwsig.py`).
  Images are signed with `PRAK` keys and encrypted with `PUEK` keys; the private parts
  are rarely available, so modules generally cannot be re-signed. (P3 predates the
  strictest of this.)
- The camera module (`m0100`) is a full Linux system (kernel + device tree + UBIFS
  rootfs). The flight controller (`m0306`) is bare-metal ARM loaded at `0x8020000`;
  the tooling turns it into an ELF for analysis (`arm_bin2elf.py`).

## How the flight controller works (m0306)

The FC is the DUML endpoint that executes the flight-controller command set
(`cmd_set = 0x03`). Its firmware symbols show the state machine and command handlers,
e.g. `kctrl_init_auto_landing` / `act_ctrl_auto_landing`, matching the flight states in
the protocol dissector (`Manual`, `GPS_Atti`, `AutoTakeoff`, `AutoLanding`, `GoHome`,
`Joystick`, …). It also exposes **hundreds of parameters** over DUML, which the service
tools get/set (`comm_og_service_tool.py`, `dji_flyc_param_ed.py`) — this is how tuning
and configuration work.

The implication for the app: the "flight control over DUML" we flagged as *unproven*
is ultimately received and acted on by `m0306`. Confirming the exact command payloads
is best done by **capturing live DUML** between a working RC/app and the aircraft, not
by modifying firmware.

## Boundaries

The reference also ships tools to edit firmware (including a no-fly-zone editor and
FC "hardcoder" patchers) and historically a firmware *downgrade* enabled root access.
Those modify the aircraft's behaviour and its safety limits — out of scope here, and
unnecessary: the app project only needs to *speak* DUML to a stock aircraft and enforce
airspace limits itself (the `geofence` gate), not to alter firmware.
