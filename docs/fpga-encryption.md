# FPGA bitstream encryption: status

One-stop status. The evidence lives in the linked sources and is not repeated here. Detection only: no key handling or recovery.

## Per image (2026-10-26)

| Image | Family | Encrypted? | Lift possible? |
|---|---|---|---|
| `m1900` air (P3, Inspire 1, same bytes) | Cyclone V e50f | Yes, strong circumstantial | No: CRAM is opaque |
| `m2000`, `m2002` ground | Cyclone V | Yes, strong circumstantial | No |
| `m2001` ground (LB2) | Cyclone IV GX, best match EP4CGX150 | **No**: the family has no bitstream encryption, and the payload decompresses with valid CRCs | Yes once pluribus decodes Cyclone IV fabric (pluribus #117) |
| P3S `m1900` | not re-classified | - | - |

## Cyclone V images: the evidence

- Full test table, controls and option-RAM bits: pluribus `docs/cyclonev-compressed-rbf.md`, section "Encrypted bitstreams". Tool: pluribus `scripts/cyclonev_encryption_probe.py`.
- In short: PRAM is cleartext with valid CRCs. CRAM is statistically uniform random, with no ECB repeats and no shared keystream between two builds. Option-RAM bits differ from every Quartus build.
- Open: no encrypted reference stream exists. So the flag bits, cipher mode and layout are inferred, and "Altera AES" vs "producer keyed scramble" is not settled.
- Lift-realism test (lifted statistics vs the Quartus-built corpus and a random control): results in [fpga-images.md](fpga-images.md).

## Cyclone IV (`m2001`)

- Cyclone IV E/GX have no design-security (AES) feature: the Cyclone IV handbook vol. 1 (`pluribus/sources/altera/Cyclone_IV_Device_Handbook_vol1.pdf`) has a compression chapter and no security or encryption section. In that generation only Cyclone III LS has AES.
- `m2001` unpack: Cyclone III/IV container, header CRC-16 ok, decompresses to 6,154 CRAM frames (pluribus `scripts/cycloneiv_decompress.py`).
- Open: the decoder covers EP4CE6 only. GX150 fabric decode is not done (pluribus #117).

## How Cyclone V keys work (public docs)

- Cyclone V handbook vol. 1 (Design Security) and AN 556 (`pluribus/sources/altera/AN556_design_security.pdf`): AES-256 hardware decryptor, one user 256-bit key.
- The key is never in the bitstream file. It is programmed into the device once, over JTAG: volatile (battery-backed RAM) or non-volatile (eFuse, one-time). That fits a factory step, not a firmware update.
- A field update then only ships the already-encrypted file. The device decrypts on load.
- `KEY_VERIFY` over JTAG reports the key state (none, volatile, non-volatile) without revealing the key. It is the cheapest device-side proof.

## Write path (air)

- The image reaches the FPGA over USB, not DUML packets: A9 to FX2LP (m1500) to FPGA. The FPGA side most likely writes its own configuration flash. Details: [fpga-write-path.md](fpga-write-path.md).

## What would settle the Cyclone V question

- `KEY_VERIFY` read over JTAG from a bench unit.
- One encrypted `.rbf` from a Quartus edition entitled to design security, compared bit for bit with the option RAM and CRAM start.
- A key-programming JTAG sequence in factory or service firmware.
