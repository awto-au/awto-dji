# Link security, pairing and "keys" (P3 Lightbridge)

Does the RC↔aircraft link use encryption keys? How do they pair? Evidence from the
firmware and the DUML command set. Short answer: **binding is by identifier, not a
crypto key pair; the "scrambler" is whitening, not a cipher; no evidence of a
negotiated/rolling link key.**

## Guiding principle: nothing in this link is hidden — don't reverse what isn't secret

Neither the ID nor the whitening is a secret, so neither should be *excavated* from the
FPGA. Treat them as what they are:

- **The ID is placed into the data by a CPU, in cleartext.** Confirmed from firmware: the
  ground MCU `m1400` (LPC1765) frames the Master-ID as a **DUML message** and sends it to
  the FPGA over a **UART** (`docs/id-entry-point.md`). The FPGA only modulates the bytes it
  is handed. So the ID is read **off the wire** (UART tap / `usbmon` / DUML stream) — never
  from the FPGA netlist. "Where it enters the FPGA" is just framed bytes arriving on a
  serial port.
- **The whitening is not a security mechanism at all.** A scrambler exists for DC-balance
  and clock recovery (break up long 0/1 runs so the PLL stays locked, keep the spectrum
  flat) — every PHY publishes one. It is almost certainly the **standard WiMAX randomizer**
  (`x^15 + x^14 + 1`, seed from frame/ID per spec): you **recognise** it, you don't reverse
  it. And even if DJI used a custom polynomial, it is **unkeyed and linear**, so
  **Berlekamp-Massey recovers it from one known-plaintext capture**, mechanically. "Linear +
  no key" falls out of a single capture either way.

Consequence: **there is nothing cryptographically secret in this link.** No payload cipher
(ATSHA204 is component auth only), the ID is an address, the whitening is unkeyed. The only
"protection" is proprietary PHY + pairing-by-address — obscurity, not key secrecy. So interop
needs: re-implement a documented-family (WiMAX/LTE) PHY, read a cleartext address, solve one
unkeyed scrambler. **None of it requires the FPGA netlist, the Mistral ALM model, or
silicon** — those answer "how is the modem built", not "how do we talk to it". The FPGA
analysis (`m2001-decomp-findings.md`, `fpga-emulation-plan.md`) stands as architecture, not
as a dependency of the link goal.

### Caveat: compressed video is already near-random — entropy is not encryption

The downlink is mostly **H.264 video**, which is already high-entropy/noise-like. So a
capture that "looks random" is **not** evidence of encryption, nor even of strong whitening —
it is mostly just compressed video. The scrambler on top is a thin, standard, unkeyed layer.
Do not infer a cipher from entropy.

### Two different "IDs" — and the one that matters may be metadata, not a PHY field

- **Link-layer pairing address:** *if* the FPGA does hardware address-filtering, the ID would
  live in the PHY/MAC header so the radio drops other aircraft before decode.
- **Device / Master-ID as application metadata:** carried as cleartext **DUML** muxed with
  the video/OSD/telemetry, checked in **software**.

Current firmware evidence leans toward the **software/metadata** model: the MCU (`m1400`)
owns the Master-ID, frames it as DUML, and moves it over a UART — no sign of a hardware MAC
filter in the FPGA. If pairing is enforced by the **CPU checking the ID in the decoded
frame** (demod the paired channel, drop mismatches in software), then the FPGA does **no
addressing** at all — it only modulates/demodulates — and the ID is **just metadata in the
stream**. Not yet proven which model holds; one capture settles it: the Master-ID almost
certainly appears in the **cleartext DUML/OSD metadata** alongside the video (where SN and
telemetry already live). Either way: read it as metadata off the wire, nothing in the FPGA to
reverse.

## Two different "protocols" — only one is secret

- **DUML** — the command/telemetry/app protocol. **Publicly documented / reverse-
  engineered** (framing, CRC, cmd-sets; this repo implements it in Dart).
- **Lightbridge PHY** — the OFDM radio waveform plus the FPGA scrambler. **Not publicly
  documented at bit level.** But undocumented ≠ encrypted (below).

## Scrambler ≠ cipher

The FPGA's "scrambler" (seen in the OFDM receiver board docs) is, by the normal meaning
in a radio, a **data whitener**: a fixed-polynomial LFSR that removes long runs / DC bias
so the OFDM spectrum is well-behaved. It has **no secret key** — descrambling needs only
the (fixed) polynomial, which is baked into the bitstream. So the RF link being
undecoded is a matter of obscurity + effort, not strong cryptography.

## Pairing is by Master ID, not keys

The DUML RC command set (`cmd_set` radio) shows the real binding mechanism:

| Command | Meaning |
|---|---|
| `RC Connected Master Id Set/Get` | the RC stores the **ID of the aircraft** it is bound to |
| `RC Available Master Id Get` | discover aircraft that can be joined |
| `RC Request Join By Slave`, `RC List Request Join Slave` | the join/bind handshake |
| `RC Pairing` (= "Frequency Set") | linking also selects the channel |

