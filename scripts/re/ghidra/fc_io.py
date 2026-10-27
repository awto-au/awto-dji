# Peripheral usage inventory: which peripherals are referenced, + key config-register immediates.
from ghidra.program.model.lang import OperandType
fm=currentProgram.getFunctionManager(); refm=currentProgram.getReferenceManager(); listing=currentProgram.getListing()
sp=currentProgram.getAddressFactory().getDefaultAddressSpace()
def A(x): return sp.getAddress(x)
PERI=[("TIM2",0x40000000),("TIM3",0x40000400),("TIM4",0x40000800),("TIM5",0x40000c00),
 ("TIM6",0x40001000),("TIM7",0x40001400),("TIM12",0x40001800),("TIM13",0x40001c00),("TIM14",0x40002000),
 ("RTC",0x40002800),("WWDG",0x40002c00),("IWDG",0x40003000),("SPI2",0x40003800),("SPI3",0x40003c00),
 ("USART2",0x40004400),("USART3",0x40004800),("UART4",0x40004c00),("UART5",0x40005000),
 ("I2C1",0x40005400),("I2C2",0x40005800),("I2C3",0x40005c00),("CAN1",0x40006400),("CAN2",0x40006800),
 ("TIM1",0x40010000),("TIM8",0x40010400),("USART1",0x40011000),("USART6",0x40011400),
 ("ADC",0x40012000),("SPI1",0x40013000),("SPI4",0x40013400),("TIM9",0x40014000),("TIM10",0x40014400),
 ("TIM11",0x40014800),("SPI5",0x40015000),("SPI6",0x40015400),("SDIO",0x40012c00),
 ("GPIOA",0x40020000),("GPIOB",0x40020400),("GPIOC",0x40020800),("GPIOD",0x40020c00),("GPIOE",0x40021000),
 ("GPIOF",0x40021400),("GPIOG",0x40021800),("GPIOH",0x40021c00),("GPIOI",0x40022000),
 ("CRC",0x40023000),("RCC",0x40023800),("FLASH",0x40023c00),("DMA1",0x40026000),("DMA2",0x40026400),
 ("USB_OTG_FS",0x50000000),("USB_OTG_HS",0x40040000)]
def refs_in(base,size=0x400):
    c=0
    for off in range(0,size,4):
        for r in refm.getReferencesTo(A(base+off)): c+=1
    return c
print("=== peripherals referenced by code ===")
used=[]
for nm,base in PERI:
    c=refs_in(base)
    if c>0: used.append((nm,base,c)); 
for nm,base,c in sorted(used,key=lambda x:-x[2]): print("  %-10s %#010x  refs=%d"%(nm,base,c))

# config-register immediates (store of a tracked immediate to a labelled reg)
def imm_writes(reg_addr):
    outs=[]
    for r in refm.getReferencesTo(A(reg_addr)):
        if not r.getReferenceType().isWrite() and not r.getReferenceType().isData(): continue
        fa=r.getFromAddress(); f=fm.getFunctionContaining(fa)
        if not f: continue
        # scan a few insns before fa in the function for mov/movw imm into the stored reg
        ins=listing.getInstructionAt(fa)
        val=None
        it=listing.getInstructions(f.getBody(),True); recent={}
        for i in it:
            if i.getAddress().getOffset()>fa.getOffset(): break
            mn=i.getMnemonicString()
            if mn in("mov","movs","movw") and i.getNumOperands()>=2 and OperandType.isScalar(i.getOperandType(1)):
                rg=i.getRegister(0); sc=i.getScalar(1)
                if rg and sc is not None: recent[rg.getName()]=sc.getUnsignedValue()
            if i.getAddress().equals(fa):
                rg=i.getRegister(0)
                if rg and rg.getName() in recent: val=recent[rg.getName()]
        outs.append((fa, val))
    return outs
print("\n=== key config registers (store immediates; None = runtime-computed) ===")
for nm,addr in [("RCC_PLLCFGR",0x40023804),("RCC_CFGR",0x40023808),
                ("USART1_BRR",0x40011008),("USART3_BRR",0x40004808),("UART4_BRR",0x40004c08),
                ("CAN1_BTR",0x4000641c),("CAN2_BTR",0x4000681c),
                ("SPI2_CR1",0x40003800),("TIM4_PSC",0x40000828),("TIM4_ARR",0x4000082c)]:
    w=imm_writes(addr)
    if w: print("  %-12s writers: %s"%(nm, [(str(a),hex(v) if v is not None else None) for a,v in w][:4]))
