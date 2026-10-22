# PHY params — AD9363 OFDM channel configuration (status + capture method)

**Goal:** the exact DJI Phantom 3 OFDM channel parameters — centre frequency, channel
bandwidth, sample rate, and gains — recovered from the AD9363 SPI register writes the air
MCU `m0900` (STM32F103) computes at runtime. This closes the one open PHY-params item in
`HANDOVER.md`.

Honesty markers used throughout: **verified** (reproduced here), **needs-tooling** (method
ready, waiting on an input), **inferred** (reasoned, not yet observed). This file is the
result slot; the numbers land here once the capture runs.

## Status (2026-10-23)

Tags: **verified** = read from firmware/registers or checked against no-OS source; **inferred** = reasoned; **unknown**.

| Piece | State |
|---|---|
| Renode 1.17.0, STM32F103 platform, SPI tap, real firmware boots | verified |
| AD9363 bus: SPI2 via FPGA bridge | verified |
| Base profile is a static 4-byte-record script @0x08016660, not runtime-computed | verified (`scripts/re/m0900_ad_script.py`; static decode matches the capture except 0x014, 0x073, 0x075) |
| Capture: 261 regs, all polls complete (run 2026-10-23, `renode/captures/m0900-ad9363-spi2.txt`) | verified as emulated; base script ran 3x in that run |
| Fref = 40 MHz | inferred: reg 0x03A = 0x27 (no-OS writes Fref/1 MHz - 1); BBPLL 716.8 MHz in range; RF ref x2 = 80 MHz fits channel table. No schematic |
| BBPLL: int 17 + 1921843/2088960 = x17.92 -> 716.8 MHz; ADC_CLK 89.6 MHz | verified regs (0x041 is MSB per no-OS); Fref assumed |
| Sample rate 11.2 MHz (RX and TX), decimation/interp 8 (HB1, HB2, FIR x2) | inferred (divider formulas checked against no-OS ad9361.c clock-scale code) |
| LO N = 121.1 -> 2422 MHz (VCO 9688 MHz, /4); RX = TX words | verified regs; MHz inferred from Fref |
| RX BB bandwidth 5 MHz (regs 0x1FB/0x1FC), RF 10 MHz (ADI RF = 2xBB); TX BBF divider 10 consistent with 5 MHz | regs verified; RF=2xBB per no-OS |
| Final RX BB bw register state is 0.625 MHz (script second pass, records 2581-2590) | verified regs; purpose unknown |
| Channel table @0x080190e0: 39 ch, 2404-2480 MHz, 2 MHz step; float = N x 20 exactly | table verified; float = LO MHz inferred |
| Gains: AGC code 1 (fast attack, inferred) both RX, max table idx 76, gain table 91 idx loaded | regs verified; TX attenuation not in script (unknown) |
| Real DUML session driving this | unknown (functions called directly with forced state) |

## Machine-readable exports (for FPGA RE)

- `docs/data/phy-params.json`: values with status (verified/inferred/unknown) and source
- `docs/data/ad9363-registers.tsv`: effective AD9363 register map (261 regs)
- `docs/data/channel-table.tsv`: 39-entry channel plan, tables A (boards 2/4/5) and B (6/7)
- Regenerate: `python3 scripts/re/export_phy_params.py`

## Gate: why cold boot never programs the AD9363 (verified)

- Cold boot ends in an IWDG-kick idle loop; bring-up is DUML-driven (cmdset 0x09 and 0x0904..0x0914 table).
- Dispatch tables: `0x0801a160` (set 0x09) and `0x0801a0f0`; handlers in `docs/symbols/m0900_V01.11.0020.tsv`.
- `get_board_version` (RAM `0x200000d8`) must be in {2,4,5,6,7}; 0 in emulation. Code-to-hardware mapping (P01007.06) unknown.
- `tcx_config_update1` guards: active flag, `+0x11b` != applied `[0x20000167]`, FPGA reg 0xE9 bits 0 AND 1 (`init_fpga_config` writes 0x03).
- `tcx_config_update1` is a TX attenuation update (AD9363 0x073/0x075), not a retune. RF-PLL words come only from the init script.
- `radio_start_stop` (`0x08010864`) calls fpga_cfg_load and other helpers; that it never touches the AD9363 is not proven.

