# m2001 decompile findings — VOID (2026-10-24)

- This document previously reported a Mistral `decomp` of `m2001` against `5CEBA4U19C8`: LUT masks, DSP modes, M10K contents, 70,007 routes, 53,889 unresolved routes, an "interconnect gap" and an LFSR-hunt follow-up.
- All of it was decode noise (pluribus #114): `m2001` is not a Cyclone V stream; the decode came from a preamble-stripping bug. Stripped input decodes to ~100k lines instead of ~375; route counts are not a quality check.
- The "DSP/M10K wall was wrong" correction is withdrawn with it. Mistral's own README statement (DSP and M10K not decoded) stands for Cyclone V.
- What `m2001` is: Cyclone III/IV-format stream, 0x20 FF preamble, 43-byte `.rbf` header with valid header CRC16, best match Cyclone IV GX EP4CGX150 (moderate: one header bit separates it from EP4CGX110). Payload ~2.12 MB, probably compressed, not decoded. Evidence: pluribus `docs/cyclonev-compressed-rbf.md`, `scripts/fpga_family_probe.py`, `scripts/fpga_family_compare.py`.
- Still valid and independent of the FPGA: the cheapest route to the whitening is recognising the standard WiMAX scrambler (`x^15+x^14+1`) and solving the seed from an all-0s / repetitive capture (`alternative-approaches.md`). No FPGA netlist exists to extract an LFSR from.
- Inventory and family verdicts: `fpga-images.md`.
