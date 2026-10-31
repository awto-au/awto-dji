# Aircraft-to-RC linking ("binding"): button, FPGA registers, state machine

Scope: the **aircraft Link Button** process (distinct from `duml-protection.md`'s RC-to-RC
"master/slave" multi-controller feature, and distinct from `link-security.md`'s AF3/SHA-1
finding). This is the ordinary consumer "link an RC to an aircraft" flow described in
DJI's own manual, traced here down to firmware addresses and FPGA registers.

Tags: V = read from code/docs (file:line or address), I = inferred, U = unknown, M = from
memory, W = public web. Sources: `m1400` (ground RC MCU) and `m0900` (air MCU)
disassembly, `tmp/apk` decompile, and a structural lift of the ground FPGA (`m2001`,
`awtoau/pluribus`).

## 1. User-visible process

- Documented by DJI (P3 Standard manual v1.4): power aircraft, press aircraft Link Button
  (blinks red = ready); power RC, gimbal dial to far left, toggle switch S2 quickly >=3
  times; RC pulsates beep, then stops and aircraft Link Button goes solid green = linked.
  W (manual, "Linking the Remote Controller").
- RC status LED: solid red = not connected; solid green = connected. Aircraft indicator:
  fast yellow flash = RC signal lost, failsafe RTH after >3 s loss. W.
- Pro/Adv app flow strings (V, `tmp/apk` strings.xml): "Press the Linking Remote
  Controller button to start linking" / "Press Linking Button on Aircraft" / "Linking in
  progress. Timeout will occur in %1$d." / "Linking Complete" / "Linking Timed Out" /
  "Linking failed." Motors must be off (`setting_ui_rc_cannot_frequency_motorup`).

## 2. Aircraft button, from code (V, `m0900`)

- Button sampler `0x0800B6AC` (20-tick task), active-low, board-dependent pin: boards
  4/5 = GPIOA bit2 (PA2); boards 2/6 = GPIOC bit13 (PC13); board 7 = GPIOA bit11 (PA11).
  Edge detector `0x0800B688`: held >=2 samples -> press (1), release -> (2).
- **Press:** FPGA regs `0x97..0x9B` <- `0xFF` x5 (wildcard receiver ID so any RC's signal
  is accepted during the window), toggles FPGA reg0, starts a 1000-tick countdown and sets
  a window-open flag (`0x0800076C`..`0x080107B4`). **Release:** clears the window flag.
- **Commit rule** (`0x080107D6`): if the window flag is set AND the countdown is <=400 AND
  a best-candidate score counter (`0x0800E66C`) is >=200, the aircraft takes the 5-byte
  candidate ID with the highest score, writes it to flash (`0x7C00`, erase+program via
  `0x0800BC2C`), and reloads the FPGA via `fpga_cfg_load`. If no candidate qualified, it
  reloads the previously stored ID from flash instead — i.e. **a link attempt that times
  out without a strong-enough candidate leaves the old pairing intact**, it does not clear
  it. V code; tick period (hence real seconds for 1000/400/200) not measured, U.
- Candidate scoring (`0x0800E63C`): keeps the ID with the highest `255 - min(reg 0xC5,
  0xC6 filtered)`. Those two registers are referenced elsewhere in this project's docs as
  a "dual temp" reading; their use here as a signal-quality score (not a temperature)
  should be treated as the primary role — I.

## 3. RC side, from code (V, `m1400`)

- DUML `6/0x2F` ("RC Pairing"/`SetFrequency`, `FreqMode` 1=Enter/2=Cancel) is handled at
  `0xD654`: sets a mode byte (`0x100000CA`) to 1 on Enter, 0 on Cancel; query returns
  current state. The firmware only implements modes 0/1/2 of the APK's fuller enum
  (`MasterEnter`/`SlaveEnter`/`SubEnter` are RC-to-RC, see `duml-protection.md`, not
  handled by this path). **The physical S2-button-x3 trigger for this is not traced** —
  no writer of `0x100000CA` other than `0xD654` was found by literal-pool scan; it may be
  that the physical button only reaches this mode byte via the app, not directly. Open
  question.
- While in linking mode, a 17-step LED/beep pattern runs at a 20-tick period (`0xC442` ->
  `0xC1F8`): status-LED pins set at step 0, cleared at step 8, beeper on steps 13-16.
  Linking mode exits when a key flag bit is observed (`0xC57A`).
- **ID write path to the FPGA:** see `id-entry-point.md` (SPI0, regs 3..7). On entering
  linking mode the ground MCU increments ID byte 0 and reloads the FPGA (`0x17742`); on
  leaving without success, decrements/restores (`0x1777E(0)`); on success, keeps the new
  byte and persists it (`0x1777E(1)`, `0x1F9B2`).
- **Default/test ID `01 02 03 04 05`:** both `m1400` (`0x17A94`) and `m0900`
  (`0x08010864`, called from `radio_start_stop(1)`) have a helper that sets this fixed ID,
  invoked from a DUML set-9 cmd 0x12 path and at boot. Looks like a factory/bench ID, not
  something reachable from the normal user linking flow — I.

## 4. FPGA register-level lock/mismatch detection (V, both MCU IRQ handlers)

