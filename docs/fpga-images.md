# FPGA image inventory

Lightbridge FPGA images from the unpacked firmwares. (Images live in the analysis env, not in this repo.)
Family evidence: pluribus `docs/cyclonev-compressed-rbf.md`, `scripts/fpga_family_probe.py`, `scripts/fpga_family_compare.py`.

| Image | Role | Size | Used | Version | Entropy | SHA-256 (16) | Family |
|---|---|---|---|---|---|---|---|
| P3 `m1900` | air FPGA (TX, `air_fpga_cyclonev`) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` | Cyclone V e50f-family (header/PRAM CRC); CRAM encrypted |
| Inspire 1 `m1900` | air FPGA (TX, `air_fpga_cyclonev`) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` | same image |
| LB2 `m2000` | ground FPGA rev 00 (`gnd_fpga_cyclonev_r0`) | 8 MiB | 4.65 MB | 01.00.2107 | 7.99 | `39a74d8d4a69ebaf` | Cyclone V (0x80 preamble, nibble-shifted sync); encrypted |
| LB2 `m2001` | ground FPGA rev 01 (`gnd_fpga_cyc4gx_r1`) | 8 MiB | 2.12 MB | 01.01.2107 | 5.84 | `b6cc5e96f12446b1` | Cyclone III/IV-format; best match EP4CGX150 |
| LB2 `m2002` | ground FPGA rev 02 (`gnd_fpga_cyclonev_r2`) | 8 MiB | 4.80 MB | 01.02.2109 | 7.99 | `30aa24c31e5180a7` | Cyclone V; encrypted |
| P3S `m1900` | air FPGA (TX) | 4 MiB | 2.01 MB | — | — | (independent sample) | not re-classified |

## Observations

- Air/ground assignment (m1900 = air, m2000/01/02 = ground) is V from the package split + MCU routing + DJI's own in-firmware `FPGA.A`/`FPGA.G` module-name table in `m0100` — see `fpga-air-vs-ground.md`.
- Air FPGA is one shared bitstream: P3 and Inspire 1 `m1900` are byte-identical (sources: `P3X_FW_V01.11.0020`, `WM610_FW_V01.11.01.50`).
- Ground FPGA has three board-revision variants (`m2000/01/02`, versions 2107/2107/2109) from `C1_FW_V01.06.0000`; they differ ~55% from each other.
- The three ground images are not the same family: m2000/m2002 are Cyclone V streams, m2001 is Cyclone III/IV-format.
- `m2001`: 0x20 FF preamble, 43-byte Cyclone III/IV `.rbf` header with valid header CRC16. Best match Cyclone IV GX EP4CGX150 (moderate: one header bit separates it from EP4CGX110). Payload ~2.12 MB, probably compressed (entropy 5.84), not decoded.
- `m1900`, `m2000`, `m2002`: ENCRYPTED, strong circumstantial; option-bit meaning inferred; may be a producer-side keyed scramble rather than Altera AES. CRAM indistinguishable from uniform random (entropy 7.9999, chi-square z within +-1.8), PRAM cleartext with valid CRCs.

## Void claims (pluribus #114)

- "Mistral decompiled m2001 against 5CEBA4U19C8: 56,337 routes, 1,832 LABs, 31 M9X9 DSP, 224 pins" was decode noise from a preamble-stripping bug (stripped input decodes to ~100k lines instead of ~375). Route counts are not a quality check.
- "No die resolves for the air m1900" used the same stripped input; the air image is Cyclone V e50f-family by header/PRAM CRC.
- "m2001 is an unencrypted Cyclone V bitstream" and every ground pin/DSP/OFDM-datapath inference built on it are withdrawn. See `ground/fpga/NOTES.md`.

## What's missing

- The Artosyn-ASIC board revision has no FPGA bitstream (logic hardened into the AR8001 ASIC; see `control-plane-re.md`).
- No ground or air FPGA netlist exists. Next: decode m2001 as a Cyclone IV GX payload (compression format); obtain the key or an oracle for the encrypted images; physical part marking / JTAG IDCODE confirms the family.

## Lift-realism test (2026-10-26)

