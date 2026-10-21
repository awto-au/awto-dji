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

## Patching the payload: the radio chain is content-agnostic

The FPGA modem, AD9363 and FX2LP **transport bytes/frames; they do not parse or validate
H.264**. Patching the payload (closest to the FPGA, e.g. in the camera Linux `m0100`,
which is unsigned/reflashable) to a **constant (all-0s / all-1s)** transmits fine — only
the phone-side `libdjivideo` decoder wants valid H.264, and it merely shows garbage. The
link doesn't reject it.

**A constant is the *optimal* scrambler-recovery input.** A whitening scrambler exists to
turn constant/low-entropy input into flat output, so feeding **all-0s** makes the
scrambled bytes equal `scrambler_sequence XOR 0` = the raw LFSR sequence — read the PRBS
directly off the wire (all-1s gives the inverted sequence). Better than the all-black test
image, which is still structured H.264.

Practical: overwrite the **payload bytes** (not the encoder control flow) so rate-control
keeps running and no watchdog trips; keep framing/length headers valid (constant as the
payload inside normal frames); the adaptive MCS/rate tracks RF link quality, not content,
so constant data just fills frames.

## Recovering the *logic* from the netlist (assisted RE tools)

Mistral yields the fabric netlist; dedicated tools then recover higher-level structure:

- **HAL** (`emsec/hal`) — open-source gate-level netlist RE framework (graph model,
  Python/C++ API, plugins).
- **DANA** (HAL plugin) — recovers high-level **registers/words** from flip-flop dataflow.
- **Module identification** (HAL) — finds **adders, multipliers, counters**, recovers bit
  order within registers.
- **RELIC** (UT Austin) — classifies registers as **control vs data**.
- Reference: *"Stealing Maggie's Secrets — IP Theft Through FPGA Reverse Engineering"*
  (2023) documents the bitstream->intent pipeline.

Scope: these do **assisted, partial** recovery (register banks, arithmetic blocks, FSM-ish
structure) toward human-reconstructed intent — not clean source. They need the LUT
contents (Mistral decodes LAB/LUT; DSP/M10K internals remain the gap). The chain
**Mistral -> HAL/DANA/module-id -> human** is real.

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
