# Where the Master-ID enters the FPGA (ground link)

Question: find where the pairing/Master-ID enters the Lightbridge FPGA.

**Resolved (2026-10-31).** Earlier versions of this doc guessed GPIO/UART from firmware
disassembly alone, before any `m2001` netlist existed (the "void m2001 decode" below was
once true and is no longer). The answer is now confirmed from both sides: `m1400`
disassembly AND a full structural lift of the `m2001` bitstream (Cyclone IV GX EP4CGX150;
`awtoau/pluribus`, `docs/altera/cycloneIV/`) agree on the same transport.

## Short answer

The ID is **not computed inside the FPGA and not a hardcoded constant.** It is owned by
the **ground MCU `m1400` (`gnd_rc_lpc1765`, LPC1765 "GROUND LB2")**, which writes it into
the ground FPGA over the **SPI0 register bus** — *not* GPIO, *not* UART, *not* the AD9363
RF sample bus, *not* the FX3/USB video path.

- **Firmware side (V, `m1400` disasm):** `fpga_set_receiver_id` at `0x16850` writes the
  5-byte ID as five `0E reg val` SPI0 frames to FPGA registers **3..7**, bracketed by a
  reg0 bit7 set/clear handshake (`0x15D4A`). SPI0: SCK `P0.15`, MISO `P0.17`, MOSI `P0.18`,
  CS `P2.9`, 4 MHz — the same `[0E reg val]`/`[0F reg FF]` register protocol as the air
  side (`docs/ground-upgrade-path.md`).
- **FPGA side (V, netlist):** a byte deserialiser exists on pad `pad_AG12` (contradicts an
  earlier note in `dji_pins/board/README.md` that no SPI slave FSM was found — that row
  should be re-checked). 344 distinct enable nets load flip-flops directly from the 8-bit
  shift chain; this is the SPI-fed register file, and registers 3..7 (the ID) are five of
  them. The exact address decode (which enable net is "register 3" vs "register 7") and
  the comparator that checks a received peer ID against this stored value (feeding status
  register `0xEB` bit0) have **not** yet been located in the netlist — open item, needs a
  full SPI frame simulation over the extracted shift chain.
- **The three GPIO lines this doc previously called "ID strobes" are not that.** `P0.16`,
  `P1.22`, `P3.25` are the **RC status LED outputs** — confirmed because the same pins are
  driven by the LED colour-code routine (`0xB226`, colour byte 1/2/3) and the link-mode
  blink/beep pattern (`0xC1F8`). `P1.23` is a real FPGA control line, but it is the
  **FPGA reset pulse** (`0xBB86` / update-finish paths), not part of the ID write.

## What else is now known about the pairing path (from the same analysis)

- **Linking changes the ID, it isn't fixed at manufacture.** On entering link mode the
  ground MCU increments ID byte 0 and reloads the FPGA; on success it persists the new
  ID[0] to internal flash (sector 8 + offset `0x90`); on cancel/failure it restores the old
  one. ID bytes [1..4] are derived from the LPC1765's own unique ID (CRC/XOR over the IAP
  "read UID" result) and do not change. (V code, I "derived from UID" — the CRC steps were
  located but not value-checked.)
- **No key or nonce anywhere in the ID/pairing path.** Absence confirmed by reading every
  handler that touches the ID or the DUML pairing commands (`6/0x06`..`6/0x3C`). This is
  consistent with `link-security.md`'s existing claim that binding is by identifier, not a
  crypto key pair — this is now confirmed from the ground MCU side specifically, not only
  inferred from the app/DUML layer.
- **A genuinely cryptographic engine does exist elsewhere on this board** (inside the
  ground FPGA itself, not in the pairing path) — see `link-security.md`'s AF3 finding. It
  plays no role in ID/pairing; it is listed here only so the two don't get conflated.

## What still needs the board schematic

- **Exact MCU-pin -> FPGA-ball mapping.** The netlist gives FPGA ball locations but not
  which board net each ball joins; confirming "this ball is SPI0 MOSI" by schematic rather
  than by protocol-shape inference needs the GL300/C1 ground-unit schematic (not held).
- **The address-match comparator's exact location in the fabric** (above) — tractable from
  the netlist alone with more simulation work, not blocked on the schematic.

## Why this was never the blocker for the link goal

Per `minimal-recovery.md` / `alternative-approaches.md`, interop never required pin-level
tracing of the ID inside the FPGA — reading the ID value and its frame position both come
from a cleartext DUML capture, not from resolving the fabric. That remains true. This doc's
update is about getting the *architecture* right (SPI0, not GPIO/UART), not about reopening
interop work that was already unblocked by capture-based methods.