So "linking" associates RC↔aircraft by **identifier + frequency** — not by exchanging or
rotating a secret key. (`RC Push Rmc Key Info` and `RC Self Defined Key Func` refer to the
physical RC **buttons**, not crypto keys.)

## How do they "pair" then, without keys?

Pairing is real, but it is **association by identity, not cryptographic pairing** — think
Wi-Fi/Bluetooth addressing minus the encryption layer:

1. Every aircraft and RC has a unique **ID** ("Master ID" — effectively a serial/address).
2. **Linking** (the physical link button, done with the two close together) is
   **trust-on-first-use by proximity**: a short local exchange where each records the
   other's ID — `RC Request Join By Slave`, `RC List Request Join Slave`,
   `RC Connected Master Id Set`.
3. Afterwards RF frames **carry that ID**, and each side **filters by it**: the aircraft
   obeys only frames from its bound RC, the RC shows only its aircraft. They also agree a
   **channel** (`RC Pairing` = "Frequency Set") and hop within 2.4 GHz.
4. The OFDM + Gold-sequence scrambler only makes frames *well-formed Lightbridge frames*
   (vs random noise), not *authenticated* ones.

So the binding stops accidental cross-control (IDs differ) and casual interference, but
with **no key there is no authentication** — the association is spoofable, which is the
property the hijacking literature (Behind The Wings, Enhanced-Wi-Fi) exploited. Pairing ≠
security here.

## Sample data / public captures

No Lightbridge-video-specific labelled dataset was found. Available instead:
- **Zenodo 4264467** — real IQ of 10 drones incl. DJI at 2.44 GHz / 5.8 GHz, raw
  interleaved 16-bit `.bin` (120/200 MHz sampling). The most useful real capture.
- **DroneID tooling** — `proto17/dji_droneid`, `anarkiwi/samples2djidroneid`,
  `droneid-native` decode the *beacon* (not video); proto17 withholds its IQ (GPS privacy).
- **Synthetic/other** — a Mendeley Phantom 4 Pro 2.4 GHz set (generated), an IEEE-DataPort
  RC-RF-signal set.

For the actual P3 Lightbridge waveform, capturing your own with the SDR is the realistic
source.

## Firmware crypto search — nothing for the link

Searched `m0900` (radio MCU), `m0100`/`m0101` (camera) for
`aes|cipher|encrypt|scrambl|key|session|nonce|handshake`:

- `m0900` radio MCU: nothing (stripped bare-metal).
- `m0100` camera: the only AES/key hits are **Wi-Fi/Bluetooth/TLS** — `wpa_supplicant`
  `CCMP`/`TKIP`, `hostapd`, OpenSSL certs. Those are the camera's Wi-Fi/app/cloud crypto,
  **not** the Lightbridge RF link.

No positive evidence of a keyed cipher or key exchange on the Lightbridge link.

## Assessment

Protection against another party controlling the aircraft is **ID binding + the
proprietary (unkeyed) waveform + whitening**, not cryptographic authentication. This is
consistent with public research of the era (e.g. "Behind The Wings", DJI Enhanced-Wi-Fi
hijacking) showing DJI links of that generation were not strongly authenticated.

Caveat: a stripped MCU or the FPGA fabric could hide logic the string search can't see,
so this is "no positive evidence of link crypto", not a proof of its absence. But the
binding commands are plainly identifier-based.

## Documentation status: how approachable is the waveform?

Updated after a deeper search — the barrier is obscurity + effort over a standards-based
PHY, not cryptography:

- **DroneID (OcuSync-era beacon) is fully reverse-engineered** — NDSS 2023 (peer-reviewed):
  601 subcarriers, 15 kHz spacing, Zadoff-Chu sync (roots 600/147), Schmidl-Cox timing,
  QPSK, a **3GPP Gold-sequence scrambler**, LTE turbo code — with working decoders
  (`proto17/dji_droneid`, `gr-droneid`, a native-C real-time one). This confirms DJI's
  "scrambler" is a **standard Gold sequence, not a keyed cipher**.
- **OcuSync video (O3/O4)** is being actively RE'd (2024-25); community repos document
  LTE-like PHY params (subcarrier spacing, CP lengths, Zadoff-Chu, QPSK/QAM). Provisional
  but clearly LTE-derived.
- **Lightbridge-2 (the P3) video:** no public end-to-end decoder or frame spec found; the
  academic Lightbridge work is signal *detection/parameter estimation* (gr-inspector), not
  decode-to-pixels.

**DJI's own firmware confirms the LTE/WiMAX family.** The Lightbridge 2 ground MCU
(`m1400`, LPC1765; from the C1/LB2 firmware) carries a link-telemetry format string:

```
ch:%d  mcs:%d  mode:%d  bw:%d  snr:%d  rssi:%d  harq:%d  err:%d
```

