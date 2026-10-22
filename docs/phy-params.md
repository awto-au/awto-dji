# PHY params — AD9363 OFDM channel configuration (status + capture method)

**Goal:** the exact DJI Phantom 3 OFDM channel parameters — centre frequency, channel
bandwidth, sample rate, and gains — recovered from the AD9363 SPI register writes the air
MCU `m0900` (STM32F103) computes at runtime. This closes the one open PHY-params item in
`HANDOVER.md`.

Honesty markers used throughout: **verified** (reproduced here), **needs-tooling** (method
ready, waiting on an input), **inferred** (reasoned, not yet observed). This file is the
result slot; the numbers land here once the capture runs.

## Status (2026-10-22)

| Piece | State |
|---|---|
| Renode built from source (1.17.0, `--no-gui`, .NET 8) | **verified** — builds, runs |
| STM32F103 platform for `m0900` (`renode/platforms/m0900.repl`) | **verified** — loads; adds SPI1/SPI2 + AD9363 taps to the stock F103 |
| AD9363 SPI tap (`renode/peripherals/AD9363SpiTap.cs`) | **verified** — compiles at runtime; frames + decodes SPI; see self-test below |
| End-to-end capture harness (`renode/scripts/m0900_capture.resc`) | **verified** to load; **needs-tooling** to run (firmware) |
| **Captured AD9363 register sequence** | **needs-tooling** — blocked on the `m0900` firmware binary (not in repo) |
| **Decoded freq / BW / sample-rate / gains** | **needs-tooling** — follows from the capture |

The capture is **blocked only on obtaining the `m0900` firmware image**
(`P3X_FW_V01.11.0020_m0900.bin`), which is not committed to this repo. See `HANDOVER.md` →
"DATA NOT IN THE REPO" and `docs/code-provenance.md` (DJI xV4 container, unpacked with
dji-firmware-tools `dji_xv4_fwcon.py`). Everything else is built and validated.

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

### Captured sequence (pending)

```
(paste spi1-capture.txt here after the run)
```

### Decoded parameters (pending)

| Parameter | Value | Source register(s) |
|---|---|---|
| AD9363 control bus | SPI? (TransactionCount winner) | — |
| Reference clock | — | — |
| BBPLL frequency | — | BBPLL int/frac + ref scaler |
| I/Q sample rate | — | BBPLL ÷ dividers ÷ decimation |
| RX centre frequency | — | RX RFPLL |
| TX centre frequency | — | TX RFPLL |
| RX channel bandwidth | — | Rx TIA / BB LPF + FIR |
| TX channel bandwidth | — | Tx LPF + FIR |
| RX gain | — | Rx gain table / manual gain |
| TX attenuation | — | Tx atten registers |

## Scope

Interoperability for an owned aircraft (`CLAUDE.md`): structural RF-parameter recovery using
the public UG-570 register map. No key extraction, no geofence/flight-restriction work.
