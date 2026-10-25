# Repair note: a failed ATSHA204 component-auth chip

Scope: **repairing an owned board whose ATSHA204 authentication chip has failed.** This note records
what the chip does, **what actually blocks when it fails (which is less than it first seems)**, and
the process to stub the check if needed. Architectural (where the check is, how patching works), not
a turnkey patch — the exact offset must be found per firmware version.
Change history: see docs/HISTORY.md.

## Hardware-level block, or only DJI-software? (important — mostly the latter)

Two **different** mechanisms are easy to conflate; only one is the ATSHA204:

- **ATSHA204 component auth** runs in the aircraft's *own* firmware (A9 `DjiEncryptCheckSN`/
  `CheckA9Mac`), so it is on-device, not merely the phone app. **But the only enforcement our RE
  actually shows from it is client/app authorization:** `DjiMsgAuthorizedMac` — "`cam_server`
  rejects clients whose MAC is not authorized." Whether a *failed/absent* ATSHA204 halts boot or
  flight is **NOT established** here (**U**) — we have the check and what it compares (SN + board
  number vs the A9 NAND copy), not the mismatch consequence. So do **not** assume a dead chip bricks
  the aircraft; its demonstrated teeth are DJI-software/client-facing.
- **DJI product activation** is the separate thing that *does* gate the hardware: the FC firmware
  carries `Product not activation, stop motor!` — a firmware-enforced **motor gate** tied to DJI's
  online/app activation. This is **not** the ATSHA204; a stub of the ATSHA204 does not touch it, and
  activation is satisfied by the normal DJI flow, not by the security chip.

Bottom line: the ATSHA204 is an anti-counterfeit on-device check whose visible effect is app/client
authorization; it is **not shown** to block flight. Before stubbing anything for a "failed chip",
first confirm the chip failure is actually what's blocking you (vs activation, or the NAND-copy
side), by decompiling the `CheckA9Mac`/`CheckSN` mismatch path.

**What this is / is not.** The ATSHA204 is **anti-counterfeit component authentication** — a
SHA-256 challenge/response that proves a part is genuine DJI (`link-security.md`: "the one real
cryptographic element … authenticates genuine components … not link encryption"). It is **not** a
safety system, **not** flight control, and **not** a regulatory control (geofence/NFZ/TX-power — all
explicitly out of scope, `autonomy-onboard-plan.md`). Stubbing it is parts-pairing repair of owned
hardware. Honest dual-use caveat: the same stub also lets a non-genuine part pass the check — the
documented intent here is a dead auth chip on a board you own, not counterfeiting.

## Where the auth lives (from RE) — it is on more than one board

The ATSHA204 appears on **at least two boards**; the primary one is the **camera/A9**, not the RC:

- **Camera / A9 (`m0100`) — the primary board authentication.** A full `DjiEncrypt*` subsystem:
  `DjiEncryptInit` (I2C, config-zone lock), **`DjiEncryptCheckA9Mac`** (nonce/MAC check between the
  ATSHA204 and an A9-held copy), **`DjiEncryptCheckSN`** (compares the chip's 9-byte serial + board
  number against the copy in the **A9's NAND**), and the factory provisioning path
  (`DjiEncryptSaveBothToSha204AndA9`, `DjiEncryptWriteAllBoardNumToOTP`). The MAC/SN are provisioned
  at factory into *both* the chip and the A9 NAND, so the check fails if **either** the chip dies
  **or** the NAND copy is lost.
- **RC / GL300C (`m1400`, NXP LPC).** `sha204p_send_slave_address` + `get_mac` — the standard
  ATSHA204 MAC challenge/response (MCU sends a challenge, chip returns
  `MAC = SHA-256(challenge ‖ secret ‖ …)`, MCU compares and gates on the match).
- The P3 **FC app (`m0306`) has no ATSHA204 code**; the P4-gen FC map shows a `secure_chip_unlock`
  (wm220 `0x0050EB40`). Other boards (smart battery, etc.) may host their own — **not yet mapped**.

A **failed/absent chip** (or, on the A9, a lost NAND copy) makes the relevant check fail and the
board refuses. The stub therefore goes in **whichever board's MCU hosts the failed chip** — the A9
`DjiEncryptCheckA9Mac`/`CheckSN` gate for the camera board, the `get_mac` caller for the RC.

## Stub process (for a failed chip, owned board)

The firmware modules are **not signature-checked** (only xV4 AES encryption — public key — + MD5 +
CRC; see `fc-bootloader.md`), so the host firmware can be patched and re-accepted. Two routes:

1. **Hardware first (preferred when possible).** The auth is a *component* check; depending on the
   board the cleanest repair is to replace the ATSHA204 (a cheap Atmel part) or move the known-good
   chip from a donor board. No firmware change, no dual-use concern. Try this before patching.
2. **Firmware stub (when the chip can't be replaced).** In the module that performs the check
   (the A9 `m0100` for the camera board, `m1400` for the RC), find the **auth-result gate** — on the
   A9 the `DjiEncryptCheckA9Mac` / `DjiEncryptCheckSN` result; on the RC the caller of `get_mac` that
   compares the returned MAC — and patch that branch to take the pass path
   unconditionally (or make the compare return equal). Then recompute CRC/MD5, re-encrypt, repack
   the xV4 module (`dji_xv4_fwcon.py`), and flash via the normal upgrade. This is the same
   no-signature patch mechanism documented in `fc-replacement-plan.md`; the ATSHA204 gate is just a
   different branch to neutralise. The exact offset is **not** given here — locate `get_mac`'s
   caller in the specific firmware version and identify its pass/fail branch first.

## To confirm before relying on it

- Which board/module the *failed* chip is actually on — the stub goes in whatever MCU queries it.
  Confirmed hosts: the **camera/A9 (`m0100`, the primary)** and the **RC (`m1400`)**; a smart
  battery or other board may host its own (not yet mapped).
- That nothing safety-relevant is gated behind the same check (it should be auth-only; verify the
  `get_mac` caller only gates component-acceptance, not a flight/power function).
- Keep the stock module image for recovery (reflash via DJI Assistant), as with any patch here.
