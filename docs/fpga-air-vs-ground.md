# Air vs ground FPGA: what fixes the side, what is still open

Scope & safety: see `SAFETY.md`.
Tags: **V** verified in code/strings/bytes (file + offset or exact string cited), **I** inferred, **U** unknown.
Related issues: #9 (P01007.06 board role), #3 (air die unidentifiable), #18 (air config-memory writer).
Method note: strings/header work on the P3X V01.03.0020 and V01.11.0020 unpacked modules; offsets are file offsets
into the unpacked module unless marked "addr". Reproduce with `strings -n 4 -t x <module>` and the xV4 entry parse below.

## Verdict

| Image | Side | Evidence | Tag |
|---|---|---|---|
| `m1900` | air | (1) Ships in the aircraft-only package `P3X_FW_V01.11.0020.bin`: xV4 entries are m0306 m0305 m0400 m1100 m1101 m1200-1203 m1500 m1700 m1701 **m1900** m0100 m0101 m0800 m0900; no m1400, no m2000-m2002. (2) Entry target byte `0x13` = kind 19. (3) Air MCU m0900 handles receiver `0x13` (Enter Loader/Confirm/Finish) and drives the FPGA over SPI2. (4) Camera `m0100` name table slot 19 = `FPGA.A`. | V (side by package + peer wiring + DJI's own `.A` tag); I that `.A` means "air" |
| `m2000` | ground | Not in the aircraft package; ships in the combined/RC package (`P3X_FW_V01.03.0020.bin` entry target `0x14` = kind 20, model 0; C1 RC package per `fpga-images.md`). Ground MCU m1400 handles receiver `0x14` with the same FPGA register code. Slot 20 = `FPGA.G`. | V (package + m1400 code), I (`.G` = ground) |
| `m2001` | ground | Same, target `0x34` = kind 20, model 1. | V for side; family is I (see below) |
| `m2002` | ground | Same, target `0x54` = kind 20, model 2. | V |

The FPGA images themselves carry no side information: `strings` over `m1900`/`m2000`/`m2001`/`m2002` finds no banner,
build string, "air", "gnd", "ground", "FPGA", Quartus or Cyclone token (only random ASCII runs; the leading `0x20`/`0x80`
bytes are `0xFF`). **V** (negative). Do not expect the bitstreams to say which side they are.

## Resolved points

**R1. DJI's own labels in firmware (V).** Aircraft camera `m0100` (V01.11.0020) holds a DUML module-name table of 8-byte
slots starting at file offset `0x71440`: `CAMERA TERMINL MAINCON GIMBAL CENTER TELECON WIFI DM368.A 1765.A PC BATTERY ESC
DM368.G 1765.G 68013.A 68013.G ONE EYE TWO EYE FPGA.A FPGA.G ...` (`0x714d0` = `FPGA.A `, `0x714d8` = `FPGA.G `). Slot
index + 1 = receiver type: `1765.A` at `0x71480` is type 9 (m0900), `1765.G` at `0x714a8` is type 14 (m1400), `FPGA.A`
is type 19, `FPGA.G` is type 20. The same strings exist in V01.03.0020 `m0100` (`0x6ef1c`, `0x6ef24`). Arithmetic and
the 9/14 cross-check against known MCU roles make the type mapping V; that `.A`/`.G` mean air/ground is I (paired
with `DM368.A/.G` and `68013.A/.G` whose roles are independently known).

**R2. Public tag sources are external, not firmware.** The strings `HD transmission FPGA air side` / `gnd side` and the
`FPGA Air`(19) / `FPGA Ground`(20) names are in the o-gs dissector (`dji-dumlv1-proto.lua` lines 46-47, 103-104), and
`FPGAA`/`FPGAG` in `dji_xv4_fwcon.py` (`DjiModuleTarget(19,..)`/`(20,..)`, lines 103-106). They are **not** found as
strings in any firmware image checked. They agree with R1, but they are corroboration, not firmware proof. The app side
also names them: type 19 `FPGA`, type 20 `FPGA_G` (`DeviceType.java:15,25-26`, per `app-upgrade-sequence.md`). V (as
sources), external for the dissector/tool.

**R3. Container kind byte (V).** xV4 entry `target & 31` = kind, `target >> 5` = model. Parsed from
`P3X_FW_V01.03.0020.bin`: m1900 `0x13`, m2000 `0x14`, m2001 `0x34`, m2002 `0x54`; minor version equals model
(1.0.2144 / 1.0.2107 / 1.1.2107 / 1.2.2109). The same kind 19/20 split is the DUML receiver type used by the MCUs.

**R4. MCU-side routing (V, with I on semantics).**
- m0900 (air, STM32F103): dispatch keys use receiver 9 (MCU) and `0x13` (`docs/fpga-upgrade-path.md`); reads FPGA id
  word from regs `0x8B..0x8E` (`0x0800cf9e`), stores it at RAM `0x200000f4` in the boot handshake (`0x0800d072`-
  `0x0800d07a`), and compares it to `0x010007ec` in Confirm (`0x0800d1ea`).
- m1400 (ground, LPC1765): receivers `0x0E` and `0x14`; the same register protocol, bit-record table and
  `0x010007ec` compare (`docs/ground-upgrade-path.md`, `c1_m1400.tsv` `fpga_read_id_word 0xde5c`).
- m0900 sends types 3, 5, 10, 11, 12, 18, 21, 23 out USART1 and types 1, 4, 8, 15 out CAN `0x412`
  (`m0900-can-channels.md`): peers are the FC, gimbal, camera, DM368 and the aircraft FX2 (`68013.A`). V. So the board
  m0900 runs on, and the FPGA it configures, are on the aircraft. I (link between "peer is an aircraft module" and "this
  FPGA is on the aircraft").
- m1400 strings are RC-only: `StickErr` (0xcc0), `FpgaErr` (0xccc), `RfModuleErr` (0xcd4), `Battery < 600mh` (0xd08),
  `GIMBAL_CTLIP:%d` (0xc10), `$GPGGA`/`$GPRMC` (0xc788), `MASTER`/`SLAVER` (0xba0/0xba8). V. So `FpgaErr` is the ground
  FPGA's fault flag in the RC status line. I (that the flag is the m2000-2 FPGA).

**R5. Boot/log strings that name the FPGA (V).** m0900 V01.11.0020: `Fpga Boot : %d` (`0x5cd4`), `Fpga Cfg : OK`
(`0x5ce8`), `Fpga Cfg : Error` (`0x5cf8`), `Phantom2X` (`0x5ca8`), `Error: ad9363 reg17 - %.2X` (`0x7784`),
`Error: ar8003 reg7C - %.2X` (`0x77a0`), query-info string ` WM32X A4_FPGA 20150902|01` (`0xa5ef`; sibling of m1400's
`WM610 A7_1765 20160321/01`, `c1_m1400.tsv`). These say "this MCU image configures an FPGA board variant (A4_FPGA)" but
carry no air/ground word of their own; the shared m0900 image also knows the Artosyn AR8003 variant. V strings, I
meaning. The ground m1400 in V01.03.0020 has no `Fpga Cfg` log lines and no `A7_1765` string (grep, V).

**R6. Superseded id in the survey (V).** `air-id-and-stream-survey.md` says "FPGA = fw-id 10"; `fpga-write-path.md`
corrects the UEG numbering to FPGA = 11 (`0xb`, path `PFPGAFw3.bin`, type 19; camera strings `0x7bb01a`). The table
is a shift-by-one error; type 19 is unaffected.

**Strength of the main assignment.** air to m1900 and ground to m2000/m2001/m2002 is **V at the package + MCU-routing
level** (three independent firmware facts: aircraft-only package, receiver 0x13 vs 0x14 wiring, DJI's `.A`/`.G` table)
and **I only in the sense of word meaning** ("A"="air"). No firmware string spells "air FPGA" or "ground FPGA".

## Still open

**(a) Issue #9, is P01007.06 the air or RC board? Leans air (I).**
- The wiki-sourced board facts (W, `rf-sdr-and-repair.md`): P01007.06 has an `STM32F103CBU6` MCU, Cyclone V
  `5CEFA4U19I7`, and its `CENTER` connector goes to the ESC center board.
- V: the air-side MCU is STM32F103 (`air_router_stm32f103`, m0900); the RC's is LPC1765 (`gnd_rc_lpc1765`, m1400, `MCG1765A`, `ground-upgrade-path.md`).
  No STM32 is in any RC module list entry.
- I: an STM32F103 + `CENTER` to the ESC board = the aircraft's board. The wiki calling it the "OFDM Receiver board"
  (the aircraft receives the uplink) does not contradict this. U: the wiki text itself; no schematic.
- Residual U: which m0900 board code (2/4/5, AD9363 + FPGA) the part is (`dataflow.md`); the air die identity (#3).

**(b) Which of m2000/m2001/m2002 maps to which RC hardware revision. U.**
- V: minor version = container model (0/1/2); builds 2107/2107/2109 (`fpga-images.md`); the app's pack list also names
  an `m2003` (`app-upgrade-sequence.md` line 222). I: model index selects by RC board revision, no table found.
- No selector string in m1400 maps a board code to a model.

**(c) m2001 family (Cyclone IV GX-format) vs m2000/m2002 (Cyclone V). I: a distinct ground board variant.**
- V: m2001 has the Cyclone III/IV `.rbf` header (valid header CRC16, 43 bytes, `fpga-images.md`); the others have the
  Cyclone V layout. A bitstream for one family does not configure the other (general FPGA fact). So if the family
  verdict holds, m2001 targets a different FPGA part, hence a different board. The family call for m2001 is
  "best match EP4CGX150, moderate" (one header bit from EP4CGX110): I. No netlist; the old Mistral decode is void (#114).
- U: which RC product(s) carry each part; whether the owner's GL300C has m2000, m2002, or neither (the Artosyn-ASIC
  revision uses no FPGA image, `fpga-images.md`).

**(d) Issue #18, air config-memory writer: U.** Image bytes reach the FX2 slave FIFO via the camera USB path
(`fpga-write-path.md`); nothing in this pass (strings, package headers) addresses the final writer.

## Prove-it plan (cheapest first)

1. **Live GetVersion to type 20 / 19 (no hardware opened, ~minutes). Settles (b) for the owner's RC; confirms side.**
   - Send DUML set 0 cmd 0x01 (Get Device Version) to receiver 20 (RC; m1400 returns the FPGA id word, RAM
     `0x10000344`, `0xde5c`) and to receiver 19 (via m0900 `0x0801226e`, words from RAM `0x200000f4/f8`). The app
     already queries `FPGA_G` and `FPGA` this way (`app-upgrade-sequence.md` section 4).
   - I (to be tested): the id word uses the package version encoding `major<<24 | minor<<16 | svn`. Supporting
     observation: `0x010007ec` = 1.0.2028 in that encoding, adjacent to the shipped svn range 2107-2144. Expected
     replies: m1900 `0x01000860`; m2000 `0x0100083b`; m2001 `0x0101083b`; m2002 `0x0102083d`. A match on the RC reply
     gives the loaded ground image (b) and, if `0x0101....`, evidence for (c). Existing capture scripts:
     `scripts/re/duml_cli.py`, `get_identity.py`. A mismatch means the word is not the version (still informative).
2. **Grep the live log/status already emitted (no capture).** The RC status line carries `FpgaErr`; the air MCU prints
   `Fpga Boot : %d` / `Fpga Cfg : OK|Error` (R5). If any serial tap exists on m0900 USART3/UART logs, the boot
   status distinguishes configured vs not. These strings do **not** name the side; they only confirm the FPGA bring-up.
3. **Board marking / photo (U-to-V for #9, (c)).** Read the PCB silkscreen (`P01007.xx`) and the FPGA top marking on
   the aircraft's OFDM board and the RC board. `5CEFA4U19I7` on the STM32F103 board that cables to the ESC center board
   settles #9 and gives the air die for #3; a Cyclone IV GX marking (`EP4CGX...`) on an RC board settles (c).
4. **JTAG IDCODE (U-to-V for #3, (c)).** P01007.06 exposes JTAG pads (W, `rf-sdr-and-repair.md`). Read the 32-bit IDCODE:
   Cyclone V E A4 vs Cyclone IV GX differ, so one read fixes the family and die for that board. Needs opening the
   hardware; the RC-side equivalent needs the pads located first (U).
5. **Firmware selection logic (U-to-V for (b)).** Trace the RC-side consumer of type-20 TranslateData and the app's
   `rc1url`/`rcurl` pack-list selection (`app-upgrade-sequence.md` section 3, "U: route of TranslateData frames
   addressed to type 20") to see how model 0/1/2 is chosen from the RC's reported hardware ID. Static work only.
6. **Over-the-air capture is not needed** for any point above; it matters only for the PHY/encryption question, which
   this doc does not touch (`link-security.md`, `what-is-actually-secret.md`).

Do not revive the void m2001 Mistral decode (#114) as evidence for any item here.