Detection only: does the image lift to logic or noise? No key handling.
Tool: pluribus `scripts/lift_realism.py` (branch `worktree-agent-af72405071c975740`, commit `158964bd3`), native decoder, `cyclonev_unpack.py --allow-invalid` (validation bypassed, statistics only).
Reference: 256 Quartus-built Cyclone V e50f designs (re-lifted, largest 825 LUTs / 1040 FFs) and 3 random-CRAM controls on the same die (1 x uncompressed random frames with CRC16 recomputed; 2 x random nibble-coded stream of the image's length, same decode path as the images).

Images run (all located locally; SHA-256 prefix 16):

| Image | SHA-256 (16) | Native decoder (strict) | Lifted (bypass) |
|---|---|---|---|
| P3 `m1900` 01.11.0020 | `f3a55dea4dc8c0d4` | refused: first CRAM frame marker `bdd0aa` != `843e01`, coded entropy 7.997 | 8227 LUTs, 9720 FFs, 28875 nets |
| Inspire 1 `m1900` (carved from WM610_FW_V01.11.01.50) | `f3a55dea4dc8c0d4` | same bytes, same refusal | identical `.bt` and counts |
| P3S `m1900` 01.01.0008 (= P3X 01.01.0006) | `0ecafe1ab6583407` | refused: marker `de000e`, entropy 7.997 | 8013 LUTs, 9526 FFs, 28307 nets |
| LB2 `m2000` | `39a74d8d4a69ebaf` | refused: marker `1e0100`; die byte 0x13 (PRAM 58 x 916), not e50f | not lifted: no tables for this die |
| LB2 `m2002` | `30aa24c31e5180a7` | refused: marker `760da0`; die byte 0x13 | not lifted: no tables for this die |
| LB2 `m2001` | `b6cc5e96f12446b1` | not Cyclone V (no `jjjj` sync); Cyclone IV decoder: header CRC ok, F = 796, 6154 / 6154 CRAM frame CRCs valid, 4,928,127 B | no lifter for Cyclone IV |

- P3S `m1900` (0ecafe..., 2.01 MB) is a different image from P3 `m1900` (f3a55d...): the older 01.01.x air FPGA. Both: die byte 0x05, PRAM 64 x 524, e50f geometry.

Metrics that separate corpus from control (corpus range / control / image P3 | P3S):
- FF with clock: 1.0 / 0.37-0.41 / 0.42 | 0.42
- FF with D driven: 1.0 / 0.49-0.76 / 0.74 | 0.74
- distinct FF clock nets: 1-2 / 1277-1807 / 1815 | 1824
- sink nets with no driver: 0 / 0.29-0.31 / 0.29 | 0.30
- output pads driven: 1.0 / 0.15-0.29 / 0.26 | 0.25
- constant LUT masks: <= 0.077 / 0.58-0.69 / 0.70 | 0.69
- LUT count 8227 | 8013 vs nibble-coded controls 8273, 8382; FF count 9720 | 9526 vs 9745, 9696. Corpus max 825 / 1040.
- Of 9 discriminating metrics: image in control range 8 (P3) and 9 (P3S); in corpus range 0 (one P3 metric outside both).

Verdict: both e50f images (P3 and P3S `m1900`) lift to noise, indistinguishable from random CRAM; they do not lift to realistic logic.
- Consistent with the earlier statistical finding that CRAM is uniform random: encrypted or otherwise scrambled; this test does not distinguish the two.
- `m2000` / `m2002`: no lift possible (different die, 02B130DD-class geometry); only the entropy result (7.997-7.998) stands.
- Log: pluribus `tmp/logs/lift_realism.log` (not committed).

## `m2001` Cyclone IV GX150 test pass (2026-10-26)

Detection only; image read in place (`firmware/unpacked/C1_FW_V01.06.0000/C1_FW_V01.06.0000_m2001.bin`, SHA-256 `b6cc5e96f12446b1...`). Tool: pluribus `scripts/cycloneiv_image_pass.py`, tables learnt from 150 Quartus-built EP4CGX150 designs; method and corpus/control numbers in pluribus `docs/cycloneiv-bitstream.md` "Third-party image test pass".

- Die: EP4CGX150 (full die, STINGRAY4), not EP4CGX110: option lane 1 bytes `00 20 0d` match every EP4CGX150 build and differ from every EP4CGX110 build (`00 a0 0d`) in one bit; that bit follows the die variant, not package or speed grade. Pluribus #117.
- Decoded: 2,178,780 set CRAM bits (5.5% of positions); 6154 / 6154 CRAM frame CRCs valid; not encrypted.
- Verdict: real logic. 89,283 of 149,760 LEs carry a nonzero mask (59.6%), 7,077 of 9,360 LABs active; no constant masks; 3,077 distinct masks; common functions `ff00` (buffer) 5,494, `9617` 3,102, `698e` 2,904, `f0f0` 2,370; 11,337 carry-form masks (12.7%); mask support 4 / 3 / 2 / 1 inputs: 50.1 / 31.7 / 8.9 / 9.3%.
- Routing: 6.4% of nonzero LAB muxes read as no known source (built designs 3.6-4.2%, shuffled control 43%); 73.1% of the LE inputs a mask depends on trace to one driver (built designs 74-82%, control 2.2%).
- IO: 16 output and 21 input sites match the learnt signatures (only the 176 / 249 sites seen >= 12 times in the corpus have one); edges right 10 + 12, top 5 + 7, bottom 1 + 2, none on the left.
- Claimed by the decode: 90.1% of set bits (unclaimed 214,628: clock tree, IO routing, M9K, multipliers, PLL, transceivers).
- Not done: a lifted netlist; the checks show statistics, not correctness.

## Running a decoded stream — emulator availability per chip

No netlist exists yet, so this is method, not current capability.

- **MCUs m0900 (STM32F103) / m1400 (LPC1765):** Renode models the peripherals, runs unmodified firmware, and co-sims Verilated HDL peripherals — the right tool (write a `.repl`). QEMU has partial STM32 board models.
- **Cyclone-V FPGA:** Project Mistral is the bitstream→netlist decoder (same project family as IceStorm/Trellis/prjxray). It maps LAB/LUT/FF/routing but not DSP/M10K internals yet. No tool runs a foreign `.rbf` as opaque silicon without decoding it first; full fidelity = load the de-packed bitstream on a matching 5CEBA4/e50f board.
- **A9SE / DM368 / DM365:** no full emulator (QEMU user-mode, CPU only).
- **AD9363 / FX2LP:** behavioral models, attachable to Renode.

Once a stream decodes: decode→netlist→Verilator sim, black-boxing DSP/M10K, with MCU firmware in Renode as stimulus and a known all-0s payload; reconcile sim output against a real capture to constrain the black boxes. Fuller writeup (premise void — assumes a decoded netlist that does not exist): `debris/fpga-emulation-plan.md`.
