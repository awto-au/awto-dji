# Lightbridge RF, SDR testing, and PCB/repair

Answers to: is Lightbridge documented, can a 2.4 GHz SDR test it, and what PCB info
exists for repair. Sourced from the dji-firmware-tools wiki
([P3X OFDM Receiver board](https://github.com/o-gs/dji-firmware-tools/wiki/P3X-OFDM-Receiver-board))
and community RE. Receive/analysis only — see the legal note.

## Is Lightbridge documented?

No official spec from DJI. But the **hardware is well documented** by the community, and
the waveform is partly understood:

- Lightbridge is **"based on WiMAX (802.16-style OFDM) with custom DJI scrambling."**
  2T2R MIMO, adaptive **BPSK / QPSK / 16QAM / 64QAM** (this is the adaptive bitrate that
  degrades the picture as the link weakens).
- The **scrambling/whitening is done in the FPGA** (Altera Cyclone V `5CEFA4U19I7`), later
  an Artosyn `AR8001` ASIC. **The scramble algorithm and frame/bit format are NOT
  published** — so there is no open way to decode the actual video.
- What *is* documented: the full RF chain and board (below), and the general OFDM nature.
  The exact channel plan and bandwidth are not published.

## The RF chain (this is what makes SDR testing viable)

The Lightbridge radio is literally built on an SDR-class transceiver:

| Part | Role |
|---|---|
| **Analog Devices AD9363** | agile 2×2 RF transceiver, 12-bit ADC/DAC — **the same AD936x family used in the PlutoSDR and USRP B200/B210** |
| Artosyn AR8003 | later replacement for the AD9363 (noisier) |
| Avago MGA-22003 ×2 | 2.3–2.7 GHz PA |
| TriQuint TQP3M9037 ×2 | ultra-low-noise LNA |
| Skyworks SKY13320 ×4 | RF switches (A/B antenna paths) |
| Altera Cyclone V FPGA / Artosyn AR8001 | OFDM baseband + DJI scrambler |
| Cypress CY7C68013A (FX2LP) | USB to the phone (H.264 video) |
| STM32F103CBU6 (Cortex-M3, 72 MHz, 128 KB) | the `m0900` Lightbridge MCU; configures the transceiver over SPI |

## Can you test it with a 2.4 GHz SDR?

**Yes — for receive and characterisation.** You cannot decode the video, but you can do a
lot, and it's a great way to diagnose the broken unit.

**You can:**
- See the downlink on a waterfall: power the P3, tune ~2.400–2.483 GHz, and the strong
  wideband OFDM burst is unmistakable. This alone is a **functional test** — proves the
  aircraft (or RC) is transmitting, which is a direct diagnostic for a dead unit.
- Measure channel centre and bandwidth, burst/frame timing, and the 2T2R MIMO.
- Blind-estimate the OFDM parameters (FFT size, cyclic-prefix length, subcarrier spacing,
  pilot pattern) from an IQ capture.
- Watch the adaptive modulation change with range/attenuation.

**You cannot (publicly):**
- Demodulate/decode the video or control payload — the DJI scrambler and frame format
  aren't published, and no open demod exists.

**SDR bandwidth matters:**
- The channel is a wide WiMAX-style OFDM carrier (~10–20 MHz). An **RTL-SDR (~2.4 MHz) is
  too narrow** to capture a whole channel — you'll only see a slice or the spectrum.
- Use a **wideband** SDR: **HackRF One** (20 MHz), **PlutoSDR** (20 MHz — and literally
  the AD936x, the same chip Lightbridge uses), **USRP B200/B210**, **LimeSDR**, or
  **bladeRF**. Tools: GNU Radio, SDR++, inspectrum, Universal Radio Hacker (URH).

## Legal note (important)

2.4 GHz is an ISM band, so **receiving is fine**. **Never transmit** on it with the SDR
near the aircraft — you would jam the control link and could cause a flyaway or crash,
and unlicensed TX is illegal (in Australia, ACMA rules). This doc is for RX/analysis of
your own equipment only.

## PCB / repair info

The firmware-tools wiki is the best board-level reference. For the RC's OFDM receiver
board it documents the chips above **plus service pads**, which is exactly what repair
needs:

- **Debug:** SWD (SWCLK/SWDIO) and, on rev P01007.06, full JTAG — so the STM32 MCUs can
  be probed/reflashed.
- **UART:** TX/RX at **256000 8N1** to the flight controller (DUML — useful for probing).
- **SPI** (MOSI/MISO/SCK/NSS), **CAN** (CANL/CANH), **USB** (DP/DM), FX2LP control lines,
  and labelled power rails (3V3, 5V/6V, 2V5, 1V1/1V2/1V3/1V7/1V8).
- **Connectors:** `CAMERA` (6-pin ribbon: USB video + CAN/DUML) and `CENTER` (6-pin: UART
  DUML + power).
- **Board revisions:** `P01007.06` (AD9363 + Cyclone V FPGA) vs `P01007.14` (Artosyn
  AR8003 + AR8001 ASIC) — the wiki notes the Artosyn version can be noticeably noisier.

Other repair resources: the dji-firmware-tools wiki (sister pages for the camera, FC and
other boards), the PhantomPilots forum, OpenBoardView/Badcaps for any shared boardview,
and specialist drone-repair shops.

### Is the FPGA bitstream in the firmware? Yes.

Confirmed by unpacking the firmware: module **`m1900`** is the **air Lightbridge FPGA
configuration image** — "lightbridge FPGA on air model 0", version `01.00.2144`,
`encrypt_type=0` (plaintext), exactly **4 MiB**, 0xFF-padded (an FPGA config-flash image,
not CPU code). The **ground/RC FPGA** bitstream ships likewise in the remote's firmware.

How it's used: a firmware update writes this bitstream into the board's **serial NOR
flash** (`N25Q064` / the `ATH` chip on the receiver board), and the FPGA loads it from
there at every power-on. So the FPGA "program" is firmware — reflashable, not fused.

**Why that matters for "it just stopped one day with a system error":** there are two
broad causes, and they point opposite ways:

1. **Software/firmware corruption** — e.g. an interrupted update, or a module left in its
   bootloader, or a bad bitstream load. This presents as a sudden "system error" / lost
   link even though nothing was physically damaged. **This is the reflashable case:**
   forcing a full firmware re-write (SD-card method, or DJI Assistant 2) rewrites the
   FPGA bitstream and every module and can bring it back. Cheap to try first.
2. **Hardware failure** — cold/cracked solder (thermal cycling), a failed PA/LNA/regulator,
   or a dead FX2LP/FPGA. A bitstream doesn't "rot" on its own, so a unit that was fine
   and died with no update is often this. Reflashing won't fix it; it needs board work.

Try the reflash first (non-destructive, rules out case 1). If it still errors, it's
hardware — use the SDR + service pads below to localise it.

### Diagnosing the broken unit
The SDR + the service pads together make a good diagnostic kit:
- If the aircraft is dead: does it emit the 2.4 GHz downlink at all (SDR)? Does the FC
  UART (256000 8N1) produce DUML/boot chatter? Is a module stuck in its bootloader (a
  failed firmware flash — see `firmware-overview.md`)?
- If the RC is dead: same RF check for its uplink, and SWD/UART probing of its STM32.

(To go further, say which unit is broken — aircraft or RC — and the symptoms, and which
SDR model you have, so the bandwidth/approach can be matched.)
