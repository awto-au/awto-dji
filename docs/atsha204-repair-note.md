# Repair note: a failed ATSHA204 component-auth chip

Scope: **repairing an owned board whose ATSHA204 authentication chip has failed.** When that chip
dies, the host MCU's component-auth check fails and the board refuses to operate even though
everything else is fine. This note records what the chip does and the process to stub its check so
the owner can revive the board. It is deliberately architectural (where the check is, how patching
works), not a turnkey patch — the exact byte offset must be found per firmware version.

**What this is / is not.** The ATSHA204 is **anti-counterfeit component authentication** — a
SHA-256 challenge/response that proves a part is genuine DJI (`link-security.md`: "the one real
cryptographic element … authenticates genuine components … not link encryption"). It is **not** a
safety system, **not** flight control, and **not** a regulatory control (geofence/NFZ/TX-power — all
explicitly out of scope, `autonomy-onboard-plan.md`). Stubbing it is parts-pairing repair of owned
hardware. Honest dual-use caveat: the same stub also lets a non-genuine part pass the check — the
documented intent here is a dead auth chip on a board you own, not counterfeiting.

## Where the auth lives (from RE)

- The ATSHA204 is driven on the **ground/RC side (module `m1400`, NXP LPC)** — symbols
  `sha204p_send_slave_address` and `get_mac` (the Atmel ATSHA204 I2C/SWI library). The flow is the
  standard ATSHA204 MAC challenge/response: the MCU sends a challenge, the chip returns
  `MAC = SHA-256(challenge ‖ stored secret ‖ …)`, the MCU compares it to an expected value and gates
  operation on the match. A **failed/absent chip** returns no/garbage MAC → the compare fails →
  the board is refused.
- The P4-generation FC map also shows a `secure_chip_unlock` (wm220 `0x0050EB40`); the P3 FC app
  (`m0306`) itself contains **no** ATSHA204 code — the auth is a ground-side (and likely
  battery/aircraft-side) function, not the flight controller's.

## Stub process (for a failed chip, owned board)

The firmware modules are **not signature-checked** (only xV4 AES encryption — public key — + MD5 +
CRC; see `fc-bootloader.md`), so the host firmware can be patched and re-accepted. Two routes:

1. **Hardware first (preferred when possible).** The auth is a *component* check; depending on the
   board the cleanest repair is to replace the ATSHA204 (a cheap Atmel part) or move the known-good
   chip from a donor board. No firmware change, no dual-use concern. Try this before patching.
2. **Firmware stub (when the chip can't be replaced).** In the module that performs the check
   (`m1400` for the RC side), find the **auth-result gate** — the caller of `get_mac` that compares
   the returned MAC and branches on pass/fail — and patch that branch to take the pass path
   unconditionally (or make the compare return equal). Then recompute CRC/MD5, re-encrypt, repack
   the xV4 module (`dji_xv4_fwcon.py`), and flash via the normal upgrade. This is the same
   no-signature patch mechanism documented in `fc-replacement-plan.md`; the ATSHA204 gate is just a
   different branch to neutralise. The exact offset is **not** given here — locate `get_mac`'s
   caller in the specific firmware version and identify its pass/fail branch first.

## To confirm before relying on it

- Which board/module the *failed* chip is actually on (RC `m1400`, smart battery, or aircraft) — the
  stub goes in whatever MCU queries it. Our symbol evidence is the RC side (`m1400`).
- That nothing safety-relevant is gated behind the same check (it should be auth-only; verify the
  `get_mac` caller only gates component-acceptance, not a flight/power function).
- Keep the stock module image for recovery (reflash via DJI Assistant), as with any patch here.
