#!/usr/bin/env python3
import struct, sys
BASE = 0x08020000
img = open(sys.argv[1], "rb").read()
BAUD = {9600:"9600",19200:"19200",38400:"38400",57600:"57600",115200:"115200",
        230400:"230400",460800:"460800",921600:"921600",1000000:"1Mbaud",
        2000000:"2Mbaud",3000000:"3Mbaud",250000:"250000",100000:"100000",
        500000:"500000",1500000:"1.5Mbaud"}
USART = {0x40011000:"USART1",0x40004400:"USART2",0x40004800:"USART3",0x40004c00:"UART4",
         0x40005000:"UART5",0x40011400:"USART6",0x40007800:"UART7",0x40007c00:"UART8"}
print("=== baud-rate constants present as 32-bit LE words ===")
hits = {}
for i in range(0, len(img)-3, 2):   # 2-byte step: literals are 4-aligned but be safe
    w = struct.unpack_from("<I", img, i)[0]
    if w in BAUD:
        hits.setdefault(BAUD[w], []).append(BASE+i)
for name in sorted(hits, key=lambda n:-len(hits[n])):
    locs = hits[name]
    print("  %-10s x%-3d  e.g. %s" % (name, len(locs), ", ".join("%#x"%a for a in locs[:6])))
print("\n=== USART base words (aligned) ===")
for i in range(0, len(img)-3, 4):
    w = struct.unpack_from("<I", img, i)[0]
    if w in USART:
        print("  %-8s @ %#x" % (USART[w], BASE+i))
