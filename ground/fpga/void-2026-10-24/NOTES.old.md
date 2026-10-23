# dji-p3-ground — notes (PRIVATE, untracked; excluded via .git/info/exclude)

Run: `PLURIBUS_SQLITE_PATH=tmp/dji/pipeline.db python3.15t scripts/run_pipeline.py --board boards/dji-p3-ground --label G --workers 8`
Logs: `tmp/pipeline_G_<stage>.log`, `tmp/logs/dji_*.log`. Outputs: `out/G.v`, `out/G-report.txt`, `out/G-chains.txt`.

## 1. Bitstream
- Used: `awto-dji/firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m2001.bin` (8 MiB, SHA-256 `b6cc5e96f12446b1...`).
- Byte-identical `m2001` also in the P3X `V01.01.0006` firmware (`awto-dji/tmp/air/P3X0006/`) -> same image ships in both; m2000/m2002 differ (entropy ~7.99, not decodable by Mistral).
- Storage: 0xFF-padded flash slot; payload starts at 0x20 (`6a f7 f7 f7...`), runs to ~2.12 MB, trailing 0xFF. NOT compressed beyond Altera's own on-chip RLE; no encryption.
- Convert: strip leading/trailing 0xFF -> `.rbf` (sha256 `7dbf960a...`, identical to awto-dji's `m2001.depack.bin`) -> `mistral-cv decomp 5CEBA4U19C8` -> `.bt` text (11.6 MB; byte-identical to awto-dji's `m2001.bt`).
- The Cyclone V lifter reads the `.bt`, not the `.rbf`. Script: `scripts/cyclonev_unpack.py` (2.7 s). Pipeline `[unpack]` now calls it.
- Part: decodes cleanly against 5CEBA4U19C8 (e50f die). U19 package table: 245 GPIO balls, 224 appear in the bitstream.
- Caveat: m2001 is labelled "ground rev 01" in the Lightbridge-2 (C1) firmware; whether the P3 RC carries rev 01 vs 00/02 is not established here (m2000/m2002 undecoded).

## 2. Pipeline status (stage, result)
| stage | status | notes |
|---|---|---|
| unpack | RUN | new `cyclonev_unpack.py`; 2.7 s |
| iomap | N/A | Trellis-only; Cyclone V pins come from the `.bt` comments |
| load | RUN | 33,336 LUT5, 11,502 FFs, 144,296 nets, 70,007 arcs, 224 pads; `pins.tsv` applied to pad_map (245 rows, 224 matched) |
| annotate | N/A | board ships no spi_registers / cell_names |
| reach | RUN | 2.3 s, 167,527 pairs; `pad_ff_influence` = 0 rows |
| reach2 | RUN | 36 s; 0 FF->FF pairs, 0 dominators |
| reach3 | RUN | FF D-functions are empty (D is None for every FF) |
| reach4 | RUN | names nothing (0 clocks, 0 groups) |
| auto_name | RUN | 0 names |
| patterns | RUN | 5 `pclk_lane` hits = MachXO2 heuristic, spurious here |
| report | RUN | "11502 stuck-at-reset, 0 active", 0 clock domains: artefact of unresolved FF D/CLK |
| chains | RUN | every pad "no fanout in netlist" |
| verilog | RUN | `out/G.v`, 244k lines, 18 MB |
| verify | RUN, GATE FAILS | 8 combinational loops, each a LUT whose output feeds its own input pin (yosys `$shiftx` B->Y) |
Exit code of run_pipeline: 1 (verify is the last stage).

