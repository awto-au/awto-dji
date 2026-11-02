# DJI m2001 — TX-first / loopback simulation (#189 steps 2-4)

> Moved from awtoau/pluribus on 2026-11-01. Paths under `fpga/m2001/` are in this repo (awto-au/awto-dji). `lifters/`, `docs/altera/...`, `reference/` and `tmp/` (lift artefacts such as `tmp/image_sim_dji_push/nl.pkl`) are in the pluribus checkout (`$PLURIBUS_REPO`, see `fpga/m2001/scripts/_repo.py`).

Gate-level sim of the lifted image (RTL emit, Verilator) driven with the real m1400 SPI0 traffic. Tags: **V** observed in sim, **I** inferred, **U** unknown. Capture-derived figures are labelled *(capture)*.

## Setup

- Script: `fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py` (`build` / `stim` / `run` / `analyse` / `rxgen` / `probes`); record builder `fpga/m2001/scripts/cycloneiv_clean_uplink_record.py`. Work dir `tmp/loopback/`, log `tmp/logs/loopback_sim.log`.
- Netlist/RTL: `tmp/image_sim_dji_push/` (rtl vs flat equivalent over 20k cycles). Build 60-70 s / 7 GB; sim ~16-21k clk_main cycles/s with probes.
- Clocks (emit has no PLL; TB-driven): clk_main 100 MHz, pll_b 50 MHz, pll_c 5.6 MHz (U), B14 40 MHz, N25 DATA_CLK 22.4 MHz.
- Stimulus, all from awto-dji (`scripts/re/m1400_fpga_script_decode.py`, `re/ghidra-projects/m1400_radio/m1400_dump.txt`):
  - boot table mode 3: 512 `[0E reg val]` (full regfile twice, reg0 bit7 = copy select), mode writes; the 2,607 bridged AD9363 writes skipped (radio not in sim)
  - post-boot `[0E 01 02]` + reg0 bit0 pulse (FUN_00015b86/FUN_00015b5e); link start: ID regs 3..7 under reg0 bit7, band words 0xBA..0xBE (FUN_0001755c/FUN_00016850/FUN_00016896)
  - per frame (FUN_000171a6 TIMER1 schedule): status reads; band switch 2.4 GHz (FUN_00016ef6: radio 0x004=03/0x005=11 via bridge, 0xB0..0xBE); 56-byte uplink record to 0x44..0x7B + ID block 0x40..0x43/0x7C..0x7F (FUN_0001698a); hop words
  - record CRCs from the firmware tables (V): CRC-16 reflected 0x8408 init 0x55AA; CRC-8 reflected 0x8C init 0xAA (after the 8-byte XOR). Header/stick/key contents are placeholders (U).
- Sim readback of reg 0 returns a rotating single bit (04,02,01,40,...), not the register → stimulus uses an MCU-side shadow instead of read-modify-write. Readback path is a separate open item.

## Results

| Item | Result | Tag |
|---|---|---|
| Regfile writes | load bit-exact in the copy selected by reg0 bit7: reg0=0x08, reg1=0x02 (engine mode), reg2 copy1=0x15, reg9=0x0A/0xDF, record 0x44=0x01, 0x45=0x10 (0x12^key), 0x7B=0x3D (CRC-8) | V |
| Frame counter `cnt_65` (21 FF, (32,89)/(32,90)) | free-running, wraps every **1,400,001 clk_main = 14.000 ms at 100 MHz**, independent of stimulus | V; matches the 14 ms frame *(capture)* |
| Frame FSM (38,86)/(39,86) | settles at state 2 after boot, never moves; AC8 stays high from 9.45 us, AB12 static | V |
| FSM inputs | 52 external leaves over the 4 FSM FFs (`ff_38_86_4/5`, `ff_39_86_0/15`): frame counter (32,89)/(32,90) 21 FFs, ~13 regfile mode bits (incl. reg 0x02 copy1 `ff_38_88_9/12`, `ff_37_84_0/3`), ~18 owned by 802.16-tx / `rx_id_comparator`. `ff_38_79_4` reaches only MCU SPI, FX3 flag and radio-MISO pads in 14 FF hops (control plane, not RX data); `ff_35_67_0`, `ff_30_89_4`, `ff_37_87_0`, `ff_41_86_2`, `ff_54_69_14` reach the 13 RX pads at 9-12 hops | V (static, `cycloneiv_clean_fsm_rxdetect_trace.py`) |
| TX path | playback-RAM write-enable leaves toggle; its 12 data inputs and the 12 pad retime FFs stay 0 → TXD = 0 throughout | V |
| R25 | toggles 50 % duty continuously (TX clock/frame output) | V |
| TX bit order | pad → RAM lane bit (V): L26,L25,K26,J26,H26,H25,G25,H24,F26,G26,E26,E25 = bit 0..11; pins.tsv `TXD_n` draft labels run the other way | V |
| RX bus order | M25,T25,T24,U26,U25,V26,W26,W25,W24,Y25,Y24,AB26,AA25 → M9K (52,74) data[0..12] | V |
| Radio-SPI engine, unforced | emits no frames of its own over 3 frames; every radio frame seen is MCU traffic relayed in mode 1 | V |
| Received-ID register (33-34,89-90) | shifts continuously (descrambler sequence; demod input idle), no comparator match, `cnt_82` idle | V |

