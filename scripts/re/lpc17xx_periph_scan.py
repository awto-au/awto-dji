#!/usr/bin/env python3
"""Count aligned 32-bit words in an LPC176x image that point into known peripheral blocks.

Mechanical pass (no decompilation): every 4-byte-aligned word whose value falls in a
peripheral window is a literal-pool / data reference candidate. Hits are binned per block
and listed with image offsets. Hits include data values that only fall in a window (e.g. 0x40022302),
so check each with scripts/re/mcu_trace.py (`lit VALUE` / `who ADDR`) before naming it.

Block bases: LPC176x user manual memory map, recalled from prior art, NOT yet checked
against UM10360 (tag [oss]). Image offsets are file offsets; flash = offset + LOAD (0xA000 for m1400).
Usage: python3 scripts/re/lpc17xx_periph_scan.py [--img PATH] [--load 0xA000]
Log: tmp/logs/lpc17xx_periph_scan.log
"""
import argparse
import os
import struct
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

DEFAULT_IMG = "firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m1400.bin"

# (base, size, name) — size is the block window used for binning, not the exact register span.
# Bases are [spec] from the LPC176x5x CMSIS-SVD (awto-dan/docs/embedded/reversing/lpc17xx/svd/
# LPC176x5x.svd), cross-checked 2026-10-24 against the original [oss] prior-art guesses. Two
# guesses were wrong: PWM1/I2C0 were both one slot low (0x40014000/0x40018000), and USB was a
# different region entirely (0x2008C000 is AHB SRAM, not the AHB-peripheral USB controller at
# 0x50008000) — see lpc17xx/README.md "Corrections" for detail. GPIOINT's real register base
# is +0x80 off (0x40028080); the old 0x40028000/0x4000-window scan still caught it.
BLOCKS = [
    (0x40000000, 0x4000, "WDT"),
    (0x40004000, 0x4000, "TIMER0"),
    (0x40008000, 0x4000, "TIMER1"),
    (0x4000C000, 0x4000, "UART0"),
    (0x40010000, 0x4000, "UART1"),
    (0x40018000, 0x4000, "PWM1"),
    (0x4001C000, 0x4000, "I2C0"),
    (0x40020000, 0x4000, "SPI (legacy)"),
    (0x40024000, 0x4000, "RTC"),
    (0x40028080, 0x3F80, "GPIO-INT"),
    (0x4002C000, 0x4000, "PINCONNECT"),
    (0x40030000, 0x4000, "SSP1"),
    (0x40034000, 0x4000, "ADC"),
    (0x40038000, 0x4000, "CANAFRAM"),
    (0x4003C000, 0x4000, "CANAF"),
    (0x40040000, 0x4000, "CCAN"),
    (0x40044000, 0x4000, "CAN1"),
    (0x40048000, 0x4000, "CAN2"),
    (0x4005C000, 0x4000, "I2C1"),
    (0x40088000, 0x4000, "SSP0"),
    (0x4008C000, 0x4000, "DAC"),
    (0x40090000, 0x4000, "TIMER2"),
    (0x40094000, 0x4000, "TIMER3"),
    (0x40098000, 0x4000, "UART2"),
    (0x4009C000, 0x4000, "UART3"),
    (0x400A0000, 0x4000, "I2C2"),
    (0x400A8000, 0x4000, "I2S"),
    (0x400B0000, 0x4000, "RITIMER"),
    (0x400B8000, 0x4000, "MCPWM"),
    (0x400BC000, 0x4000, "QEI"),
    (0x400FC000, 0x4000, "SYSCTL"),
    (0x50000000, 0x4000, "EMAC"),
    (0x50004000, 0x4000, "GPDMA"),
    (0x50008000, 0x4000, "USB"),
    (0x2009C000, 0x4000, "GPIO-FIO (fast)"),
    (0x1FFF0000, 0x2000, "BOOTROM"),
    (0x10000000, 0x8000, "LOCAL-SRAM"),
    # AHB SRAM banks, up to (not including) the fixed fast-GPIO window below. Exact bank
    # boundaries inside this range are not in the SVD (it only covers registers, not RAM);
    # treated as one bucket. This is where the old [oss] scan's wrong "USB@0x2008C000" literal
    # hits actually land (real USB controller is 0x50008000, see lpc17xx/README.md).
    (0x2007C000, 0x20000, "AHB-SRAM"),
]


def repo_root() -> Path:
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return Path(env)
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                      cwd=os.path.dirname(os.path.abspath(__file__)),
                                      stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return Path(top)
    except (OSError, subprocess.CalledProcessError):
        pass
    return Path(__file__).resolve().parents[2]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", default=DEFAULT_IMG)
    ap.add_argument("--load", default="0xA000")
    args = ap.parse_args()
    root = repo_root()
    img_path = Path(args.img) if Path(args.img).is_absolute() else root / args.img
    load = int(args.load, 0)
    log_path = root / "tmp" / "logs" / "lpc17xx_periph_scan.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    data = img_path.read_bytes()
    hits = defaultdict(list)  # name -> [(offset, value)]
    for off in range(0, len(data) - 3, 4):
        val = struct.unpack_from("<I", data, off)[0]
        for base, size, name in BLOCKS:
            if base <= val < base + size:
                hits[name].append((off, val))
                break

    lines = [f"image={img_path} size={len(data)} load=0x{load:X}"]
    for base, size, name in BLOCKS:
        h = hits.get(name, [])
        if not h:
            continue
        sites = ", ".join(f"0x{o:05x}" for o, _ in h[:8])
        more = f" (+{len(h) - 8})" if len(h) > 8 else ""
        lines.append(f"{name:18s} base=0x{base:08X} words={len(h):3d} word_offsets: {sites}{more}")
    text = "\n".join(lines) + "\n"
    log_path.write_text(text)
    sys.stdout.write(text)
    print(f"log: {log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
