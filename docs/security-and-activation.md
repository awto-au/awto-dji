# P3 security, authentication, activation & integrity — what gates what

Consolidated reference for the distinct mechanisms that decide whether the aircraft runs, who may
talk to it, and whether firmware is accepted — kept apart because they are easy to conflate. Tags:
**V** verified in firmware, **I** inferred, **U** unknown / needs more RE. Companions:
`link-security.md` (RF link), `duml-protection.md` (DUML), `fc-bootloader.md` (loader/upgrade),
`atsha204-repair-note.md` (failed-chip repair).

## Summary

| Mechanism | Where enforced | What it gates | HW block or DJI-software? | Status |
|---|---|---|---|---|
| **DJI product activation** | FC app `m0306` | **motor start** (`Product not activation,stop motor!`) | **Hardware behaviour** (firmware won't spin motors), driven by DJI online/app activation | V (gate); the activation exchange itself I |
| **ATSHA204 component auth** | A9 camera `m0100` (primary), RC `m1400` | demonstrated: **client/app authorization** (`cam_server` rejects un-authorized MAC). Flight/boot block **not shown** | On-device check, but visible teeth are **DJI-software/client-facing** | V (check exists + what it compares); mismatch consequence **U** |
| **Device identity (UID/SN)** | `m0306`, `m0900`, `m0100` | nothing by itself — used to *build* an identity/serial | neither; it's an identifier, not a gate | V (reads); consumers partly U |
| **Authorized-MAC list** | A9 `cam_server` (`DjiMsgAuthorizedMac`) | which clients may connect to the camera server | DJI-software/client-facing | V |
| **Firmware integrity** | loader + xV4 container | whether a firmware image is accepted | on-device; **no signature** → patchable | V |
| **RF link "security"** | FPGA/radio | none (unkeyed waveform + whitening; no link encryption) | neither (spoofable association) | V (absence), OTA-encryption not ruled out |

## 1. DJI product activation — the real hardware gate

- **V** The FC app (`m0306`) refuses motor start when not activated: string `Product not activation,
  stop motor!`, alongside `is_prod_activated` (0x08047c2c), `check_activation_authority` (0x08047d5e),
  `dji_sdk_set_key` (0x0805a964). The SDK/API key is **supplied externally** (DJI app/server), not
  derived on-device.
- So "won't fly without DJI software" is **this** mechanism — a firmware motor gate keyed on DJI's
  online/app activation. It is **separate** from the ATSHA204 and from firmware signing (there is
  none). `enable_api` defaults off (`fc-io-inventory.md`); activation is one of many motor-start
  gates (most others are safety: battery, tilt, calibration).

## 2. ATSHA204 component authentication — anti-counterfeit, mostly software-facing

- **V** It is on **more than one board**: primary on the **camera/A9 (`m0100`)** — `DjiEncryptInit`
  (0x0e871e94), `DjiEncryptCheckA9Mac` (0x0e871ae0), `DjiEncryptCheckSN` (0x0e8731cc), provisioning
  `DjiEncryptSaveBothToSha204AndA9` (0x0e872740) / `DjiEncryptWriteAllBoardNumToOTP` (0x0e871140) —
  comparing the chip's 9-byte SN + board number against a copy in the **A9 NAND**; and on the **RC
  (`m1400`)** — `get_mac`, `sha204p_send_slave_address`. The P3 FC (`m0306`) has **no** ATSHA204 code.
- It is DJI's **one real cryptographic element** (SHA-256 challenge/response), for **component
  anti-counterfeit**, not link encryption (`link-security.md`).
- **V** The only enforcement RE shows from it is client authorization: `DjiMsgAuthorizedMac`
  (0x0e85f370) — `cam_server` rejects clients whose MAC is not authorized. **U** whether a
  failed/absent chip (or a lost NAND copy) halts boot/flight — the mismatch consequence in
  `CheckA9Mac`/`CheckSN` is not yet decompiled. Repair implications: `atsha204-repair-note.md`.

## 3. Device identity (UID / serial)

- **V** `m0306` reads the STM32F4 96-bit UID (`uid96_read` 0x0808527a) and folds word 0 into a
  10-byte identity record (`id10_build` 0x080596ea). `m0900` exposes its STM32F103 UID over DUML
  (`0x0904`→`0x0954`). `m0100` uses the ATSHA204 SN + board number (not an SoC/FPGA UID).
- These are **identifiers, not secrets** — used for serial/identity reporting, not as a key. No OTP,
  option-byte, or ST-ROM secret read by the FC app.

## 4. Firmware integrity — no signature

- **V** FC images are protected by xV4 **AES-128** (public module key) + container **MD5** +
  upgrade-transfer **CRC** + a `0x77557755` valid-image marker + `FIRM_MATCH` (version/hardware) —
  **no public-key signature**. A correctly packaged image is therefore accepted, which is why
  patching/replacement is feasible (`fc-bootloader.md`, `fc-replacement-plan.md`). DJI's signed
  format (`IM*H`) appears only on the later SAM E70-class products.

## 5. RF link — not cryptographically secured

- **V** (per `link-security.md`): proprietary unkeyed OFDM waveform + whitening, no link-layer
  encryption or authentication in the MCUs; association is spoofable. Over-the-air encryption in the
  FPGA datapath is **not ruled out** (unreadable datapath).

## What this means for owned-hardware work

- To **run/fly**, the gate that matters is **activation** (mechanism 1), satisfied by DJI's normal
  flow on an owned aircraft — not the ATSHA204.
- The **ATSHA204** (mechanism 2) is anti-counterfeit parts-pairing; its demonstrated effect is
  client-authorization, and a failed-chip repair is covered (with its unknowns) in
  `atsha204-repair-note.md`. None of this touches geofence/NFZ/TX-power, which stay out of scope
  (`autonomy-onboard-plan.md`).
