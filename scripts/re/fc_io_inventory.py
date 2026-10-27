#!/usr/bin/env python3
"""I/O inventory for the m0306 flight controller (STM32F427), from the decrypted module.

No Ghidra needed: STM32 code reaches a peripheral through a base pointer held in a literal pool
(`ldr rN,[=BASE]`), so the count of literal-pool words equal to each peripheral's base address is
a good proxy for how heavily that peripheral is used. We also pull the DMA stream base words and
report any 32-bit word that matches a known AF/clock config constant is NOT attempted here (those
are runtime-computed); this script only inventories *which* peripherals the firmware drives.

Usage: python3 scripts/re/fc_io_inventory.py docs/.../m0306_decrypted.bin   (image base 0x08020000)
The decrypted module is produced by scripts/re/xv4_decrypt.py; see docs/data-manifest.md.
"""
import struct
import sys

BASE = 0x08020000

# STM32F427 peripheral base addresses (RM0090). name -> base.
PERI = {
    "TIM2": 0x40000000, "TIM3": 0x40000400, "TIM4": 0x40000800, "TIM5": 0x40000C00,
    "TIM6": 0x40001000, "TIM7": 0x40001400, "TIM12": 0x40001800, "TIM13": 0x40001C00,
    "TIM14": 0x40002000, "RTC": 0x40002800, "WWDG": 0x40002C00, "IWDG": 0x40003000,
    "SPI2/I2S2": 0x40003800, "SPI3/I2S3": 0x40003C00, "USART2": 0x40004400, "USART3": 0x40004800,
    "UART4": 0x40004C00, "UART5": 0x40005000, "I2C1": 0x40005400, "I2C2": 0x40005800,
    "I2C3": 0x40005C00, "CAN1": 0x40006400, "CAN2": 0x40006800, "PWR": 0x40007000,
    "DAC": 0x40007400, "UART7": 0x40007800, "UART8": 0x40007C00,
    "TIM1": 0x40010000, "TIM8": 0x40010400, "USART1": 0x40011000, "USART6": 0x40011400,
    "ADC1-3": 0x40012000, "SDIO": 0x40012C00, "SPI1": 0x40013000, "SPI4": 0x40013400,
    "SYSCFG": 0x40013800, "EXTI": 0x40013C00, "TIM9": 0x40014000, "TIM10": 0x40014400,
    "TIM11": 0x40014800, "SPI5": 0x40015000, "SPI6": 0x40015400,
    "GPIOA": 0x40020000, "GPIOB": 0x40020400, "GPIOC": 0x40020800, "GPIOD": 0x40020C00,
    "GPIOE": 0x40021000, "GPIOF": 0x40021400, "GPIOG": 0x40021800, "GPIOH": 0x40021C00,
    "GPIOI": 0x40022000, "CRC": 0x40023000, "RCC": 0x40023800, "FLASH_IF": 0x40023C00,
    "BKPSRAM": 0x40024000, "DMA1": 0x40026000, "DMA2": 0x40026400, "ETH": 0x40028000,
    "USB_OTG_HS": 0x40040000, "FSMC": 0xA0000000, "USB_OTG_FS": 0x50000000,
}


def main():
    path = sys.argv[1]
    img = open(path, "rb").read()
    rev = {v: k for k, v in PERI.items()}
    counts = {k: 0 for k in PERI}
    # all aligned 32-bit words
    for i in range(0, len(img) - 3, 4):
        w = struct.unpack_from("<I", img, i)[0]
        if w in rev:
            counts[rev[w]] += 1
    print("peripheral base-pointer loads (literal-pool word == base), m0306 %d B:" % len(img))
    for k, c in sorted(counts.items(), key=lambda x: -x[1]):
        if c:
            print("  %-12s %#010x  x%d" % (k, PERI[k], c))


if __name__ == "__main__":
    main()
