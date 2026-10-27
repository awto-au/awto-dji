#!/usr/bin/env python3
import struct, sys
BASE = 0x08020000
img = open(sys.argv[1], "rb").read()
def rd(addr):
    off = addr - BASE
    return struct.unpack_from("<I", img, off)[0]
GPIO = {0x40020000:"GPIOA",0x40020400:"GPIOB",0x40020800:"GPIOC",0x40020c00:"GPIOD",
        0x40021000:"GPIOE",0x40021400:"GPIOF",0x40021800:"GPIOG",0x40021c00:"GPIOH",0x40022000:"GPIOI"}
USART = {0x40011000:"USART1",0x40004400:"USART2",0x40004800:"USART3",0x40004c00:"UART4",
         0x40005000:"UART5",0x40011400:"USART6",0x40007800:"UART7",0x40007c00:"UART8"}
CAN = {0x40006400:"CAN1",0x40006800:"CAN2"}
def who(v):
    return GPIO.get(v) or USART.get(v) or CAN.get(v) or ("%#x"%v)
for name in sys.argv[2:]:
    a = int(name, 16)
    v = rd(a)
    print("  DAT_%08x -> %#010x  %s" % (a, v, who(v)))
