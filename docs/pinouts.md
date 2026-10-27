# Pinouts and connectors: index

Where every pin, pad and connector fact lives. This page links; the source docs hold the data.
Tags: **V** read from firmware/hardware, **W** wiki (not independently checked), **I** inferred, **U** unknown.

## Chip pin maps (from firmware)
| Device | Covers | Tag | Source |
|---|---|---|---|
| Aircraft radio MCU `m0900` (STM32F103) | UART/SPI/CAN pins (USART1 PA9/PA10, USART2 PA2/PA3 board 7 only, USART3 PB10/PB11, SPI2 CS PB12), board-code straps PA0/PC15/PC14, PB3 FPGA reset, PA1 strobe, PA4, PB4 | V pins; some roles U | `data/m0900-buses.tsv`, `air-router-io-and-naming.md` section 4.2, `fpga-bringup.md` |
| Aircraft flight controller `m0306` (STM32F427) | CAN1 PD0/PD1, CAN2 PB12/PB13, SDIO, USB OTG_FS PA11/PA12 AF10 | V (SPL callers) | `fc-io-inventory.md` |
| Gimbal MCU `m0400` (STM32F4) | GPIOA/B/C traced to peripherals; SPI1 IMU, 3 UARTs, CAN1, ADC1 | V | `air-id-and-stream-survey.md` ("GPIOA/B/C: every pin traced") |
| RC MCU `m1400` (LPC1765) | board-strap mechanism, full GPIO/bus survey | V | `control-plane-re.md` (strap section, "Full GPIO/bus survey") |
| Aircraft front micro-USB, RC micro-USB | which chip owns each port | U (aircraft, #21); RC V | `fc-usb-port.md`, `ground-upgrade-path.md` (Q5) |
| USB mode-switch GPIOs (FX3 / camera) | GPIO 41/42 reads, mux topology | V partly | `fx3-usb-modes.md`, `ground-fx3-m1601.md` section 7 |

## Board connectors and pads
| Item | Covers | Tag | Source |
|---|---|---|---|
| Lightbridge air board `CENTER` (6-pin, 1.25 mm ribbon, to ESC center board) | signals GND, 5V/6V, TX, RX | W; **pin 1-6 order unknown** | `board-connections.md`, `rf-sdr-and-repair.md` |
| `CAMERA` (6-pin, 1.25 mm ribbon, to gimbal/camera board) | USB DP/DM, others | W; **pin order unknown** | same |
| ESC center board connector | JST GH `MB10B-GHS-TBT`, 10-pin table (the only pin map we have for this link) | W/I | `rf-sdr-and-repair.md` |
| Service pads (SWD/JTAG, UART 256000 8N1, SPI, CAN, USB) | named test pads by board revision | W | `rf-sdr-and-repair.md` |
| Camera Linux console pads | which pads, network path | U (#20) | `camera-linux-console-access.md` |
| FPGA external interfaces | derived from the MCU/FX2/DaVinci side; no package pins (bitstreams not decoded) | I | `fpga-pinout-model.md`, `fpga-interfaces.md` |

## Known gaps
- No schematic exists for any board; every pin fact above is firmware-derived or from the o-gs wiki.
- `CENTER` / `CAMERA` pin order and the air-vs-RC board role: #13 (continuity probe on a real board) and #9.
- Which MCU answers on the aircraft front USB port: #21, #82.
- Camera console pads: #20.
- FPGA package pin assignments: unknowable until a bitstream decodes (`fpga-images.md`).
