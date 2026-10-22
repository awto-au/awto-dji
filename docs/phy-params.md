# PHY params — AD9363 OFDM channel configuration (status + capture method)

**Goal:** the exact DJI Phantom 3 OFDM channel parameters — centre frequency, channel
bandwidth, sample rate, and gains — recovered from the AD9363 SPI register writes the air
MCU `m0900` (STM32F103) computes at runtime. This closes the one open PHY-params item in
`HANDOVER.md`.

Honesty markers used throughout: **verified** (reproduced here), **needs-tooling** (method
ready, waiting on an input), **inferred** (reasoned, not yet observed). This file is the
result slot; the numbers land here once the capture runs.

## Status (2026-10-23)

| Piece | State |
|---|---|
| Renode 1.17.0 built from source, STM32F103 platform, SPI tap, real firmware boots | **verified** |
| Why cold boot makes 0 SPI transactions | **verified (static + emulation)** — see "Gate" |
| AD9363 bus + access protocol | **verified** — SPI2, via FPGA bridge, see "Protocol" |
| AD9363 register sequence captured (177 regs, 2464 writes) | **verified as emulated** — `renode/captures/m0900-ad9363-spi2.txt`; produced by calling firmware fns directly with forced state, not by a real DUML session |
| BBPLL word: integer 17, frac 1921843/2088960 => Fvco = Fref x 17.92 | **verified** (register values), Fref unknown |
| Sample rate, RF centre freq, BW, gains | **needs-tooling** — see "Open" |

## Gate: why cold boot never programs the AD9363 (verified)

- Cold boot ends in an IWDG-kick idle loop. Radio bring-up is DUML-driven (cmdset 0x09).
- DUML dispatch tables in flash: `0x0801a160` (set 0x09: cmd 0x06/0x07/0x12/0x13) and
  `0x0801a0f0` (ids 0x0904, 0x0911-0x0914). Full list: `docs/symbols/m0900_V01.11.0020.tsv`.
- Second gate: `get_board_version` (RAM `0x200000d8`) must be in {2,4,5,6,7}; reads 0 in emulation.
- Third gate: `tcx_config_update1` needs active flag, channel-changed, FPGA reg 0xE9 bit1.
- `radio_start_stop(1)` @ `0x08010864` programs the FPGA only, not the AD9363.
  The AD9363 is programmed by `init_fpga_config` (base profile) and `tcx_config_update1` (tune).

## Protocol: AD9363 is behind the FPGA on SPI2 (verified)

- SPI2 `0x40003800`; SPI1 sees nothing.
- `[0x0E, reg, val]` FPGA write; `[0x0F, reg, 0xFF]` FPGA read.
- AD9363 access: `[0E 01 01]` arm, then `[0x80|hi, lo, val]` write / `[hi, lo, 0xFF]` read.
- Tap frames 3-byte units, resyncs on stray bytes (`renode/peripherals/AD9363SpiTap.cs`).

## Capture method (reproduce)

- `python3 scripts/re/m0900_capture.py` -> `tmp/spi2-capture.txt` (copy kept in `renode/captures/`)
- `python3 scripts/re/decode_ad9363.py` -> effective map + derived values
- Forced state: board=2, tcx guards, status seeds (0x05E=0x80, 0x247=0x02, 0x037=0x0A, FPGA 0xE9=0x02)
- Static tools: `scripts/re/m0900_trace.py` (`dis`, `who`, `ptr`)

## Open (do not treat as results)

- RX and TX RFPLL words decode identically (int 3276) and cal polls 0x244/0x284/0x287 hit
  300-iteration timeouts: the tune phase likely ran on timed-out paths or the 0x231/0x271
  field mapping is wrong. Centre frequency NOT recovered.
- Fref (AD9363 reference clock) not in the SPI stream; needs board/schematic or firmware constant.
- Sample rate needs BBPLL dividers + FIR/decimation regs decoded vs UG-570.
- Captured by direct function calls with forced state; confirm by driving a real DUML 0x09 command.

