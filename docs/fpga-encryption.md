# FPGA bitstream encryption: DJI images

Per-image status only. Family support, key mechanism and the detection evidence: pluribus `docs/fpga-encryption.md`. Detection only: no key handling or recovery.

| Image | Family | Encrypted? | Lift possible? |
|---|---|---|---|
| `m1900` air (P3, Inspire 1, same bytes) | Cyclone V e50f | Yes, strong circumstantial | No: CRAM is opaque |
| `m2000`, `m2002` ground | Cyclone V | Yes, strong circumstantial | No |
| `m2001` ground (LB2) | Cyclone IV GX, best match EP4CGX150 | **No**: Cyclone IV cannot encrypt; header CRC ok, decompresses to 6,154 CRAM frames | Yes once pluribus decodes Cyclone IV GX fabric (pluribus #117) |
| P3S `m1900` | not re-classified | - | - |

- The Cyclone V verdict rests on the evidence in the pluribus doc; that doc's "4 third-party flash images" are these images.
- Lift-realism test (lifted statistics vs the Quartus-built corpus and a random control): [fpga-images.md](fpga-images.md).
- Write path (air): the image reaches the FPGA over USB, A9 to FX2LP (m1500) to FPGA; the FPGA side most likely writes its own configuration flash. Details: [fpga-write-path.md](fpga-write-path.md).

## What would settle the Cyclone V images

- `KEY_VERIFY` read over JTAG from a bench unit: reports key state (none, volatile, non-volatile) without revealing the key.
- A key-programming JTAG sequence in factory or service firmware.
- One encrypted reference `.rbf` (generic, see the pluribus doc).
