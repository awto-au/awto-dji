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

## Deeper decode: what the chip is actually doing, not just port mechanics (2026-10-31)

This capture is `m0900` (air router MCU) programming the AD9363 at boot — the **air** unit, confirmed
by the capture filename/header and `m0900`'s own identity elsewhere in this repo. Decoded against the
real bit-field tables in Analog Devices' *AD9364 Register Map Reference Manual* (UG-672, register
bits) and *AD9361 Reference Manual* (UG-570, the Control Output signal table, which UG-672 doesn't
carry) -- both public ADI documents, fetched directly from analog.com. Confidence noted per finding; `[reg]` = bit meaning stated plainly by the
datasheet, `[formula]` = datasheet-stated equation with all constants known, `[partial]` = a real
register fact but missing an external (board-level) constant to turn into an absolute number.

**TX1/TX2 attenuation (0x073-0x076) — both channels equally attenuated, NOT equal-power-at-max** [reg]:
Captured `TX1_ATTEN_0/1 = 0xFF/0x00`, `TX2_ATTEN_0/1 = 0xFF/0x00`. Per UG-672 Table 31, this is a 9-bit
word (`Atten[7:0]` in the `_0` register, `Atten[8]` in `_1`'s D0), 0.25 dB/LSB, range 0-359(d) = 0-89.75
dB. Both channels decode to the SAME 9-bit value 255 → **63.75 dB of attenuation on both TX1 and TX2**
— equal between channels (consistent with the existing "air enables both TX with equal power" claim
in `docs/lightbridge-fpga.md` on the EQUAL part), but this is substantial attenuation, not a max-power
state. Caveat: `decode_ad9363.py`'s own method is last-write-wins across the whole boot capture: this
could be the firmware's genuine steady-state TX level, or a transient value captured before a later
write this trace didn't include changes it further. Not resolved either way — flagged, not guessed.

**ENSM: FDD mode, SPI-controlled state with independent RX/TX enable, both synthesizers always on**
[reg]: `0x013=0x01` (D0 FDD Mode = 1 → **FDD**, not TDD). `0x014=0x29` = `D5 Force Tx On=1` (puts ENSM
into the FDD state), `D4 ENSM Pin Control=0` (**SPI writes control state transitions**, not the
ENABLE/TXNRX pins), `D3 Level Mode=1`, `D0 To Alert=1`. `0x015=0x84` = `D7 FDD External Control
Enable=1` (independent RX/TX enable via the ENABLE/TXNRX pins — "FDD Independent Control Mode" per
UG-672), `D2 Dual Synth Mode=1` (**both RF synthesizers, RX and TX, are always on** — not switched
one-at-a-time). Coherent picture: full-duplex operation with independent, pin-level RX/TX enable
control layered on top of an otherwise SPI-configured state machine.

**AGC: Fast Attack, full gain table** [reg]: `0x0FA=0xE5` → `[D1:D0]=01` = Gain Control Setup 1 =
**Fast attack automatic gain control**, per UG-672 Table 43 (not manual, not slow-attack, not hybrid).
`0x0FB=0x08` → `D3 Use Full Gain Table=1` (full table, not split table), `D0 Manual Gain Control=0`
(confirms AGC, not manual). `0x0FC=0x03` → ADC Overrange Sample Size = 3+1 = 4 samples. The
`FAST_*` block (0x110-0x11B, fast-AGC gain-lock/threshold tuning) was NOT decoded bit-by-bit this
pass — these are internal state-machine tuning constants (gain-lock hysteresis, energy-lost
thresholds) whose individual values only matter relative to each other, not as standalone facts;
flagged as present but not characterized, rather than forced into a claim.

**RX baseband filter bandwidth: capture ends mid-calibration-sweep at the driver's minimum clamp**
[formula, with an important caveat]: `decode_ad9363.py`'s own earlier analysis (already in the dump,
not new this pass) caught that `0x1FB`/`0x1FC`/`0x1F8` OSCILLATE across the capture (0x1FB:
0x05→0x00→0x05→0x00...). The FIRST pass decodes to RX baseband bandwidth 5 MHz (RF bandwidth 10 MHz,
per `real_rx_bandwidth = rf/2`) — a clean, plausible operational value. The FINAL (last-write-wins)
state is `0x1FB=0x00, 0x1FC=0x50`: per UG-672's Equation 23 (`Rx Tune BBBW kHz[6:0] =
round((BBBW-floor(BBBW))×1000/7.8125)`), 0x50=80(d) → BBBW = 0 + 80×7.8125/1000 = **0.625 MHz = 625
kHz**. Cross-checked against ADI's own `no-OS` driver (`drivers/rf-transceiver/ad9361/ad9361.c`:
`tx_bb_bw = no_os_clamp(tx_bb_bw, 625000UL, 20000000UL)`) — **625 kHz is the AD9361/9363 driver's
documented MINIMUM bandwidth clamp**, exact match. Reading: the capture very likely shows the RX
filter TUNING/CALIBRATION algorithm sweeping its range (as `ad9361_set_rx_rf_bandwidth` does per
UG-672) and this trace's last recorded register write happens to land at the sweep's minimum-clamp
end, not necessarily the firmware's real operational RX bandwidth. The 5 MHz BBBW / 10 MHz RF
bandwidth from the first pass is the more likely actual operating value; treat the 625 kHz state as a
calibration-sweep artifact, not the real configured bandwidth, pending a cleaner capture.

**BBPLL: confirmed formula, missing the one external constant needed for an absolute frequency**
[formula, partial]: Already in the dump: `BBPLL [reg]: int=17 frac=1921843/2088960 -> x17.920000`.
Verified this IS exactly UG-672 Equation 10, `FOUT = FREF × (NINTEGER + NFRACTIONAL/2088960)` — the
×17.92 multiplier is a confirmed hard fact. `0x009=0x17`: `D4 XO Bypass=1` → **external reference
clock in use** (not the internal DCXO), `D2 Digital Power Up=1`, `D0 BBPLL Enable=1`. `0x00A=0x03`:
BBPLL Divider[2:0]=3 → ADC clock = BBPLL / 2^3 = BBPLL / 8 (UG-672 Equation 2). `0x045=0x00`: Ref
Clock Scaler=00=×1 (no scaling before the BBPLL). **Missing**: the actual external reference clock
frequency fed into AD9363 REFCLK — a board-level fact, not present in any SPI register, so `FOUT`
cannot be turned into an absolute MHz number from this capture alone. This AD9363 BBPLL is a
SEPARATE clock domain from the FPGA-internal PLL `docs/lightbridge-fpga.md` describes ("Fin lies in
54.9-83.3 MHz" — that note is about the FPGA's own PLL_2/PLL_8, fed from ball B14, not this chip);
they should not be conflated, and nothing here confirms or denies that FPGA-side number.

**Rx quadrature calibration: phase+gain correction and tracking enabled on CH1, one register
mismatches the datasheet's fixed-constant claim** [reg, with a flagged discrepancy]: `0x169=0xCF` →
`D7 Enable Phase Corr=1`, `D6 Enable Gain Corr=1`, `D3 Free Run Mode=1`, `D2 Enable Corr Word
Decimation=1`, `D0 Enable Tracking Mode CH1=1` — RX quadrature phase/gain correction and tracking
genuinely enabled. `0x16A=0x75` matches UG-672's stated "must be 0x75" exactly. **`0x16B=0x15`,
but UG-672 states this register "must be 0x95"** — a real mismatch, not explained by anything found
this pass. Possible explanations not distinguished here: a sub-revision difference between AD9361 and
AD9363's exact register behavior at this address (plausible but unconfirmed independently), a
firmware quirk, or a transcription/capture artifact. Flagged as open, not resolved.

**Control outputs: all 8 enabled, carrying calibration busy/done flags — NOT a match for the FPGA's
generic enable-pin group** [reg, cross-doc finding]: `0x036=0xFF` → all 8 `En ctrl0-7` bits set, all 8
CTRL_OUT pins active. `0x035=0x00` → Control Output Pointer row 0 (UG-570 Table 44, the only place
this mapping exists — UG-672 doesn't carry it). Row 0x00's exact 8 signals: D7 Cal Done, D6 Tx CP Cal
Done, D5 Rx CP Cal Done, D4 Rx BB Filter Tuning Done, D3 Tx BB Filter Tuning Done, D2 Gain Step Cal
Busy, D1 Rx Synth VCO Cal Busy, D0 Tx Synth VCO Cal Busy. **This is a specific, negative cross-doc
finding**: `docs/lightbridge-fpga.md`'s FPGA-side note "9 enable/direction style outputs" speculated
these might connect to the FPGA's AD9363-facing control pins in some generically meaningful way — the
actual signals are calibration status monitor flags, not control/mode/data signals, so if this 8-pin
CTRL_OUT bus does land on those FPGA pads, its content is "is calibration X done/busy," nothing more
interesting than that. Not yet cross-referenced pad-for-pad against the pluribus structural pass — the
SIGNAL MEANING is now known with datasheet confidence; the PHYSICAL PAD mapping on the FPGA side is
not.

## Open

- Which physical FPGA pads are the TX-port (P0) half vs. the CTRL_OUT bus, to confirm pad-for-pad
  against these register findings — not yet cross-referenced pin-by-pin against the pluribus
  structural pass.
- 2R2T Timing (0x010 D2) reads clear (1R1T), yet `docs/lightbridge-fpga.md` separately states "both
  RX channels on at both ends" (2R2T) from firmware. Likely not a real contradiction (2R2T Timing in
  this register controls I/O *data formatting* compatibility, not which/how-many RF channels are
  enabled — and Dual Synth Mode, confirmed set above, independently supports both channels being
  live) but not explicitly reconciled.
- 0x16B = 0x15 vs. UG-672's "must be 0x95" — unresolved discrepancy, see above.
- TX attenuation (63.75 dB) — real steady-state value or a transient from this specific capture
  window; not resolved.
- RX baseband bandwidth: the 625 kHz final-state reading is very likely a calibration-sweep artifact
  (see above), with 5 MHz/10 MHz RF as the more probable real operating value — not independently
  confirmed which one the firmware actually settles on post-boot.
- Absolute BBPLL frequency: needs the external AD9363 REFCLK value (board-level fact, not in this
  capture) to convert the confirmed ×17.92 multiplier into a real MHz number.
- The FAST_* fast-AGC tuning block (0x110-0x11B) — present, not characterized bit-by-bit.
