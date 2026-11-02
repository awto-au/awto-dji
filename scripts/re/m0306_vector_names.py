#!/usr/bin/env python3
"""Emit docs/symbols/m0306-vectors.tsv: ISR names from the m0306 vector table (STM32F427, RM0090 table 62). Issues #40, #83.

Vector word i: i<16 Cortex-M exception, else IRQ i-16. Word 0x080219a1 (shared by every unused slot) = isr_Default.
Evidence [V]: slot->IRQ number by RM0090; roles of CAN1/CAN2/SysTick/PendSV/HardFault handlers by decompile.
Stub ISRs at 0x0803a4xx load (cb, arg) from g_irq_cb_table[irq] (8 B stride) and tail-call cb(irq, arg).
Run: python3 scripts/re/m0306_vector_names.py   Log: ./tmp/logs/m0306_vector_names.log
"""
from __future__ import annotations

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0306.bin"
OUT = REPO / "docs" / "symbols" / "m0306-vectors.tsv"
DEFAULT = 0x080219A0
EXC = {2: "NMI", 3: "HardFault", 4: "MemManage", 5: "BusFault", 6: "UsageFault", 11: "SVC", 12: "DebugMon",
       14: "PendSV", 15: "SysTick"}
IRQ = ("WWDG PVD TAMP_STAMP RTC_WKUP FLASH RCC EXTI0 EXTI1 EXTI2 EXTI3 EXTI4 DMA1_S0 DMA1_S1 DMA1_S2 DMA1_S3 DMA1_S4 "
       "DMA1_S5 DMA1_S6 ADC CAN1_TX CAN1_RX0 CAN1_RX1 CAN1_SCE EXTI9_5 TIM1_BRK_TIM9 TIM1_UP_TIM10 TIM1_TRG_COM_TIM11 "
       "TIM1_CC TIM2 TIM3 TIM4 I2C1_EV I2C1_ER I2C2_EV I2C2_ER SPI1 SPI2 USART1 USART2 USART3 EXTI15_10 RTC_Alarm "
       "OTG_FS_WKUP TIM8_BRK_TIM12 TIM8_UP_TIM13 TIM8_TRG_COM_TIM14 TIM8_CC DMA1_S7 FMC SDIO TIM5 SPI3 UART4 UART5 "
       "TIM6_DAC TIM7 DMA2_S0 DMA2_S1 DMA2_S2 DMA2_S3 DMA2_S4 ETH ETH_WKUP CAN2_TX CAN2_RX0 CAN2_RX1 CAN2_SCE OTG_FS "
       "DMA2_S5 DMA2_S6 DMA2_S7 USART6 I2C3_EV I2C3_ER OTG_HS_EP1_OUT OTG_HS_EP1_IN OTG_HS_WKUP OTG_HS DCMI CRYP "
       "HASH_RNG FPU UART7 UART8 SPI4 SPI5 SPI6 SAI1 LTDC LTDC_ER DMA2D").split()
ROLE = {"CAN1_TX": "clears TSR flag, calls can1 tx pump FUN_080351d0", "CAN1_RX0": "reads RX FIFO0 mailbox (CAN1+0x1B0), queues frame",
        "CAN1_RX1": "reads RX FIFO1 mailbox, queues frame", "CAN2_TX": "clears TSR flag, calls can2 tx pump FUN_08035484",
        "CAN2_RX0": "reads CAN2 RX FIFO0, queues frame", "CAN2_RX1": "reads CAN2 RX FIFO1, queues frame",
        "SysTick": "irq-save, ++nesting counter, OSTimeTick-style calls (uC/OS-III tick)",
        "PendSV": "uC/OS-III context switch (saves r4-r11, s16-s31)", "HardFault": "selects MSP/PSP, calls fc___hard_fault",
        "OTG_FS": "USB OTG FS, calls FUN_08029f26(usb handle)", "SDIO": "thunk to FUN_0802ef32", "DMA2_S3": "thunk to FUN_0802efc8"}


def main() -> int:
    d = FW.read_bytes()
    rows = ["addr\tkind\tname\tnote\tsource"]
    rows.append(f"{DEFAULT:#010x}\tfunc\tisr_Default\t[V] target of every unused vector slot\tm0306_vector_names.py")
    for i in range(2, 16 + len(IRQ)):
        v = struct.unpack_from("<I", d, 4 * i)[0]
        if v in (0, DEFAULT | 1):
            continue
        name = EXC.get(i) if i < 16 else IRQ[i - 16]
        if name is None:
            continue
        stub = "" if name in ROLE else "; stub: tail-calls g_irq_cb_table[irq].cb(irq, arg)" if 0x0803A400 <= v < 0x0803A600 else ""
        note = f"[V] vector word {i} = {'exception' if i < 16 else f'IRQ{i - 16}'} {name}; {ROLE.get(name, '')}{stub}".replace("; ;", ";")
        rows.append(f"{v & ~1:#010x}\tfunc\tisr_{name}\t{note}\tm0306_vector_names.py")
        log(f"{i:3d} {name:18s} {v & ~1:#010x}")
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log(f"wrote {len(rows) - 1} rows -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