### Bypass (Verilator force, one RX-sync FF pulsed 2,000 cycles per 14 ms frame)

- `ff_35_67_0` forced: no downstream change.
- `ff_38_79_4` (`sr_13[2]`) forced: the next stages come alive (V):
  - `cnt_82` (24-bit timer behind the ID-match combiner) starts counting
  - the deserialiser (31,65) loads
  - the radio-SPI engine issues 6 AD9363 frames, SCK = 3 clk_main/bit (33 MHz): `R 0x2B0`, `R 0x2B5`, `W 0x0FA=0xE0` (x2), `R 0x2B0`, `R 0x2B5`
    - UG-672: 0x0FA = AGC Config 1, 0xE0 → gain-control mode 00 = manual; 0x2B0 = Rx1 gain index (readback), 0x2B5 = Rx2 slot
    - reading: on RX lock the FPGA reads both gain indices and freezes the AGC (I)
  - frame FSM, AC8, TX data still static (see "TX data path" below)
- No engine write to 0x00A..0x00F seen → the "/64 BBPLL divider" in section 3 of `fpga/m2001/docs/lightbridge-fpga.md` comes from the MCU boot script (AD_WR 0x00A=0x06 in the mode-3 table), not an FPGA rewrite in this sequence. **U** for other engine triggers.

### Engine control registers as the MCU loads them (boot tables, V)

| Reg | mode3/mode1 copy0 | mode3/mode1 copy1 | mode0 copy0 | mode0 copy1 |
|---|---|---|---|---|
| 0x12 | 00 | 20 | 00 | 2C |
| 0x13 | 00 | 20 | 10 | 25 |
| 0x1B | 00 | 12 | 00 | 12 |
| 0xA0 | 00 | 38 | 04 | 2E |
| 0xA1 | 00 | AC | 0F | AC |
| 0xBF | 00 | 00 | 00 | 00 |

None decodes as an AD9363 clock register address; meaning **U**.

### Real downlink RX (secondary — public captures are not relied on)

- Zenodo `DJI_matrice_100_2G.bin` (SHA-256 verified), burst at +16.52 MHz *(capture)*, mixed/LPF/resampled to 11.2 MS/s *(capture-derived rate)*, 12-bit, 2R2T DDR on the 13 RX pads with N25 as DATA_CLK; 474,836 words played.
- No sync: received-ID register unchanged in character, comparator idle, demux/FIFO/AC11/AC10 static. Not treated as a lift fault: stimulus fidelity (frame pad unknown, channel order, AGC level) is unverified.

### Loopback

Not possible yet: TX produced no samples (TXD = 0), so there is nothing to feed back. The uplink and downlink are also different modems (narrow hopping vs 1024-FFT OFDM *(capture)*), so a loopback non-sync would not be a lift fault.

## TX data path: where TXD = 0 starts (2026-11-02, #91)

Conditions: Verilator, rtl_s emit, m1400 boot-table stimulus, 4-6M clk_main cycles. "Live RX" = `stim_rx.txt` + `rx_m100.txt` (474,836 RX words consumed).

- 30 runs, none opens the TX slot (V): 7 leaf force sets (`--force`), leaf polarity 0 (`--fval 0`), FSM state hold 0..15 (`--fsm N`), live RX with/without forces. In all: TXD words 0, TXD bit toggles 0, AC8 1 toggle (2 in FSM states 2,3,6,8,9,10,13,14).
- `ff_41_86_2` forced 1 cancels the `ff_38_79_4` radio-SPI wake-up; forced 0 does not (V). Wake-up indicator = P19 toggles 2444 vs 2394 unforced.
- The idle RX bus, the FSM state and the RX-lock leaves are not the blocker (V).
- Playback RAM M9K (23,62)/(23,63): simple dual port, write clk_main, one shared `we` (`lc_15_62_13`).
  - write side live: `we` group 1.34M changes / 12M half-cycles, write and read address ~84k changes each (V)
  - 24 data-leaf FFs (18 + 6) share `ena = lc_15_62_13` and never change (V) → their D inputs are 0
  - static: data cone reaches the 13 RX pads at 13 FF hops, plus FX3 flags, radio MISO, SPI pads, `uplink_record_readers`, LFSR r0092 (reach only)
- 227 FFs probed 3 stages back from the data leaves: 108 dead; live ones are control (counter `ff_28_72_6..9`, `ff_24_63_3`, `ff_87_61_2`, `ff_34_61_*`). The whole data chain `ff_19_64_*`, `ff_19_62_*`, `ff_20_62_*`, `ff_21_62_*`, `ff_18_64_*`, `ff_18_61_12` is dead (V).
- Regfile copies. The boot table writes each register twice: copy0 while reg0 = 0xB8, copy1 while reg0 = 0x08 (V, probe value history). Link start writes reg0 = 0x88.

