# Intel WiMAX i6050 firmware patch feasibility - 26 October 2026

Evidence from GitHub Actions run [40202327160](https://github.com/awto-au/awto-dji/actions/runs/40202327160) and Intel's GPL Linux driver `v5.10/drivers/net/wimax/i2400m/fw.c`.

## Verified observations
- The actual `i6050-fw-usb-1.5.sbcf` image is **1,531,932 bytes**; SHA256 `bd38e7dc36deebd0ba3601ea8c5dc70dcd11a99b940137811e99387d5f249296`.
- Whole-image entropy is **6.26705** bits/byte. Multiple low-entropy data regions, literal pools and readable strings; the image is not uniformly encrypted. This does not establish that every segment is uncompressed plaintext code.
- ARM **Thumb** instruction sequence decoded from file offset `0x11f624` (target memory address `0xea5db0`), immediately before frequency constants. Using a `thumbv7m-none-eabi` LLVM assembler/disassembler on these bytes gives:
  ```asm
  ldr r1, [pc,#0x78]
  cmp r0,r1
  bhi ...
  movs r4,#0x0f
  b ...
  ```
  The surrounding code includes further `cmp`/`bhi` pairs, `movs r4,#0x10`/`#0x11`, and returns with `pop {r4,r5,r6,pc}`. **ARM Thumb is strongly supported** for this loaded region, but the whole-chip architecture and CPU have not been fully mapped.
- At file offset `0x11f654` / loaded memory address `0xea5de0`, there is a contiguous sequence of 32-bit little-endian kHz frequency constants. Examples: **2300000, 2350000, 2400000, 2450000, 2496000, 2550000, 2600000, 2650000, 2700000**, followed by 3 GHz values. This resembles frequency bin/range classification. It **does not** prove that 2450 MHz is a permitted operating channel, nor that changing the table is sufficient.
- The SBCF has `SIGNED_JUMP` as its terminal loader command, with 256-byte key and modulus lengths and a 4-byte exponent. Linux driver handles signed and unsigned boot depending on modem boot state, and sends the signature during signed finalisation (`i2400m_dnload_finalize`). **On a device enforcing signed boot, even a one-byte change would invalidate the vendor signature.** Whether a particular i6050 card enforces it has not yet been measured.
- Intel's Linux host `i2400m_msg_to_dev` and userland `wmx_SetChannelPlan` do not show an explicit exclusion of 2400-2496 MHz; internal modem/hardware acceptance has not been verified.

## Engineering assessment
There are four independent hurdles:
1. Host can request frequency (plausible).
2. Embedded firmware's tuning policy and calibration (not confirmed).
3. Analog RF front end acceptance / synthesiser / filters (not confirmed).
4. Signed boot enforcement on target card (potential hard obstacle to flash edits).

Additionally, even tuning to 2450 MHz does not prove that DJI Lightbridge waveform, FEC, framing and scrambling are sufficiently standard WiMAX to be demodulated by Intel's modem.

## Next targeted analysis
1. Map callers/xrefs to Thumb frequency classification function at `0xea5db0` and determine its return enum values, especially if input `2450000` is sent to a synthesiser or rejected.
2. Identify the boot ROM signed/unsigned mode of the specific 6250 card.
3. Capture read-only modem response to a configured `2450000` kHz scan in a shielded receive-only setup, and assess diagnostic status/error report.
4. If there is a boot signature restriction, prioritise parameter/configuration or RAM-side diagnostics rather than proposing signed image edits.
5. Check whether FPGA RF signal matches 802.16e preamble and FEC before spending effort on firmware adaptation.
