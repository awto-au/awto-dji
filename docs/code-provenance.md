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
  from the dji-firmware-tools README: FC `0x08020000`, radio MCU `0x08008000`.)
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
| `m0800` video encoder (Linux) | `GNU` / `GPL` | **GNU GCC** |
| `m0101` camera loader | `IAR` | **IAR** (with ThreadX) |
| `m0306` FC, `m0900` radio, `m0400` gimbal | stripped raw `.bin`, no compiler comment | ARM EABI (Cortex-M); not identifiable from strings |

## Chips (from Cortex-M vector tables)

- **`m0900` radio MCU** — Cortex-M3 (STM32F103): initial SP `0x20004cb8`, reset into app
  at `0x08008200` (bootloader occupies `0x08000000`–`0x08008000`).
- **`m0306` A3 flight controller** — Cortex-M4-class **STM32F4**: initial SP `0x2002ff00`
  (~192–256 KB SRAM), app at `0x08020000`.

## RTOS / library provenance — the key findings

| Module | Third-party code found | How |
|---|---|---|
| **`m0306` A3 flight controller** | **µC/OS** (Micrium RTOS) | `uC/OS` string; PendSV (`0x0802c79f`) + SysTick (`0x08029de3`) handlers populated = µC/OS preemptive scheduler |
| `m0101` camera loader | **ThreadX** (Express Logic RTOS) + IAR | strings |
| `m0100` camera | **Linux**, glibc, busybox, OpenSSL, wpa_supplicant, zlib, libjpeg, dropbear, ThreadX | strings (see license-compliance.md) |
| `m0900` radio MCU | none named — small bare-metal (likely ST StdPeriph/CMSIS + custom) | disासm + strings |
| `m0400` gimbal | none named — bare-metal | strings |

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
