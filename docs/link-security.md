# Link security, pairing and "keys" (P3 Lightbridge)

Does the RC↔aircraft link use encryption keys? How do they pair? Evidence from the
firmware and the DUML command set. Short answer: **binding is by identifier, not a
crypto key pair; the "scrambler" is whitening, not a cipher; no evidence of a
negotiated/rolling link key.**

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
