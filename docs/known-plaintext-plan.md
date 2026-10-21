# Recovering the link: ID + framing + scrambler (no cipher to break)

Because the Lightbridge link has **no payload encryption** (only an unkeyed whitening
scrambler and ID-based pairing — see `link-security.md`), the whole link can be recovered
with a **known-plaintext** approach instead of cryptanalysis. Two independent tasks:

## 1. Recover the ID (DUML layer — no radio needed)

The Master-ID that pairs RC <-> aircraft rides the **DUML** `RC Connected Master Id
Set/Get` commands. So its value and byte-length are **directly readable from a capture**:

- Capture the RC<->phone AOA USB stream (`usbmon`) or tap the RC UART (`256000 8N1`).
- Read the `RC Connected Master Id` command payload -> the ID bytes and their count.
- The ID is a device address (a few bytes), not a crypto key — consistent with "no
  encryption, just recover the ID".

Its **position in the RF frame** is then wherever those same bytes sit constant in the
header across frames to one aircraft (the controlled capture below makes them obvious).

## 2. Recover framing + scrambler (known-plaintext)

The camera firmware (`m0100`) has a built-in test-pattern generator, including an
**"all black test pattern"** (strings: `1: horizontal`, `2: vertical`, `3: all black test
pattern`). Forcing it feeds a **known, static, low-entropy** input to the H.264 encoder.

- **Nuance:** H.264 of all-black is not literally constant bytes (SPS/PPS + slice headers,
  skipped-macroblock coding), but it is **extremely repetitive frame-to-frame and
  low-entropy**. That repetition is the lever: identical payloads at the frame period
  expose the **scrambler sequence/period**, and XORing two identical-payload captures
  cancels the payload and leaves the scrambler differences.
- From the recovered sequence, solve the **whitening LFSR polynomial + seed** (it is
  unkeyed, so this fully breaks the "scrambling"). Capture black and white patterns for
  two reference payloads.

## Where to capture — digital tap on a DJI device beats SDR

The strongest method is the **digital boundary on the board**, with a logic analyzer:

- Tap **DM368 -> FPGA input** = the H.264 plaintext (known, via the test pattern), and
  **FPGA -> AD9363 output** (or the AD9363 data bus) = the scrambled/framed version.
  Plaintext + ciphertext pairs at the digital level solve the **framing and scrambler
  deterministically**, with no demodulation ambiguity.
- Or use a **second DJI device as the receiver** and tap its **FX2LP output** (recovered
  H.264) against the known camera input — confirms payload + framing end to end, no RF.
- **SDR is the fallback / over-air cross-check** once the framed bytes are known: it maps
  the recovered frame onto the actual OFDM waveform (WiMAX/LTE family — `mcs`/`harq`
  confirmed in the LB2 MCU strings).

## Net

No cipher stands in the way. The recovery reduces to:

1. **DUML capture -> ID** (size + position).
2. **All-black test pattern + digital tap on a DJI board -> frame structure + unkeyed
   scrambler seed.**
3. **SDR -> map the known frame onto the OFDM waveform** (optional cross-check).

Tap points are the documented board service pads (SWD, UART `256000 8N1`, SPI, the FX2LP
slave-FIFO lines, the AD9363 data port); the camera test pattern is set from the Linux
side on `m0100`.
