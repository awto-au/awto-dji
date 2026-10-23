# FPGA image inventory

Lightbridge FPGA images from the unpacked firmwares. (Images live in the analysis env, not in this repo.)
Family evidence: pluribus `docs/cyclonev-compressed-rbf.md`, `scripts/fpga_family_probe.py`, `scripts/fpga_family_compare.py`.

| Image | Role | Size | Used | Version | Entropy | SHA-256 (16) | Family |
|---|---|---|---|---|---|---|---|
| P3 `m1900` | air FPGA (TX) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` | Cyclone V e50f-family (header/PRAM CRC); CRAM encrypted |
| Inspire 1 `m1900` | air FPGA (TX) | 4 MiB | 2.06 MB | 01.00.2144 | 7.98 | `f3a55dea4dc8c0d4` | same image |
| LB2 `m2000` | ground FPGA rev 00 | 8 MiB | 4.65 MB | 01.00.2107 | 7.99 | `39a74d8d4a69ebaf` | Cyclone V (0x80 preamble, nibble-shifted sync); encrypted |
| LB2 `m2001` | ground FPGA rev 01 | 8 MiB | 2.12 MB | 01.01.2107 | 5.84 | `b6cc5e96f12446b1` | Cyclone III/IV-format; best match EP4CGX150 |
| LB2 `m2002` | ground FPGA rev 02 | 8 MiB | 4.80 MB | 01.02.2109 | 7.99 | `30aa24c31e5180a7` | Cyclone V; encrypted |
| P3S `m1900` | air FPGA (TX) | 4 MiB | 2.01 MB | — | — | (independent sample) | not re-classified |

## Observations

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
