#!/usr/bin/env python3
"""Pre-Ghidra triage of the m0400 gimbal MCU image (issue #41).

Checks, in order:
  1. Cortex-M vector table: initial SP, reset vector, load base consistency.
  2. Debug remnants: embedded ELF magic, DWARF/.symtab/.debug section names,
     toolchain banner strings, map-file tokens.
  3. Library/RTOS/SDK fingerprints: ST StdPeriph/HAL/CMSIS tokens, RTOS
     tokens, assert/file-path strings, compiler runtime symbols.

Output is logged to tmp/logs/m0400_fingerprint.log (stdout is not used).
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0400.bin"
BASE = 0x08008000

# Patterns searched in printable-string runs. Each hit is logged with its offset.
DEBUG_PATTERNS = [
    rb"\.symtab", rb"\.strtab", rb"\.debug_[a-z]+", rb"\.ARM\.exidx",
    rb"GNU C", rb"GCC: \(", rb"ARM C", rb"IAR ", rb"Keil", rb"armcc",
    rb"\.map\b", rb"Memory Configuration", rb"Linker script",
]
LIB_PATTERNS = [
    rb"stm32f[0-9a-z]+", rb"STM32F[0-9A-Z]+", rb"StdPeriph", rb"stm32f10x",
    rb"stm32f4xx", rb"HAL_[A-Z]+_", rb"CMSIS", rb"core_cm[0-9]", rb"FreeRTOS",
    rb"ThreadX", rb"uC/OS", rb"RTX", rb"assert_failed", rb"assert",
    rb"__aeabi_", rb"libgcc", rb"newlib", rb"_sbrk", rb"__libc",
    rb"\.c\b", rb"\.h\b", rb"\\\\", rb"/[A-Za-z0-9_./-]+\.c",
]


def vector_table(data: bytes) -> None:
    sp, reset = struct.unpack_from("<II", data, 0)
    log(f"initial SP = 0x{sp:08x}")
    log(f"reset vector = 0x{reset:08x} (thumb={reset & 1})")
    end = BASE + len(data)
    in_img = BASE <= (reset & ~1) < end
    log(f"reset inside image [0x{BASE:08x}, 0x{end:08x}): {in_img}")
    # Walk the Cortex-M exception/IRQ vectors until the first entry that is not
    # a Thumb address inside the image (or 0), to size the table.
    n = 0
    for off in range(4, min(len(data), 0x200), 4):
        v = struct.unpack_from("<I", data, off)[0]
        if v == 0 or (v & 1 and BASE <= (v & ~1) < end):
            n += 1
        else:
            break
    log(f"vector entries after SP plausible: {n} (offsets 0x04..0x{4 + 4 * n - 4:02x})")
    for i in range(min(n + 1, 0x40)):
        v = struct.unpack_from("<I", data, 4 * i)[0] if i else sp
        log(f"  vec[{i:02d}] @0x{4 * i:03x} = 0x{v:08x}")
    # SRAM top implied by SP: STM32F103 SRAM 0x20000000..0x20005000 (20 KB),
    # STM32F4 SRAM 0x20000000..0x20020000 (128 KB) / 0x2001C000 (112 KB).
    log(f"SP in SRAM region 0x20000000..0x20020000: {0x20000000 <= sp <= 0x20020000}")


def strings_scan(data: bytes) -> None:
    runs = [(m.start(), m.group()) for m in re.finditer(rb"[\x20-\x7e]{4,}", data)]
    log(f"printable string runs (>=4): {len(runs)}")
    for name, pats in (("DEBUG", DEBUG_PATTERNS), ("LIB", LIB_PATTERNS)):
        log(f"--- {name} fingerprints ---")
        for pat in pats:
            hits = [(o, s) for o, s in runs if re.search(pat, s)]
            if not hits:
                continue
            log(f"pattern {pat!r}: {len(hits)} run(s)")
            for o, s in hits[:8]:
                log(f"    0x{BASE + o:08x}  {s.decode('ascii', 'replace')[:120]}")


# Peripheral base literals that differ between STM32F1 (RM0008) and STM32F4
# (RM0090). Presence of a family-specific value in the literal pool is the
# discriminator; shared bases (TIM2-4, SPI2, USART2/3, I2C1) are ignored.
FAMILY_BASES = {
    0x40021000: "F1 RCC", 0x40023800: "F4 RCC",
    0x40010800: "F1 GPIOA", 0x40020000: "F4 GPIOA",
    0x40013800: "F1 USART1", 0x40011000: "F4 USART1",
    0x40022000: "F1 FLASH_IF", 0x40023C00: "F4 FLASH_IF",
    0x40026000: "F4 DMA1", 0x40012400: "F1 ADC1", 0x40012000: "F4 ADC1",
    0x1FFFF7E8: "F1 UID", 0x1FFF7A10: "F4 UID", 0x1FFFF7E0: "F1 FLASH_SIZE",
    0x1FFF7A22: "F4 FLASH_SIZE",
    0xE0042000: "DBGMCU_IDCODE (same address F1/F4; DEV_ID differs)",
}


def peripheral_literals(data: bytes) -> None:
    log("--- family-discriminating literal words (all 4-byte aligned words) ---")
    counts: dict[int, list[int]] = {}
    for off in range(0, len(data) - 3, 4):
        v = struct.unpack_from("<I", data, off)[0]
        if v in FAMILY_BASES:
            counts.setdefault(v, []).append(BASE + off)
    for v, name in FAMILY_BASES.items():
        hits = counts.get(v, [])
        if hits:
            locs = " ".join(f"0x{h:08x}" for h in hits[:6])
            log(f"0x{v:08x} {name}: {len(hits)} literal(s) at {locs}")
    if not counts:
        log("no family-discriminating peripheral literals found")


def elf_and_symbol_remnants(data: bytes) -> None:
    magic = data.find(b"\x7fELF")
    log(f"ELF magic offset: {magic if magic >= 0 else 'none'}")
    log(f"SHT-like '.text' name present: {b'.text\x00' in data}")
    log(f"'.symtab' present: {b'.symtab' in data}")


def main() -> int:
    if not FW.exists():
        log(f"firmware not found at {FW}", level="ERROR")
        return 1
    data = FW.read_bytes()
    log(f"image {FW.name}: {len(data)} bytes, base 0x{BASE:08x}")
    vector_table(data)
    peripheral_literals(data)
    elf_and_symbol_remnants(data)
    strings_scan(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
