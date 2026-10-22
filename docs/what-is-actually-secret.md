# What is actually secret vs just undocumented (P3 Lightbridge)

Synthesis of the link analysis. "Hidden" is three different things; only a narrow slice is
real cryptography, and none of it gates reading the ID, reading telemetry, or app-to-bird
control.

> **LAYER CAVEAT (important).** Everything "cleartext/no-crypto" below is **proven only at
> the MCU / DUML layer** — i.e. at the USB/UART, where DJI's own hardware has already
> demodulated the radio. It is **not proof that the data is unencrypted over the air.** The
> MCU hands cleartext bytes to the FPGA; the FPGA *could* encrypt or keyed-scramble them
> before modulation and the MCU code would look identical. Supporting (not conclusive)
> evidence: no AES/TEA cipher tables or crypto routines exist in either MCU (`m1400`,
> `m0900`); the only `Encrypt*` strings are ATSHA204 component auth. But a cipher in the
> **FPGA** cannot be ruled out from firmware, because the FPGA datapath is unreadable
> (decode gaps). **The over-the-air claim (incl. "unkeyed whitening") is inference from the
> WiMAX basis, NOT proof.** Only an over-the-air SDR capture (or reading the FPGA datapath)
> settles it. Treat Tier-3 "whitening unkeyed" accordingly.

## Tier 1 — genuinely secret (real cryptography)

| Thing | What it protects | Does it gate interop? |
|---|---|---|
| **ATSHA204 keys** | **component authentication** (battery/part is genuine) — *now confirmed in `m1400` code: the only `Encrypt`/`mac` strings are ATSHA204 provisioning state, see `cpu-reversing-proof.md`* | **No** — does not encrypt the link or telemetry |
| **Firmware signing keys** | image authenticity on signed products | **No on P3** — P3 `xV4` images are unsigned (CRC+MD5); only newer IMaH products are signed |
| **DUML `encrypt_type` != 0** | a few sensitive commands (activation, parts of binding) | **No** — telemetry, OSD and the Master-ID are `encrypt_type 0` (cleartext) |

So there *are* genuine secrets in the system — but they authenticate parts / sign firmware /
protect a handful of sensitive commands. They do not protect the data path.

## Tier 2 — "hidden" only as obscurity (undocumented, not secret; effort, not keys)

- OFDM PHY bit-level framing — proprietary, but WiMAX/LTE-family, re-implementable from spec.
- FPGA bitstream -> gates — needs the open Cyclone-V model (Mistral + ALM model), not a key.
- Some DUML field offsets; which UART is the FPGA link (needs the board schematic).
- The ID's exact **byte position** in the frame — "hidden in plain sight," found by capture
  + the scanner's static-payload / ASCII heuristics.

## Tier 3 — not hidden at all (open / standard / cleartext)

- DUML protocol (documented / dissected).
- Telemetry: GPS, height, velocity, attitude, battery — cleartext DUML data.
- **Master-ID** — a cleartext address in the DUML stream.
- Whitening/scrambler — unkeyed, almost certainly the standard WiMAX PRBS; recoverable.
- AD9363 register map — public (ADI UG-570).
- P3 MCU firmware — unsigned, disassemblable.

## Bottom line

The only genuine secrets are the ATSHA204 auth key, the signing keys (N/A on P3), and a few
DUML-encrypted sensitive commands — **none of which gate the things on the roadmap.** Reading
the ID, reading telemetry, and driving the bird over the normal (already-authenticated) link
all run on cleartext channels. The ID is "hidden" only in the trivial sense of being
unlabeled bytes to spot in the stream. Everything else called "hidden" earlier is obscurity
(effort), not secrecy (keys) — see `link-security.md`, `minimal-recovery.md`,
`m2001-decomp-findings.md`.