## 3. What the Cyclone V lifter faults mean for this output (not fixed here; issue #106 agent)
- FF D/CLK/CE/LSR unresolved -> every FF "stuck-at-reset"; reach3/reach4/auto_name/patterns have nothing to chew on.
- LUT pin mapping wrong in every mode (#106) -> the 8 comb loops are most likely mis-assigned pins, not real latches.
- Interconnect: Mistral resolves ~70k arcs; 53,889 active routes unresolved (docs/cyclonev-interconnect-gap.md). Measured here on the arc graph:
  - 14,605 nets have a block-port source, 9,648 have a sink, only 2,267 have both (LAB/MLAB dominated).
  - 480 nets sourced by a GPIO, 0 reach any LAB/MLAB/DSP/M10K input. 0 pad nets feed any LUT input (real or vacuous).
  -> no pad has a measurable fan-out cone. "Rank by how much logic hangs off it" is not computable today.
- Pad arcs are not evidence of use: the 48 pad positions that exist in NO package table (x=0,54 at y=14-17,29-33) carry DATAIN/DATAOUT arcs and IO settings at the same rate as bonded pads (DATAIN 65/48 pads vs 438/224; PLL_SELECT, LVDS_BUFFER_USED also on unbonded tile 0,17). Treat arc presence and the GPIO tile settings as likely default-state decode, unless corroborated.
- Evidence that IS structural: HMC (hard memory controller) <-> pad links exist only on bonded top-edge tiles (y=45), 45 pads. HMC has non-default INST_ROM_DATA / AC_ROM_DATA / DDIO_*_EN settings.
- Package label in `bitstreams.package` and report header now carry U19 (was "UNKNOWN").

## 4. Pin hypotheses (pins.tsv; io_table.tsv = raw per-pad features; hypotheses.tsv = class + evidence)
Confidence scale: 1 none, 3 guess, 5 estimate, 8 inferred, 10 fact.
| class | pads | conf | evidence |
|---|---|---|---|
| CFG | 15 | 10 (class) | Mistral package table `dedicated_programming_pad`; function per index needs the Intel U484 pin-out |
| DDR3 (HMC-named) | 46 | 5 | `.bt` lines name `IOINT<sig>` / `PHYDDIO<sig>` HMC nodes on the ball: CK J9, CK# J8, CS# H8/G7, CAS# A10, RESET# B22, BA C6/C10/C9, DM A15, ADDR (A7 A8 B8 C8 D9 E7 F8), DQS G12/G15, DQS# G8/H12/G14, DQ0..DQ25 on 25 balls. Bit index = n//4 (DIN/DOUT), n//2 (OE); DQ indices agree across kinds; ADDR/DQS/CS index scaling unverified |
| DDR3? (bank only) | 34 | 3 | rest of banks 7A/8A (80 balls); a x32 DDR3 needs ~72 |
| PLLOUT? | 5 | 3 | PLL_SELECT=PLL on C2 W14 Y15 Y19 AA15 (setting may be noise) |
| UNUSED | 4 | 3 | P5 R4 V3 V5: GPIO balls with no tile data |
| no evidence | 139 | 1 | banks 4A 44, 3B 32, 5A/5B/3A 16 each, 2A 15 |
- DQ max index 25 and 3 DQS pairs seen -> x32 bus (4 lanes) likely; only 26 of 32 DQ visible.
- AD9363 data port: LVDS looks unlikely: LVDS_BUFFER_USED on only 2 bonded tiles (36,45 and 40,0) vs 7+ needed for 14 pairs; AD9363 init script never writes LVDS_BIAS/INVERT (0x03C-0x03E); parallel-port regs 0x010=0x08, 0x012=0x02 (bit meanings not verified against UG-570). CMOS likely, conf 4.

## 5. Top pin guesses
1. J9 / J8 = DDR3 CK / CK#, conf 6 (HMC IOINTCKDOUT/CKNDOUT on adjacent balls). Check: DDR3 chip ball J7/K7 continuity or probe 400-ish MHz clock.
2. B22 = DDR3 RESET#, conf 6. Check: low->high at power-up, 1.5 V swing.
3. H8 / G7 = DDR3 CS#0 / CS#1, conf 5. Check: only CS#0 routed on the DRAM.
4. G12 G15 = DQS(1,2), G8 H12 G14 = DQS#, conf 4 (scaling unverified, pairing plausible). Check: trace to DRAM DQS/DQS# pairs.
5. F12 = DQ0, E12 = DQ1, B12 = DQ2, B13 = DQ3 (conf 4). Check: trace to DRAM DQL0-3; lane permutation is common on PCBs, so these may differ.
6. Banks 7A+8A (80 balls) = DDR3 x32 data/CA, conf 4. Check: identify the DRAM part number next to the FPGA (one look validates ~80 balls).
7. Y15 / AA15 / W14 / Y19 = PLL-driven clock outputs, conf 3 (FB_CLK/ref clock to AD9363, IFCLK to FX2LP, or ADC clock). Check: scope the pads with the board running.
8. AD9363 interface is CMOS (not LVDS), conf 4. Check: probe AD9363 DATA_CLK for single-ended swing; or read reg 0x012 bits from the datasheet against 0x02.
9. 15 CFG balls = dedicated programming pads (nCONFIG, nSTATUS, CONF_DONE, DCLK, nCE, AS_DATA, JTAG...), conf 10 for class. Check: Intel Cyclone V U484 pin list by index.
10. Bank 3A/3B/4A (bottom) carries the radio/MCU/USB side, conf 2. Check: board layout (where AD9363, FX2LP, STM32 sit relative to the FPGA).

## 6. Ranked "needs board trace" list
Order = information per probe (balls resolved) x cheapness.
1. DRAM chip: part number + which FPGA balls go to it (validates HMC/DDR3 hypothesis, ~46 named + ~34 bank-level balls). One visual check first.
2. AD9363 data port: DATA_CLK, FB_CLK, RX_FRAME, TX_FRAME, P0_D[11:0], P1_D[11:0], ENABLE, TXNRX, CTRL_IN -> ~30 balls. Gives LVDS-vs-CMOS and the clock architecture (which pad is the sample clock into the PLL).
3. FX2LP (CY7C68013A): FD[15:0], IFCLK, SLRD#, SLWR#, SLOE#, PKTEND, FLAGA-C, FIFOADR[1:0] -> ~28 balls; width 8 vs 16 settled by FD7-FD15 existence.
4. STM32 SPI2 (PB12 CS, PB13 SCK, PB14 MISO, PB15 MOSI) + config/reset GPIOs -> FPGA slave-SPI pins (pairs with FPGA register map in awto-dji/docs/data/fpga-regs.tsv).
5. FPGA reference clock source (XO/crystal) -> dedicated CLK pin and PLL input; the first row of the clock architecture.
6. AD9363 SPI as bridged by the FPGA (SCLK, MOSI, MISO, CS) -> 4 balls.
7. Config flash + JTAG/MSEL pins -> confirms CFG-class function indices.
8. UART (CENTER connector, 256000 8N1), LEDs, reset/boot straps -> a handful of balls.

## 7. What blocks a proper lift
- Interconnect source decode (53,889 unresolved active routes; GPIO nets never reach a LAB input). Blocks pad -> logic tracing, clock architecture, every `reach*` result.
- FF D/CLK/CE/LSR and LUT pin mapping (#106; other agent).
- No IO-standard decode in Mistral (VCCIO is board-level; IOCSR_STD/VOD/termination are partial and noisy).
- No pad direction/oe truth: DATAOUT is the sink of a mux whose source is often "unknown", so outputs are under-seen.