- `mcs` = **Modulation and Coding Scheme** (adaptive BPSK->64QAM + code rate — an LTE/WiMAX
  concept), `bw` = selectable channel bandwidth, `snr`/`rssi` = standard metrics, and
- `harq` = **Hybrid ARQ**, a 3GPP LTE/WiMAX retransmission scheme — a direct giveaway that
  the link is LTE/WiMAX-family, not a bespoke waveform.

Also in `m1400`: `MASTER`/`SLAVER`/`TestMaster`/`TestSlaver` (confirms the master/slave ID
pairing), and `sha204p_send_slave_address` — an **ATSHA204 crypto-auth chip**. That is
SHA-256 challenge-response for **component authentication (anti-counterfeit)**, not link
encryption; it is the one real cryptographic element, and it authenticates *genuine
hardware*, not the RF payload. (LB2 is also dual-band — a `5.8G VER ERR!` string — unlike
the P3's 2.4 GHz-only Lightbridge.)

**And Lightbridge is "based on WiMAX" (IEEE 802.16 OFDM)** per the receiver-board docs — a
*published standard*. So reaching symbol demod is approachable (blind OFDM param estimation
+ standard WiMAX/LTE sync; the DroneID pipeline is a ready template). The remaining work is
DJI-specific and *findable* rather than secret: the exact scrambler seed/polynomial, framing
tweaks, and H.264 depacketization. Still genuinely unproven to a picture — "approachable PHY"
is not "weekend project to live video" — but there is no cryptographic wall, only effort and
the DJI-specific framing.

## Is Lightbridge really different from the understood streams?

Working assumption: **no — treat it as an understood-family stream with unknown
parameters, not a new waveform.** DJI reuses PHY IP across products, so the right prior
is strong:

- **Same primitives.** DroneID/OcuSync decode to LTE-style OFDM (CP, pilots, Zadoff-Chu
  sync, Gold-sequence scrambler, turbo/convolutional FEC, QPSK/QAM). Lightbridge is
  "based on WiMAX" (802.16 OFDM) per the receiver board — WiMAX and LTE are siblings. The
  understood-stream toolkit (blind OFDM estimation, Schmidl-Cox, the `dji_droneid`
  pipeline) applies directly.
- **Differences are parameters, not principle:**
  - *Lineage:* WiMAX (Lightbridge) vs LTE (DroneID/OcuSync) — siblings; preamble/pilot/
    framing details differ, so adapt the decoder, don't run it unchanged.
  - *Scale:* DroneID is a tiny fixed beacon (9 symbols, ~10 MHz, 601 subcarriers);
    Lightbridge is a continuous video link — wider, 2T2R MIMO, adaptive BPSK→64QAM, with a
    MAC to multiplex H.264 + control.
  - *Undocumented specifics to recover:* FFT size/CP/subcarrier spacing, ZC roots,
    scrambler seed/polynomial, FEC rate, video/control framing — recovered, not invented.

So model it as "WiMAX-family OFDM with DJI framing"; the task reduces to parameter
estimation + adapting a known pipeline, with the WiMAX-vs-LTE deltas and the extra
video-link framing as the real (but bounded) unknowns.

### Did DJI say anything? (FCC is the only disclosure)

DJI's one authoritative public statement is the **FCC filing**. The P3 aircraft
(`SS3-WM3231503`/`-507`/`-510`) is authorised as a **Digital Transmission System (DTS),
2406.5-2476.5 MHz, Part 15C**. "DTS" is the FCC class for **wideband digitally-modulated
(OFDM-class)** systems, not frequency hopping — i.e. DJI officially declared it as the
same kind of wideband OFDM signal the decoded streams are. The exact emission designator
and occupied bandwidth are in the test-report PDF (BACL `RDG150107002-00A`, viewable on
fccid.io); its OB is the figure to compare against DroneID's ~10 MHz channel. No DJI
patent or white paper describing the Lightbridge modulation/coding was found.

**Conclusion:** there is no DJI statement, and no evidence, that Lightbridge differs in
kind from the decoded OFDM streams; the FCC classification agrees with "wideband OFDM,
2.4 GHz." What's missing is only a published bit-level spec — absence of documentation,
not evidence of difference. Correct default: assume it is the understood stream until a
capture shows a specific parameter differs.

## Probing it (how to confirm dynamically)

An Android **emulator can run DJI GO but cannot reach the RC** (no USB-accessory
passthrough), so it won't see live link data — the weakest tap. Better, in order:

1. **USB (`usbmon`)** — capture the RC↔phone AOA stream: DUML + video directly.
2. **RC service pads** — UART `256000 8N1` DUML, or SWD on the STM32s (probe the
   MCU↔FPGA interface to observe the scrambler setup / fixed seed).
3. **SDR** — characterise the RF waveform/OFDM params (cannot decode the payload).
4. **Frida on a rooted phone** — hook the SDK to watch DUML in the app (but link keys are
   not there, because there are none).

The scrambler polynomial/seed, if wanted, is best recovered by probing the MCU↔FPGA
config at bring-up or from the bitstream — not from the app layer.
