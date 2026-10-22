# Proving the model by reversing the MCU code (status + method)

The link model in this repo is built from inference + partial evidence. The **proof is in
the MCU firmware**. This tracks, per claim, what to find, what is confirmed so far, and the
method — honestly separating "shown" from "needs more work / tooling".

## Claim -> where it is proven

| Claim | Proof target | Status |
|---|---|---|
| ID is CPU-placed cleartext data | DUML "Connected Master Id" handler storing + emitting the ID on the data path | **partial** — `m1400` has `MASTER`/`TestMaster`/`FpgaErr` strings; handler not yet traced to the send |
| FPGA is just the datastream (control via GPIO, data via UART) | MCU GPIO = discrete control strobes; data over UART | **shown on `m1400`** — GPIO routine at 0x1234 does FIOSET/FIOCLR bit toggles; UART ISR present; no SPI (see `id-entry-point.md`) |
| Whitening is stock / at most a seed | MCU writing (or not) a scrambler-seed/frame-mode register to the FPGA | **not yet** — needs the FPGA bring-up path in `m0900`/`m1400` |
| PHY is WiMAX-family with standard params | `m0900` AD9363 SPI register sequence decoded vs UG-570 | **partial** — SPI confirmed; config is runtime-computed, not a static table (below) |

## Confirmed so far

- **`m1400` (ground, LPC1765):** GPIO = discrete FPGA control lines (FIOSET/FIOCLR bit
  set/clear); data path is interrupt-driven UART; **no SPI**. Strings `FpgaErr`, `MASTER`,
  `TestMaster`. => FPGA treated as a configured modem, ID handled in MCU software.
- **`m0900` (air, STM32F103):** app at `0x08008000` (SP `0x20004cb8`, reset `0x08008201`).
  Uses **both SPI1 (`0x40013000`) and SPI2 (`0x40003800`)** plus USART1/2/3. One SPI is the
  **AD9363 control bus** (control-plane-re.md); USARTs carry DUML.
- **The AD9363 config is runtime-computed, not a static table.** A static scan for an
  AD9361/3 register table found only `(start,end,index)` descriptor arrays (regular 0x14-wide
  ranges), not register/value pairs. So DJI's driver computes registers from a profile (as
  the ADI no-OS `ad9361.c` does), and the register sequence does not exist as a decodable
  blob in flash.

## Method to finish the proof

1. **AD9363 params (strongest single proof).** Because the config is runtime-computed,
   **emulate `m0900`'s init and capture the SPI writes**, then decode against UG-570 ->
   exact centre frequency / channel bandwidth / sample rate. Tool: **Renode** (full STM32F103
   peripheral models incl. SPI; Unicorn is CPU-only and diverged — see
   `fpga-emulation-plan.md`). Renode is **not installed in this analysis env**; this is the
   gated step. Alternative: statically reverse the driver's BBPLL/clock math (harder, noisier).
2. **ID framing (proves "cleartext, CPU-placed").** Trace the DUML "Connected Master Id"
   handler in `m1400`/`m0900` from the USART parser to where the stored ID is emitted; show
   it travels as a DUML field (encrypt_type 0), not inserted by the FPGA.
3. **Scrambler seed (proves "stock / seed-only").** In the FPGA bring-up path, look for a
   seed/frame-mode register write to the FPGA. None => whitening fixed in the bitstream
   (stock). One => recover the seed value (still not a cipher).

## Honest bottom line

Reversing the MCUs is the right way to turn the model from well-supported inference into
proof, and the control-plane claims are already partly shown on `m1400`. The decisive RF
parameter proof needs **emulation (Renode) to capture the runtime AD9363 config** — not
available in this environment, so it is the clear next-tooling step rather than something a
static pass can finish. No part of this requires defeating a secret; it is interoperability
analysis of the operator's own device.