## Why emulation (recap)

The AD9363 config is **runtime-computed** in `m0900`, not a static table
(`docs/cpu-reversing-proof.md`): a static scan found only `(start,end,index)` descriptor
arrays, not register/value pairs. So the register sequence does not exist as a decodable
blob in flash — it is produced by the driver's BBPLL/clock math as the ADI no-OS
`ad9361.c` does. Reading it means running the init and capturing the SPI traffic. A raw-CPU
emulator (Unicorn) diverged because it models no peripherals; Renode models the STM32
peripherals and runs the firmware.

## The tool (built + validated)

`renode/` holds the whole harness (see `renode/README.md`):

- **`peripherals/AD9363SpiTap.cs`** — an `ISPIPeripheral` slave that taps every AD9361/AD9363
  SPI transaction. AD9361 and AD9363 share the SPI map and framing (ADI UG-570): a 16-bit
  instruction word (`D15` R/W̄, `D14:D13` byte-count−1, `D12:D0` start address) followed by
  the data byte(s). The STM32 SPI controller drives chip-select from a GPIO and never calls
  `FinishTransmission()`, so the tap **self-frames from the header byte-count** and also keeps
  a **lossless flat MOSI byte log** as a re-framing fallback. It returns tunable readback
  values (`SetReadDefault`) so ID/PLL-lock/cal-done polls during bring-up don't stall.
- **`platforms/m0900.repl`** — extends Renode's stock `stm32f103.repl` with `spi1`
  (`0x40013000`) and `spi2` (`0x40003800`), each carrying an AD9363 tap. Both candidate buses
  are tapped, so the capture itself settles which SPI is the AD9363 control bus (compare
  `TransactionCount`).
- **`scripts/m0900_capture.resc`** — loads firmware at the app base `0x08008000`, boots from
  its vector table (SP `0x20004cb8`, reset `0x08008201`), and captures the config.
- **`scripts/m0900_selftest.resc`** — firmware-free smoke test.

### Self-test (verified, no firmware)

`renode --console -e "i @renode/scripts/m0900_selftest.resc"` drives three SPI transactions
straight at SPI1 (as the CPU would) and the tap decodes them exactly:

```
W 0x017 [0x05]  ; ENSM / state
W 0x000 [0x00]  ; SPI config / soft reset
R 0x037 [0x0A]  ; product id          <- readback returned the seeded default
```

`spi1.ad9363_spi1 TransactionCount` → 3, `spi2.ad9363_spi2 TransactionCount` → 0. This proves
the platform, the runtime-compiled peripheral, the self-framing, the read path, and the
`SaveCapture`/`SaveRaw` dump all work. The real capture reuses this exact path with firmware
loaded.

## Decode plan (against ADI UG-570)

Once `spi1-capture.txt` exists, decode the write groups against the UG-570 register map:

- **Sample rate** ← the **BBPLL** registers (reference-clock scaler + integer/fractional
  BBPLL word) give the BBPLL frequency; the clock dividers and the digital decimation chain
  (HB3/HB2/HB1 + programmable FIR taps) set the final I/Q sample rate.
- **Centre frequency** ← the **RX/TX RFPLL** synthesizer registers (integer word, fractional
  word, VCO/divider) give f_LO = f_REF · (N_int + N_frac/2^n) / divider.
- **Channel bandwidth** ← the **Rx TIA / baseband LPF** and **Tx secondary LPF** calibration
  registers, plus the FIR configuration.
- **Gains** ← the **Rx gain-table / manual-gain** registers and the **Tx attenuation**
  registers.

Record the raw sequence and the decoded values in the tables below, then flip the
PHY-params row in `HANDOVER.md` and `docs/cpu-reversing-proof.md` from "open" to the result.

## Scope

Interoperability for an owned aircraft (`CLAUDE.md`): structural RF-parameter recovery using
the public UG-570 register map. No key extraction, no geofence/flight-restriction work.
