# Minimal recovery: eliminate the complex FPGA, reverse only the small DJI-specific parts

Strategy that collapses the whole effort. The protocol family is established (WiMAX/LTE
OFDM, confirmed by `mcs`/`harq` in firmware, FCC DTS classification, and the `m2001`
netlist). So the standard modem is **re-implemented from spec, not reversed** — and the
only DJI-specific unknowns are **small and outside the DSP datapath**.

## What is complex vs small

| Part | Where | Handle it by |
|---|---|---|
| FFT / filters / FEC / equaliser (64 DSPs + M10K) | FPGA datapath | **Re-implement from the WiMAX/LTE spec — do NOT reverse** |
| OFDM framing / sync / pilots / CP | FPGA | Standard; re-implement with parameters from AD9363 config / blind estimation |
| **ID / addressing ("the key")** | **MCU (MAC layer)** | Reverse the small frame-build/parse code; read value from DUML capture |
| **Whitening / scrambler** | FPGA, but a tiny LFSR | Berlekamp-Massey on an all-0s capture, or extract the small LFSR from the netlist |

The one hard blocker — the DSP/M10K internal config — holds exactly the parts we
**re-implement**, so it is eliminated from the critical path.

## The two small things to recover

### 1. The ID (an address, not a cipher key)

The Master-ID is a MAC-layer field the **MCU** inserts into the frame header and filters
on receive. So:

- **Value + length:** read directly from a DUML capture (`RC Connected Master Id
  Set/Get`) over USB (`usbmon`) or the RC UART (`256000 8N1`). No radio needed.
- **Frame position / handling:** reverse the small frame-build/parse routine in `m0900`
  (air) / `m1400` (ground) — ordinary MCU code, not the modem. Trace from the DUML/UART
  parser to where the header (preamble + ID + seq + length) is assembled before the FPGA
  hand-off.

### 2. The whitening (unkeyed LFSR)

A scrambler is a handful of flip-flops + XORs, independent of the FFT/DSP datapath.
Recover it without decoding the complex FPGA:

- **Known-plaintext (easiest):** force the camera **all-black test pattern** / patch the
  payload to **all-0s** (the radio chain is content-agnostic, see
  `known-plaintext-plan.md`). The transmitted (de-framed) bytes then equal the LFSR
  output. Run **Berlekamp-Massey** on that bit sequence -> it returns the LFSR
  **polynomial + seed** directly. Done in a few lines; no FPGA reversing.
- **Netlist extraction (alternative):** locate the small LFSR structure in the `m2001`
  Mistral netlist and ignore the 64 DSPs / M10Ks entirely.

## Result

Full link interop reduces to: **reverse the small MCU ID/frame code + solve one LFSR by
Berlekamp-Massey**, with the OFDM/FEC taken as standard WiMAX re-implemented from spec.
This is tractable without decoding the modem datapath, without Quartus, and without the
hardware-only DSP/M10K recovery. The remaining inputs are a **DUML capture** (ID) and one
**all-0s RF/digital capture** (whitening) — both small, both already planned.