| Reg | copy0 | copy1 |
|---|---|---|
| 0x08 | 0x0F | 0x80 |
| 0x09 | 0x0A | 0xDF |
| 0x02 | 0x00 (never written) | 0x15 (at 945036 half-cycles, when AC8 goes high) |

- The playback gate reads copy0: `ff_26_78_8` = reg 0x08 bit 4, `ff_26_78_15` = reg 0x09 bit 2, `ff_26_78_5` = reg 0x09 bit 3 (V, `cycloneiv_clean_image_sim.spi_regs`).
- Replaying boot table 2 into copy0 as well (copy0 = 0x15 / 0x80 / 0xDF): `ff_26_78_15` goes to 1, playback data FFs still 0, TXD 0, AC8 closed (V). The config copy is not the blocker.
- Gate structure (V, LUT init): chain FFs are 2:1 muxes selected by `ff_26_78_15`, e.g. `ff_19_64_0` D = sel ? `lc_18_64_5` : `ff_18_63_3` (init 0xAACC). Both sources are 0.
- Dead frontier (dead FFs feeding the chain, probed): `ff_18_63_3`, `ff_17_63_14`, `ff_13_62_14`, `ff_18_63_1`; enable `ff_13_61_15` is live (live-RX copy-A replay run, 8M half-cycles), data is 0.
- Frontier expansion (`loopback_mkprobes_frontier.py`, runs pf/ph/pi, same stimulus): the dead chain runs back through `fr1`..`fr5` to five M9K read ports (36,62) (23,61) (36,54) (23,55) (23,54), 4b x 2048 SDP, no init data (0 of 2048 words non-zero), we = `lc_34_61_1` / `lc_34_61_7`.
- Those RAMs are written (output FFs go non-zero once) but only by a few 0->1->0 pulses; write data comes from `ff_102_60/61_*` via `ff_84_61_*` / `ff_87_61_*` (enable `ff_87_61_2`), sequencer enable `ff_32_73_0` <- `ff_31_73_4`.
- Read side: read-address FFs change 1-2 times, at the times of SPI register writes (half-cycles 11148, 45452, 945036, 970124, 1912122). I: the RAMs are register-indexed lookup tables, not RX sample buffers. Not traced one-for-one to the register FFs.
- `ff_31_73_4` also enables `ff_26_72_2` (enable of `ff_15_62_1/2`, in the playback-RAM we cone): I, one sequencer gates both paths.
- Open: which table word is read and whether the table write (`ff_102_60/61_*`, `ff_87_61_2`, `ff_31_73_4`) ever targets it; `uplink_record_readers` outputs (record bytes are non-zero); register group `ff_37_79_*` (`ena = lc_37_82_1`, not in the SPI register map); reg 0x02 copy0 never written.

## Lift faults found

- None localised to a cell. Open: reg-0 readback rotates instead of returning the register (sim artefact or lift fault in the MISO mux, U).

## Not done

- Constant-fold of the boot configuration + yosys opt (#189 follow-up 1).
- Probing past the dead frontier (above).
- Forcing the ID-match combiner `lc_37_90_12` directly: LUT outputs are not named in the RTL emit, so it cannot be forced by name; needs the flat emit.

## Reproduce

```
python3.15t fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py build
python3.15t fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py stim --frames 3 --out stim_tx.txt
python3.15t fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py run --tag tx --stim tmp/loopback/stim_tx.txt --cyc 14000000
python3.15t fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py run --tag f1 --force 1 --stim tmp/loopback/stim_tx.txt --cyc 6000000
python3.15t fpga/m2001/scripts/cycloneiv_clean_loopback_sim.py analyse --tag tx; ... probes --tag f1
```
Force sweep (bounded parallel): `python3.15t fpga/m2001/scripts/loopback_force_sweep.py --jobs 5`.
Probes: `loopback_mkprobes_frontier.py [--trace TAG]` appends backward stages (`fr*`) and head-RAM write/read cones (`hw*`) to the same file. `loopback_mkprobes_ram.py` writes `tmp/loopback/probes_ram.json` (playback-RAM cones, 3 upstream FF stages, regfile copies 0x00/0x02/0x08/0x09); rebuild the sim after changing it. Decoders: `loopback_probe_boundary.py TAG` (dead FFs with live inputs), `loopback_probe_regs.py TAG` (register value history). The sim also reads `tmp/loopback/probes_extra.json` if present (earlier regfile/TX-RAM set from `spi_regs`; the file was overwritten on 2026-11-02 and not regenerated).
Static traces: `cycloneiv_clean_fsm_rxdetect_trace.py`, `cycloneiv_clean_playback_ram_trace.py` (`--nl tmp/image_sim_dji_push/nl.pkl`).
