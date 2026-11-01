# DUML encryption types

V = verified here, I = inferred, U = unknown. Two different fields are both called `encrypt_type`; do not conflate them.

## 1. Frame header: byte 8, bits 0-2 (per packet, on the wire)

| Value | o-gs dissector label | App enum (DJI-Link's reading of the DJI Fly app) | Seen on a Phantom 3 link |
|---|---|---|---|
| 0 | None | NO | **V** |
| 1 | AES 128 | DIC | never |
| 2 | Self Def | OTHER | never |
| 3 | Xor | SIMPLE | **V** (104,915 frames, 2026-11-02) |
| 4 | DES 56 | not in the enum | never |
| 5 | DES 112 | not in the enum | never |
| 6 | AES 192 | not in the enum | never |
| 7 | AES 256 | not in the enum | never |

- Labels: `o-gs/dji-firmware-tools` `dji-dumlv1-proto.lua` (GPL-3.0). It does not say where the labels come from (**U**).
- App enum: Kolya080808/DJI-Link `DUML_ENCRYPTION.md` (Apache-2.0), read from smali of `DataConfig$EncryptType`. Not checked against our GO 4 unpack (**I**).
- Our codec decodes 0 and 3 and rejects the rest (`app/packages/duml/lib/src/simple.dart`, [duml-protection.md](duml-protection.md)).
- No AES on the DUML frame path in the app: its AES libraries are for media (DJI-Link, **I**).

## 2. SIMPLE (3) behaviour

- **V** Transforms bytes 9..len-2 (cmd set, cmd id, payload) with a fixed table and the packet sequence; header and CRC16 stay clear; CRC16 is recomputed after. Self-inverse.
- **V** Never applied to COMMON (set 0x00) or camera 0x10/0x11/0x70/0x71.
- **V** The app mirrors the peer: a SIMPLE frame from the peer turns protection on, a clear eligible frame turns it off (GO `UAVPackManagerBase`, [duml-protection.md](duml-protection.md); our `auto` mode).
- **V** Independent implementation agrees: DJI-Link's worked example (param write 0x03/0xF9, seq 7) reproduces byte for byte with `applySimple`'s recurrence (run 2026-11-02).
- **V** Live Phantom 3 Pro, 2026-11-02, read-only `GetPlaneName` (0x03/0x34): forced SIMPLE got a full reply; forced clear got none. One other clear FC query drew COMMON 00/cc (`CmdNeedEncrypt`); the other did not, so 00/cc is a hint only (**I**).
- **V** 22 of 23 decoded command pairs in the capture are in the 723-row catalog once SIMPLE is undone (issue #86).
- **I** Newer aircraft also use it: DJI-Link reports a WM160 FC ignores clear config frames (0x03/0xF0-0xFA). GlassFalcon's README says a Mavic 2 (wm240) works in clear; no capture of ours (**U**).

Per-model default and runtime rules: `docs/schema/duml/protection-profiles.yaml`.

## 3. Firmware container (xV4 entry): a different field

- Entry `encrypt_type` = byte 1 high nibble. 0 = plaintext (`m1900` FPGA, LPC images). 1 = AES-128-CBC, IV 0, cipher reset every 256 bytes, upstream's public module key (`m0306` and most modules). **V** ([stm32-reversing-process.md](stm32-reversing-process.md), [firmware-overview.md](firmware-overview.md), [fc-bootloader.md](fc-bootloader.md)).
- Newer DJI products use the signed `IMaH` container instead ([firmware-overview.md](firmware-overview.md)).
- Whether this field uses the same numbering as the frame header is not verified (**U**).

## 4. Not `encrypt_type`

- ATSHA204 component authentication and General 0x30 `Encrypt Config` (factory key pairing; failing verification can leave a device ignoring most commands): [security-and-activation.md](security-and-activation.md). Not sent by this repo.
- RC master/slave connection: sent clear ([duml-protection.md](duml-protection.md)).
- Over-the-air protection: not ruled out ([what-is-actually-secret.md](what-is-actually-secret.md)).
- Flight-record log encryption (pydjirecord): unrelated to DUML frames.

## Open

- Do header values 1, 2, 4-7 ever appear on any product?
- Same numbering for the header field and the xV4 field?
- wm240: clear on the wire, or only on some commands or paths?
