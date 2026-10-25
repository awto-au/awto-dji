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
| **Authorized Ethernet MAC** | A9 `cam_server` (`DjiMsgAuthorizedMac`) | which client (by 6-byte Ethernet MAC) may connect to the camera server; a pairing whitelist | DJI-software/client-facing; **changeable** (`t dji mac …`, `MCCTRL_AuthorizedMacUpdate`) | V |
| **Firmware integrity** | loader + xV4 container | whether a firmware image is accepted | on-device; **no signature** → patchable | V |
| **RF link "security"** | FPGA/radio | none (unkeyed waveform + whitening; no link encryption) | neither (spoofable association) | V (absence), OTA-encryption not ruled out |

## 1. DJI product activation — the real hardware gate

- **V** The FC app (`m0306`) refuses motor start when not activated: string `Product not activation,
  stop motor!`. Addresses re-derived for the loaded `P3X_FW_V01.11.0020_m0306.bin` build
  (`fc-auth-enforcement-trace.md`): the activation-state byte is read by `FUN_08046d54` (0x08046d54)
  and supplied externally by `fc_sdk_set_key` (0x08046e86); the byte is checked inside the real
  motor-arm logic (`FUN_08024b46`, which emits that exact log, and the table-driven
  `fc_Motor_fail`/`fc_Motor_Start` path that also gates auto-takeoff `FUN_080a8010`). The SDK/API
  key is **supplied externally** (DJI app/server), not derived on-device.
  (The earlier `is_prod_activated` 0x08047c2c / `check_activation_authority` 0x08047d5e /
  `dji_sdk_set_key` 0x0805a964 were from a different build's symbol map and land in an unrelated MD5
  routine in this build — superseded.)
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
- **V** Client authorization: `DjiMsgAuthorizedMac` (0x0e85f370) — `cam_server` rejects clients
  whose MAC is not authorized (its own callers live in Linux `cam_server`, not in this image, so
  that string-level claim is **U**/not re-verified).
- **V, new** (`fc-auth-enforcement-trace.md`): `CheckA9Mac`/`CheckSN` retry 3× then latch pass/fail
  into a persistent RAM flag (0x109d00b8); **≥3 other A9 functions branch on that flag and skip
  work when "unauthorized"** (a DUML report send, clearing an enable-bit 0x200, part of a
  Wi-Fi-channel-enable gate). So the check is **more than a connection filter — it gates ≥1
  on-device A9 feature path**; which subsystem is **I/U**. **No** path to the FC or to flight/boot
  was found. Repair implications: `atsha204-repair-note.md`.

## 2a. "MAC" is two different things here (don't conflate)

- **Ethernet MAC — `DjiMsgAuthorizedMac` (A9).** A **6-byte Ethernet/Wi-Fi hardware address**: the
  *authorized client's* MAC, a pairing whitelist. `cam_server` accepts the client whose Ethernet MAC
  matches. **V — decompiled** (m0100 sys partition at base `0x0E600000`, `0x0e85f370`): it copies
  the stored authorized MAC (`DAT_0e85ff68`) and does `memcmp(stored, incoming, 6)` — a **6-byte**
  compare — returning **0 (authorized)** or **0xe6 (rejected)** (with a secondary list check on
  mismatch). Also V from the strings: `Update authorized MAC: %02x:…:%02x`, `Set authorized mac.
  t dji mac xx xx xx xx xx xx`, `MCCTRL_AuthorizedMacUpdate`.
  - **Changeable: yes.** Settable by the shell command `t dji mac xx xx xx xx xx xx` and
    `MCCTRL_AuthorizedMacUpdate` (and over DUML). The underlying interface MACs are themselves
    software-set — one script even **randomly generates** a MAC (`printf "%02X:…" $RANDOM >
    /tmp/wifi1_mac`) and others read `/proc/ambarella/board_info`. So this is a mutable pairing, not
    a fused secret. Interop use: an onboard companion connecting to `cam_server` would set the
    authorized MAC to its own interface MAC.
- **Crypto MAC — `DjiEncryptCheckA9Mac` (A9) / `get_mac` (RC).** The **ATSHA204 SHA-256
  challenge/response** value (`[DJI_ENCRYPT] response_mac[…]`), §2 above. **V — decompiled**
  (`0x0e871ae0`): builds a **32-byte** nonce, computes the expected MAC on the A9 (`FUN_0e871840`)
  and reads the ATSHA204's MAC (`FUN_0e8716f8`), then XOR-compares all **32 bytes** — returning
  **0 (genuine)** or **0xe1 (fail)**. A SHA-256 response, not an Ethernet address and not freely
  settable. (What a `0xe1`/`0xe6` return then gates in the *caller* is still open — issue #45.)

### Does the ATSHA204 hold a hard Ethernet MAC (to lock the GMAC)? — no evidence on the P3

Tested the idea that the secure element stores a provisioned Ethernet MAC that the GMAC uses:
- **V** The A9 has a GMAC (`ST GMAC Registers`, `Rx/Tx GMAC` — Synopsys/ST Ethernet controller).
- **V** The Ethernet MAC comes from **`/proc/ambarella/board_info`** (`wifi1_mac` read from it), with a
  **random fallback** when empty/`00:00:00:00:00:00` (`printf "%02X:…" $RANDOM > /tmp/wifi1_mac`).
  Nothing reads a MAC out of the ATSHA204.
- **V** The ATSHA204 stores **SN + board number + the crypto secret**; every `204`/`DjiEncrypt`
  string is the *crypto* MAC (`get mac from 204`, `check a9 mac`), never a network address.
- **Conclusion:** on the P3 the Ethernet/Wi-Fi MAC is **not** sourced from the ATSHA204 — it is
  `board_info`-provisioned or random, independent of the secure element. (What ultimately populates
  `board_info` — NAND/factory env vs anything else — is **U**; it is not the ATSHA204 in the code
  seen. A secure-element-stored MAC may be a pattern on other products, but is not evidenced here.)

### The A9 has Ethernet + Wi-Fi (a full network stack)

**V** The camera Linux brings up **`eth0` at `192.168.1.12`** (`ifconfig eth0 … up`), bridges it
(`br0`), and drives an **MII PHY** (`Phy Address = 0x%x`, `MII Interrupt`) — the Ambarella A9's
built-in GMAC with a board PHY; plus `eth1`/`veth0` (virtual) and Wi-Fi `wlan0`/hostapd/
wpa_supplicant. `192.168.1.2` is the Wi-Fi module (hard-coded FTP cred). So `cam_server` is an **IP
server** and clients are identified by Ethernet MAC — which is why the authorized-MAC pairing is an
Ethernet MAC address, not the crypto MAC. (Wi-Fi clients carry the same 802 hardware MAC, so
"Ethernet MAC" here means the network hardware address in general, as distinct from the ATSHA204
crypto MAC.)

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
  `atsha204-repair-note.md`. Scope & safety: see `SAFETY.md`.
