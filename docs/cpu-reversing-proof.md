# Proving the model by reversing the MCU code (status + method)

The link model in this repo is built from inference + partial evidence. The **proof is in
the MCU firmware**. This tracks, per claim, what to find, what is confirmed so far, and the
method — honestly separating "shown" from "needs more work / tooling".

## Claim -> where it is proven

| Claim | Proof target | Status |
|---|---|---|
| ID is CPU-placed cleartext data | DUML "Connected Master Id" handler storing + emitting the ID on the data path | **shown (role path)** — traced the RC role/pairing state machine at `m1400:0x9bd0`: cleartext field parse into RAM, no crypto (below). Binding-`Id` handler itself not yet isolated |
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

## Traced: RC role/pairing state machine (`m1400` @ 0x9bd0)

Disassembled with radare2 (`-a arm -b 16 -m 0`). The strings `MASTER` (0x9db4) / `SLAVER`
(0x9dbc) are reached by **PC-relative `ADR`** (why no literal-pool or `MOVW` match exists; a
raw address byte-search cannot find ADR refs). The referencing function is the RC role state
machine:

```
0x9bd0  ldrb r0,[recv]; ubfx r0,r0,2,2   ; extract a 2-bit ROLE field from a received byte
0x9bd6  cmp r0,[r4,0x18]                  ; vs the stored role; skip if unchanged
        switch(r0): 1 -> MASTER (0x9be6), 2 -> SLAVER (0x9c20), 0 -> none (0x9c42)
MASTER: copy [r5,0x07]->state+0x2e (u32), [r5,0x0b]->+0x32 (u16),
        [r5,0x1d]/[r5,0x1e] bytes -> state; adr r1,"MASTER"; movs r0,3; bl 0x5d6c  (log)
SLAVER: set slave flags [r5,0x1c]=1,[r5,0x0f]=1; adr r1,"SLAVER"; movs r0,3; bl 0x5d6c
none:   fast-GPIO 0x2009c000: FIOCLR/FIOSET bit toggles (control lines)
```

What this proves (and does not):

- **Proven:** the pairing/identity path is handled in **MCU software on cleartext data** —
  fields are parsed straight out of the received message buffer by byte offset
  (`ldrb`/`ldrh`/`str`) into a RAM state struct (`0x10003c06+…`), with **no decryption step
  anywhere** in the routine, and the radio is driven by **GPIO control-line** toggles. This
  matches the model: cleartext DUML field -> MCU state -> control, FPGA just the datastream.
- **Scope (honest):** this specific routine is the RC **master/slave *role*** (dual-remote),
  adjacent to but not identical with the "Connected Master *Id*" (aircraft binding). Same
  mechanism (cleartext field -> MCU state), but it is not literally the binding-ID handler;
  isolating that one is the remaining step.

Reproduce: `r2 -a arm -b 16 -m 0 -qq -c 'pd 85 @ 0x9bd0' c1_m1400.bin`.

## Traced (pass 2): "Encrypt" is ATSHA204 auth, and the WiMAX link params are telemetry

Two more claims now shown in `m1400` code (radare2, `-a arm -b 16 -m 0`; strings reached by
PC-relative `ADR`).

### "Encrypt" = ATSHA204 component auth / provisioning, NOT link encryption

The only `Encrypt` strings in the firmware sit in a secure-element cluster:

```
0xfac0 Factory_Info err   0xfad4 mac err   0xfadc Chip_Info err
0xfaf4 IsAreadyEncrpty:%02x...   0xfb18 Bn:%c%c%c%c%c%c%c%c%c%c  (10-char barcode serial)
0xfb74 Encrypt change!!!   0xfb88 Encrypt loss!!!
```

next to the `sha204p_send_slave_address` (ATSHA204 I2C) code at 0xf07a. The routine at
~0xf880 reads a record, checks a `'G'(0x47),3,0x11,7` header/version, logs the chip serial
(`Bn2:%c%c…`), and compares stored vs received **"IsAlreadyEncrypt" provisioning state** of
the secure element, logging `Encrypt change!!!`/`Encrypt loss!!!` on mismatch, via helpers in
the sha204 neighbourhood. So "encrypt" here = the ATSHA204 **locked/provisioned state** and
its challenge-response **MAC** ("mac err") — component authentication, not a link/payload
cipher. **Proves the Tier-1 claim in `what-is-actually-secret.md` in code**: the sole
"encryption" in the RC firmware is component auth; nothing encrypts the radio data.

### WiMAX link params are tracked and reported as telemetry

Format string at `0x25abc`:

```
ch:%d  mcs:%d  mode:%d  bw:%d  snr:%d  rssi:%d  harq:%d  err:%d %d
```

formatted by the reporter at `0x256cc` (reads the fields from a RAM link-state struct).
`mcs`, `bw`, `harq` are WiMAX/LTE-family PHY terms. => the firmware tracks the WiMAX link
parameters and emits them as **cleartext telemetry/log data**, corroborating both the
WiMAX-family modem and the "it's all cleartext data" model. (Reproduce:
`r2 -a arm -b 16 -m 0 -qq -c 'pd 60 @ 0x256b0' c1_m1400.bin`.)

### Still open

The exact DUML "Connected Master *Id*" (aircraft binding) handler is not yet isolated. The
role path (0x9bd0) and these two findings all show the same mechanism — cleartext fields in
MCU RAM, component-auth the only crypto — so the binding-ID handler is expected to be more of
the same; isolating it is the remaining step.
