import sys, struct
from unicorn import *
from unicorn.arm_const import *

img = open(sys.argv[1], "rb").read()
FLASH = 0x08000000
SRAM = 0x20000000
MMIO = 0x40000000
PPB = 0xE0000000

uc = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
uc.mem_map(FLASH, 0x100000)                 # flash
uc.mem_write(FLASH, img)
uc.mem_map(SRAM, 0x20000)                   # 128K SRAM
uc.mem_map(MMIO, 0x10000000)                # peripherals
uc.mem_map(PPB, 0x100000)                   # system control (SysTick/NVIC/SCB)

# Pre-set "ready" status so polling loops pass:
def w32(a, v): uc.mem_write(a, struct.pack("<I", v))
w32(0x40021000, 0xFFFFFFFF)   # RCC CR  (HS/PLL ready bits)
w32(0x40021004, 0xFFFFFFFF)   # RCC CFGR (SWS = PLL used)
w32(0x40021018, 0xFFFFFFFF)   # RCC APB2ENR
for base in (0x40013000, 0x40003800):       # SPI1, SPI2
    w32(base + 0x08, 0x00000002)             # SR: TXE=1, BSY=0

spi_writes = []
gpio_writes = []

def hook_write(uc, access, address, size, value, user):
    if address in (0x4001300C, 0x4000380C):           # SPI_DR
        spi_writes.append((address, value & 0xFFFF))
    elif 0x40010800 <= address < 0x40012000 and (address & 0xFF) in (0x10, 0x14):  # GPIO BSRR/BRR
        gpio_writes.append((address, value))

def hook_read(uc, access, address, size, value, user):
    # keep SPI status "ready" after any clear
    if address in (0x40013008, 0x40003808):
        w32(address, 0x00000002)

uc.hook_add(UC_HOOK_MEM_WRITE, hook_write, begin=MMIO, end=MMIO + 0x10000000)
uc.hook_add(UC_HOOK_MEM_READ, hook_read, begin=MMIO, end=MMIO + 0x10000000)

# watchdog: detect tight infinite loops
seen = {}
stop = [False]
def hook_code(uc, address, size, user):
    seen[address] = seen.get(address, 0) + 1
    if seen[address] > 200000:
        stop[0] = True
        uc.emu_stop()
uc.hook_add(UC_HOOK_CODE, hook_code)

sp = struct.unpack_from("<I", img, 0)[0]
reset = struct.unpack_from("<I", img, 4)[0]
uc.reg_write(UC_ARM_REG_SP, sp)
_c=uc.reg_read(UC_ARM_REG_CPSR); uc.reg_write(UC_ARM_REG_CPSR, _c | 0x20)
print(f"SP={sp:#010x} reset={reset:#010x} ; booting m0900 ...")
try:
    uc.emu_start(reset | 1, FLASH + len(img), count=20_000_000)
except UcError as e:
    pc = uc.reg_read(UC_ARM_REG_PC)
    print(f"stopped: {e} at PC={pc:#010x}")

print(f"instructions at distinct PCs: {len(seen)}  loop-stopped={stop[0]}")
print(f"SPI writes captured: {len(spi_writes)}")
for a, v in spi_writes[:40]:
    print(f"  SPI {a:#010x} <- {v:#06x}")
print(f"GPIO BSRR/BRR writes: {len(gpio_writes)} (chip-selects / FPGA config lines)")
