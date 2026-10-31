# AD9363 radio configuration: what the air MCU actually programs at boot

Where the dump lives, how it was produced, and one concrete finding (the CMOS parallel-port mode)
that resolves a cross-repo question about the FPGA's apparent RX data-pin count.

## What exists

- `renode/captures/m0900-ad9363-spi2.txt` — raw SPI write/read capture of the air MCU (`m0900`)
  programming the AD9363 at boot, taken via `renode/peripherals/AD9363SpiTap.cs`.
- `scripts/re/ad9361_regs.tsv` — the real ADI AD9361/AD9363 register map (address, name,
  description), sourced from ADI's UG-570/UG-671/UG-672 documentation (AD9361 and AD9364/AD9363
  share one register map per ADI's own doc).
- `scripts/re/decode_ad9363.py` — reduces the raw capture to the effective register map (last
  write wins per address) with readable names, plus derived RF parameters (channel table, PLL N
  values). Tags: `[reg]` read straight from registers, `[asm]` stated firmware assumption, `[inf]`
  inferred from ADI driver semantics, not bench-verified.
- Output: **261 registers written, 13 polled/read**, every one resolved to its real ADI register
  name. Previously only in `tmp/logs/ad9363_decode.txt` (regenerable scratch); the full dump is
  reproducible any time via `python3 scripts/re/decode_ad9363.py renode/captures/m0900-ad9363-spi2.txt`.

## Finding: CMOS parallel port runs in Full-Port mode, both data ports enabled

`docs/lightbridge-fpga.md`'s (in `awtoau/pluribus`) existing note that the FPGA's AD9363-facing pads
look like a "12 RX_D + RX_FRAME + 8 CTRL_OUT = 21" group, and a separate structural re-check there
splitting that into 13 genuinely-uniform pads + 8 pads with zero consumers in the lift, is settled by
the actual register programming:

| reg | value | relevant bits (UG-672, Table 11 / "SPI Register 0x010/0x012") |
|---|---|---|
| 0x010 PARALLEL_PORT_CONF_1 | `0x08` | D3 Rx Frame Pulse Mode = 1 (toggling 50% duty cycle, not "high while RX enabled"); D2 2R2T Timing = 0 (1R1T timing); all other bits 0 |
| 0x012 PARALLEL_PORT_CONF_3 | `0x02` | D4 LVDS Mode = **0** (single-ended CMOS, matches the existing doc note); D2 Single Port Mode = **0** (both P0 and P1 data ports ARE used); D1 Full Port = **1** (RX forced onto one data port, TX forced onto the other) |

Cross-checked against ADI's own reference driver (`analogdevicesinc/no-OS`,
`drivers/rf-transceiver/ad9361/ad9361.h`: `#define FULL_PORT (1 << 1)`, matching bit D1 of 0x012
exactly) — and `projects/ad9361/src/main.c`'s `default_init_param.full_port_enable = 1` shows this is
ADI's own **recommended default**, not an unusual choice by this firmware.

**So the FPGA-side 21-pad grouping was conflating two different things that happen to share one
physical FPGA pin bank**: the real RX data port (P1: the 13 structurally-uniform pads — ~12 data
bits + 1 frame pin, matching the AD9361/9364 datasheet's documented port width) and TX-port pins
that physically interleave with it pin-by-pin in the same bank (Full Port mode dedicates P0 to TX
and P1 to RX, so the TX-direction pins correctly show zero RX-path consumers in a lift that only
traced the RX side). This explains the "8 pads with no consumer at all" finding without needing a
disabled/unused second port, or a non-standard bus width — it is the TX half of a standard Full-Port
CMOS configuration.

Note on the pad naming: these are `DIFFIO_*` pads in the Cyclone IV sense (the pin TYPE supports a
differential input buffer), which is a fact about the FPGA's own pin architecture, not a claim about
how the board wires them. The confirmed register setting is `LVDS Mode = 0` -- single-ended CMOS --
so each `DIFFIO_*` pin here carries one single-ended signal, not a true LVDS pair across two pins.
Consistent with Dan's observation that the FPGA and the AD9363 sit millimetres apart on the board:
short single-ended traces are the expected, simpler choice at that distance, and differential
signalling (LVDS) exists specifically to survive longer runs / lower noise margins -- there would be
little reason to pay for differential buffering between two ICs this close together.

## Open

- Which physical pads are the TX-port (P0) half, to confirm pad-for-pad against this register
  finding — not yet cross-referenced pin-by-pin against the pluribus structural pass.
- 2R2T Timing (0x010 D2) reads clear (1R1T), yet `docs/lightbridge-fpga.md` separately states "both
  RX channels on at both ends" (2R2T) from firmware. Worth reconciling: 2R2T Timing in this register
  controls I/O *data formatting* compatibility, not which/how-many RF channels are enabled — these
  may not be the contradiction they look like at first read, but it hasn't been checked.
- Full decoded dump (261 registers) still needs a pass to flag which settings are genuinely
  interesting (RF channel enables, gain tables, calibration) vs. boilerplate defaults, before it's
  useful as more than a reference table.