- **Ground (`m1400` FPGA IRQ `0x171A6`):** on the status-poll IRQ bit, compares FPGA regs
  `0xE3..0xE6` (the peer ID echoed back by the radio) against the stored ID bytes [1..4].
  Mismatch -> clears a shadow bit and pulses FPGA reg0 bit1 (`0x15CFA`, a resync request)
  — this is the MCU's concrete "ID mismatch, try again" action, repeated every IRQ while
  unlinked. Match -> reg `0xE0` bits [4:0] select a period value (one of 1000/2000/4000/
  8000/3000/19000, units not established) and a 16-bit value is read from regs
  `0xE7:0xE8`.
- **Air (`m0900` RX poll `0x0800F978`):** reg `0xE9` bits [1:0] == 3 and not already
  locked -> treat as locked, read the new frame (peer ID echo at regs `0xE2..0xE6`,
  payload at `0x44..0x7B`/`0x7C..0x7F`), descramble (zero key, consistent with
  `link-security.md`'s "whitening is unkeyed" finding — this is the same descrambler, now
  confirmed from the air MCU's own call site). Timeout (45/34/39 polls depending on prior
  state) -> marks link lost, sets a no-signal marker.
- **Paired / unpaired, as concrete register conditions (I, from the above code):**
  - paired: ground `0xEB` bit0 = 1 AND `0xE3..0xE6` == stored ID[1..4]; air: `0xE9[1:0]`
    == 3 plus a good frame checksum.
  - ID mismatch (not yet paired, or wrong RC in range): ground `0xEB` bit0 = 1 but the ID
    bytes don't match -> continuous resync pulses, no lock.
  - link lost after having been paired: air RX timeout; ground `0xEB` bit0 drops to 0.
  - no radio at all: ground sets `FpgaErr` after 3 failed FPGA/AD9363 bring-up tries (see
    error table below); air skips bring-up entirely if the board-strap code isn't one of
    the handled values.

## 5. Hardware path (V)

- SPI0 (ground, `m1400`): SCK `P0.15`, MISO `P0.17`, MOSI `P0.18`, CS `P2.9`, 4 MHz,
  3-byte frames `0E reg val` (write) / `0F reg FF` (read) — see `id-entry-point.md`.
  Ground ID write sequence: read reg0, set bit7, write regs 3-7 <- ID[0..4], clear bit7.
  Air: regs `0x97..0x9B` <- ID[0..4], then reg0 bit3/bit7 bracket, regs `4..7` <-
  ID[1..4].
- FPGA reset: ground `P1.23` low pulse (see the `fpga-pinout-model.md` correction — this
  pin is real FPGA control, the LED pins beside it are not); air `PB3`.
- **Not yet found in the netlist:** the actual address-match comparator between the
  stored ID and the received peer-ID echo (expected shape: ~5 FFs XOR/equality-checked
  against bytes from the receive pipeline, feeding the `0xEB`/`0xE9` flag FFs). The
  strongest candidate enable net identified so far is pad `AB11` (an 8-FF enable, possibly
  the reg0 bit0/1/7 set/pulse line), unconfirmed.

## 6. Error / status conditions

| condition | side | user-visible | trigger |
|---|---|---|---|
| RC not linked | RC | solid red LED | FPGA lock/ID mismatch (section 4) |
| RC linked | RC | solid green LED | lock + ID match |
| Linking in progress | RC | pulsating beep, 17-step pattern | mode byte `0x100000CA` == 1 |
| Linking ready/success | aircraft | Link Button blinks red -> solid green | button window (section 2) |
| Linking success/fail/timeout | app | "Linking Complete"/"failed"/"Timed Out" | `SetFrequency` reply code; app-side timeout |
| FPGA/RF not ready | RC | log "FpgaErr" | FPGA or AD9363-lock bring-up fails x3 |
| ID mismatch | RC | none user-visible found; FPGA resync pulse only | `0x171A6`, regs `0xE3..0xE6` != ID |
| RC signal lost | aircraft/app | fast yellow flash; failsafe RTH after >3 s | air RX timeout |

## 7. Open questions

1. The physical button/switch trigger into `0x100000CA` (RC side) — not found; may only
   be reachable via the app's DUML command, not a direct GPIO-to-mode-byte path.
2. Exact address decode for FPGA regs 3..7 and the comparator location in the netlist
   (section 5) — needs full SPI0 frame simulation over the extracted shift-register chain.
3. Tick period for the 1000/400/200 counts in the aircraft button commit rule (section 2)
   — needs a bench timing measurement, not firmware-derivable.
4. Colour/beep-pattern mapping beyond the manual's red/green (bench observation).

## Corrections this doc makes to earlier analysis

- `id-entry-point.md` and `fpga-pinout-model.md` previously attributed 3 GPIO lines to
  "ID write strobes" — corrected (2026-10-31) to RC status LEDs; see those docs' own
  updated text.
- A prior internal draft of this analysis cited the `SetPassword`/`GetPassword` no-op
  finding under DUML "set 6" — the correct cmd_set is **9**, per
  `control-plane-re.md`'s already-correct, address-cited table (`0x0A`/`0x0B` fall to the
  default no-op path off the `cmd_set 9` dispatcher at `0xF6E4`). `control-plane-re.md`
  itself did not need correcting; only this cross-reference did.