## Protocol: AD9363 is behind the FPGA on SPI2 (verified)

- SPI2 `0x40003800`; CS = GPIOB ODR bit 12, active low (`0x0800b5e8` / `0x0800b5f6`).
- Byte helper `0x0800b500`: 200 polls for TXE, 200 for RXNE; returns 0 silently on expiry.
- `[0x0E, reg, val]` FPGA write; `[0x0F, reg, 0xFF]` FPGA read.
- AD9363 write: `[0E 01 01]`, CS low `[0x80|hi, lo, val]` CS high, `[0E 01 (flag?02:00)]` trailer.
- AD9363 read: `[0E 01 01]`, `[hi&0x7f, lo, 0xFF]`, trailer as above.
- Tap frames 3-byte units, resyncs on stray bytes (`renode/peripherals/AD9363SpiTap.cs`).

## Init script (verified)

- 2639 records x `[op, a, b, c]` @`0x08016660` (boards 2/4/5), executed by `0x0800d318`.
- Ops: 05 FPGA write, 06 AD write, 08 AD read, 0A poll (bit `c>>4` == `c&1`, 300 tries), 0B delay, 0C/0D markers.
- 12 polls: 0x05E b7=1 (x2), 0x244 b7=1, 0x284 b7=1, 0x247 b1=1, 0x287 b1=1, 0x016 b7/b6/b0/b1/b4/b7=0.
- Seeds in the resc satisfy all (0x016 default 0 = cal busy bits self-clear).

## Channel plan (table verified, use inferred)

- `0x080190e0`: 39 x 9 B `[int16 N, frac24, float32]`; N = 120.2 + 0.1*i; float = 2404 + 2*i; float/N = 20.0000 for all.
- LO = N x 80 MHz / 4 (Fref_rf 80 MHz = 2 x 40, VCO divider code 1).
- `radio_config_apply` (`0x0800f436`) writes the 5 PLL bytes to FPGA regs 0xBA-0xBE (boards 2/4/5): the FPGA retunes the AD9363, not the MCU over SPI.
- `radio_config_apply` sets index `S+0x84 = 3` before using it; how the index changes at run time: unknown (`0x0800e78a` looks like the hop/fixed-channel index calc).
- Table B `0x0801923f` (boards 6/7): same 2404-2480 list, different ref (MHz/N 19.35-19.5).

## Capture method (reproduce)

- `python3 scripts/re/m0900_capture.py` -> `tmp/spi2-capture.txt` (copy kept in `renode/captures/`)
- `python3 scripts/re/decode_ad9363.py` -> effective map, derived values, channel tables
- `python3 scripts/re/m0900_ad_script.py [capture]` -> static script decode, polls, script-vs-capture diff
- Forced state: board=2, tcx guards, status seeds (see resc)
- Names: `scripts/re/ad9361_regs.tsv` (no-OS register header)
- Static tools: `scripts/re/m0900_trace.py` (`dis`, `who`, `ptr`; `who` uses a nearest-push heuristic, verify with `dis`)

## Open (do not treat as results)

- Fref: 40 MHz inferred, not confirmed by schematic/measurement.
- Why the script ends with RX BB bw 0.625 MHz; whether runtime restores 5 MHz.
- TX attenuation / gain values at run time (`S+0x11b`, `[0x20000167]`).
- Run-time channel index source (`S+0x84`) and meaning of cfg-word fields (bits 7-11, 18-20, 27-29).
- Confirm with a real DUML 0x09 session.
- AD9363 reference/gain-table contents (91 entries) not decoded to dB.

## Why emulation (recap)

The AD9363 base profile is a record script in flash (see "Init script"); the earlier static
scan missed it because records are 4-byte `[op,a,b,c]`, not register/value pairs. Emulation
remains the cross-check (script vs capture differ only in 0x014/0x073/0x075). A raw-CPU
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
