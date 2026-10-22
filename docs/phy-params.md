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
| Renode built from source (1.17.0, `--no-gui`, .NET 8) | **verified** — builds, runs |
| STM32F103 platform for `m0900` (`renode/platforms/m0900.repl`) | **verified** — loads; adds SPI1/SPI2 + AD9363 taps + RCC_CFGR fix (see below) |
| AD9363 SPI tap (`renode/peripherals/AD9363SpiTap.cs`) | **verified** — compiles at runtime; frames + decodes SPI; see self-test below |
| `m0900` firmware obtained + verified | **verified** — downloaded from `dl.djicdn.com` (DJI's own CDN, still live), unpacked with `dji_xv4_fwcon.py`; SHA-256 of both the container and the unpacked module match `docs/data-manifest.md` byte-for-byte |
| Real firmware boots in Renode | **verified** — `PC = 0x8008201, SP = 0x20004CB8`, exactly the documented reset vector/SP; required one fix (RCC_CFGR, below) to get past the clock-switch wait |
| **Captured AD9363 register sequence** | **needs-tooling** — firmware boots and reaches a steady idle loop (watchdog-kick only) but makes **zero** SPI1/SPI2 transactions in 15 simulated seconds. AD9363 bring-up appears gated behind an external trigger (UART/DUML command from another module, or a GPIO input) not yet supplied in the emulation. See "Boot findings" below |
| **Decoded freq / BW / sample-rate / gains** | **needs-tooling** — follows from the capture |

### Fix required: RCC_CFGR tag

The stock `stm32f103.repl` already works around the unmodeled RCC peripheral for `RCC_CR`
(`Tag <0x40021000, 0x40021003> "RCC_CR" 0x0A020083`, pre-set PLL-ready/HSE-ready bits) — but
not for `RCC_CFGR`. Without a value there, `m0900`'s clock-switch-to-PLL wait loop (polling
CFGR's SWS bits) spins forever, since nothing ever reports "switched". Added the same pattern
to `renode/platforms/m0900.repl`:

```
sysbus:
    init:
        Tag <0x40021004, 0x40021007> "RCC_CFGR" 0x00000008   // SWS = PLL selected
```

With this, the real firmware boots past clock init, AFIO/GPIO config, and what look like
CAN/I2C/USB bring-up writes (0x40006600, 0x40003000 region addresses - not yet identified
against the base repl's memory map) into a steady loop that only services the independent
watchdog (`IWDG_KR` writes of `0xAAAA`/`0xCCCC` at 0x40003000, ~500ms period).

### Boot findings (2026-10-23, real firmware, 15 simulated seconds)

- `cpu PC`/`SP` at start match the documented vector table exactly — confirms the firmware
  module, load address, and VectorTableOffset are correct.
- `spi1.ad9363_spi1 TransactionCount` and `spi2.ad9363_spi2 TransactionCount` are **both 0**
  after 15 s of simulated time (`emulation RunFor "00:00:15"`) — `m0900` never touches either
  SPI controller from cold boot alone.
- The firmware settles into a steady state (watchdog kick every ~0.5s, no change over the
  run) rather than progressing further - consistent with the air MCU waiting for a command
  (DUML over UART, or a GPIO signal from the FPGA/another module) before it brings up the
  radio, rather than configuring the AD9363 unconditionally at boot.
- **Next step (not yet done):** either (a) disassemble `m0900`'s main loop/state machine to
  find what condition gates AD9363 init (same method as the `m1400` proofs in
  `docs/cpu-reversing-proof.md`), or (b) inject a plausible stimulus (a DUML "enable
  transmission" command on a UART, or drive a candidate GPIO input) and re-run. (a) is more
  certain; (b) is faster if the trigger is guessable.

Firmware acquisition is **no longer the blocker** — the harness runs against the byte-exact,
hash-verified real `m0900.bin` (see `docs/data-manifest.md`). The open item is now purely
firmware behavioural: finding/supplying whatever `m0900` is waiting on before it talks to the
AD9363.

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
