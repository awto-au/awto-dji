# Fact-correction history

Dated changelog of fact-corrections previously narrated inline in the docs. Each entry is
phrased as "initial understanding -> corrected finding." The docs now state only the
corrected/current fact; this file preserves the history for reference.

## 2026-10-25 (systematic STM32 pass on air_router, closing the gap with air_fc)

- **`air_router_stm32f103` (m0900) got its first systematic (not opportunistic)
  `stm32-reversing-process.md` pass, via a background agent, reviewed and spot-checked (4
  claims decompiled and confirmed directly) before merging.** Confirmed register library as ST
  StdPeriph/SPL via 3 independent call-signature idioms plus a new, reproducible 9-entry
  NVIC/IRQn table whose values match the real STM32F103 vector table exactly. Re-ran the
  existing 152-address literal-pool sweep to completion and triaged all of it for the first
  time: 42 (28%) are proven false positives (value lies outside the actual 20 KB SRAM range, so
  they can't be real pointers — they're data-table bytes that coincidentally decode as RAM
  addresses). Of the 24 globals in the `0x200000a0-0x200001fe` cluster (previously 4 named), 13
  now carry a real type or resolved role: 4 new Ghidra `Structure` types applied at their RAM
  addresses with flash-side pointers retyped to match (`PA1FaultCounters`, `AntennaQuadrantState`
  — an address-exact match to the upstream map's quadrant-state cluster, now with real field
  semantics — `FpgaSensorAvgState`, `FlycDetectSampler`) plus 7 plain-typed globals and 17
  function renames. 3 cluster addresses honestly left **U** (inside one large, not-fully-
  decomposed FPGA/radio state machine) rather than guessed. Confirmed explicitly that step 6
  (parameter-table extraction) does not apply to this chip — its config is one opaque 252-byte
  blob, no `FlycExportParam`-equivalent array exists. (`docs/air-router-stm32-full-pass.md`,
  `docs/symbols/m0900-structs.h`, `docs/symbols/m0900_V01.11.0020.tsv`)

## 2026-10-25 (XOR key traced — it's zero)

- **`ofdm_payload_descramble`'s 8-byte XOR key, traced to source.** Located at
  `radio_state_s+0x64` (RAM `0x20001b18`-`0x20001b1f`, inside the struct's previously-opaque
  `pad_10` gap). No DUML command handler writes this offset (Set Config writes a different,
  earlier struct); a direct reference search of all 8 bytes found zero writers anywhere in the
  firmware. Traced how the RAM region gets its boot-time value: the C-runtime's RAM-init table
  has two region descriptors, and the key's address falls inside the one whose initializer is a
  plain zero-fill loop (the *other* descriptor, covering a different RAM range, really does use
  a compressed-copy decompressor — so this is a specific finding, not "everything's zero").
  **The key is always zero in this build; the XOR step is a no-op, and the real validation is
  the two-stage checksum alone, not encryption.** (`docs/air-router-deep-dive.md` §6a)

## 2026-10-25 (second ring resolved — RF link confirmed, not a bus guess)

- **`fpga_uart_to_fc_relay`'s first ring, previously open, fully resolved.** Ruled out CAN
  entirely first (traced all 4 real `can_queue_init` call sites — `0x412`/`0x413`/`0x414`/
  `0x415` — none registers this ring's address). The actual source is `FUN_0800e008`
  (named `ofdm_payload_descramble`): an XOR-with-repeating-key + chained-checksum validator
  whose sole caller, `FUN_0800f978` (`ofdm_link_rx_statemachine`), is the live AD9363/OFDM
  radio link's own receive poll loop (polls an FPGA status register, checks demod-lock state,
  processes newly-arrived frames). **Both of `fpga_uart_to_fc_relay`'s rings are now confirmed
  RF-sourced** — one via the FPGA's UART framing (USART3), one via the FPGA's SPI
  status/payload interface — and both get relayed verbatim to the FC on USART1. This is the
  strongest evidence yet, independent of the retracted log, that `air_router` really does
  forward radio-link traffic to the flight controller. Flagged for a future pass: the
  descrambler's XOR key and checksum scheme are worth tracing on their own (fixed vs.
  pairing-derived). (`docs/air-router-deep-dive.md` §6a, `docs/symbols/m0900_V01.11.0020.tsv`)

## 2026-10-25 (RF-to-FC relay found)

- **A real, code-confirmed USART3 (FPGA/radio UART) → USART1 (FC UART) relay inside
  `air_router`, found while chasing whether RF/CAN forwarding to the RC exists** (independent
  of, and not relying on, the retracted `duml_watch.log`). `FUN_080103f8` (named
  `fpga_uart_to_fc_relay`), called every other tick from the main scheduler, drains two ring
  buffers through the DUML parser and relays any complete frame straight to `send_usart1` —
  bypassing `air_router`'s own dispatch table entirely. One of the two rings is an exact
  address-level match for `usart3_irq`'s own RX push target, and USART3 is the already-known
  "FPGA UART" — so inbound traffic on the radio-facing UART gets bounced verbatim to the FC.
  The other ring's source was traced as far as ruling out all three UART RX IRQs and the
  static CAN-ID dispatch table (which is populated at runtime, not visible in the static
  image) — genuinely still open, not yet a CAN/RF source confirmed. Also incidentally named
  `usart2_irq` (previously unnamed) while ruling out the UART IRQs as the second ring's source.
  (`docs/air-router-deep-dive.md` §6a, `docs/symbols/m0900_V01.11.0020.tsv`)

## 2026-10-25 (retraction)

- **`captures/sessions/2026-10-24/duml_watch.log` retracted, per operator instruction — stop
  citing it.** Everything downstream of it in `fc-usb-duml.md`'s "Breakthrough, live hardware"
  section (the claim that the aircraft's front port answers DUML as `air_router`/`GL300C`, the
  receiver sweep, the `0x14` anomaly) is retracted along with it, not merely flagged open. This
  was already in doubt: the identity string it reported was independently found to not exist in
  either `air_fc`'s or `air_router`'s own firmware. The section is kept in the doc, marked
  retracted, for the paper trail; nothing in it should be treated as established. What the
  front port actually reaches is open again, pending a clean re-test.
- **Renode "USB interrupt never unmasked" claim downgraded, same pass.** The static evidence
  (dead vector-table entries in flash, five USB IRQ slots sharing one self-loop target) stands
  on its own, chip/emulator-independent. The dynamic claim ("never unmasked within 2s of
  simulated boot") does not: that 2s window ends inside an SD-card status poll that Renode's
  generic peripheral model can never satisfy (always reads `STA=0`), so the simulated boot
  never gets past that point to show what happens next. Correctly identified by the operator as
  an unexamined confound. Not re-tested (the Renode binary from the earlier session isn't
  available in this one) — recorded as open, not resolved. (`docs/fc-usb-duml.md`)

## 2026-10-25 (deeper follow-up)

- **cmd `0xfe` (`air_router_stm32f103`, set 0x00) re-examined and found to be more significant
  than first described:** initial understanding (from the completeness pass above) was "mode 1
  calls an untraced helper and replies 1 status byte" -> fully traced: `0x080010af4` is a
  pointer variable whose value is `0x20001ab4`, the exact base of the already-typed
  `radio_state_s` struct, so mode 1 writes host-supplied payload bytes **directly into the live
  radio-state struct**, then reloads the FPGA from it (`fpga_cfg_load`) and re-runs the radio's
  full bring-up sequence (`radio_first_init`) — an engineering-style "push raw state and force
  reload" command, not a status query. No authentication/validation gate was found on either
  mode. Also resolved in the same pass: cmd `0x0c`'s previously-opaque status global
  (`0x080125e8`) is a pointer to the already-known `fpga_boot_status` handshake state machine's
  own variable, not a separate undocumented flash constant; cmd `0xff`'s type-9 reply copies a
  fixed 32-byte RAM blob populated by the C-runtime `.data` initializer at boot (content still
  unidentified). (`docs/air-router-io-and-naming.md` §2.4/§6, cross-referenced from
  `docs/air-router-deep-dive.md`)

## 2026-10-25 (later still)

- **`air_router_stm32f103` (m0900) completeness pass closes the I/O-inventory/naming gap left
  open after the first deep dive:** 17 more handlers named via direct `(set,cmd)`-key
  correspondence with the upstream `V01.07.0060` map (one upstream name,
  `cmd_exec_flyc_unlimit_state`, explicitly does **not** reconcile with cmd `0x42`'s actual
  simple-forward behavior — reported as a mismatch, not forced); cmd `0xfe`/`0xff`/`0x0c` fully
  decompiled — notably cmd `0xff`'s "catchall" is **not** inert: for the FPGA receiver it replies
  with a hardcoded firmware-ID string matching the upstream map's own string symbol byte-for-byte
  across a 4+ year firmware gap. First Ghidra project built for `m0900` (426 functions, 107
  named). New I/O found: `PA4` (role unknown), joint `PB3+PB6` config, a `PA1` pulse-strobe
  candidate antenna/quadrant-switch relay (supported by an address-exact RAM cross-check against
  the upstream map's `ofdm_board_version_flags`/`switch_active_quadrant` cluster). Spot-checked
  directly against the new Ghidra project (cmd `0xfe`/`0xff`/`0x0c`, `pa1_pulse_strobe`) before
  trusting/committing. (`docs/air-router-io-and-naming.md`)

## 2026-10-25 (later)

- **`air_fc_stm32f427` receiver-forward / debug-port question, resolved negative:** initial
  question was whether `air_fc` has code that forwards DUML frames addressed to receivers it
  doesn't own (explaining why its front port answers as `air_router`), or a generic
  debug/bus-sniff command -> traced `air_fc`'s own full incoming-command dispatch table
  (`0x080ab440`-`0x080ab644`, ~65 entries) and found **no** wildcard/catchall/forwarding entry
  — every entry is one of `air_fc`'s own owned `(cmd,cmd_set)` pairs, almost all `cmd_set=3`
  (FLYC). Combined with the already-documented facts that `air_fc`'s own USB-OTG interrupts
  are dead code and the front connector is publicly documented as a UART (not real USB-CDC),
  the simplest explanation is that the connector taps the same internal UART bus
  `air_router_stm32f103` also listens on, so `air_router` itself answers receiver-`0x0e`
  queries directly — no forwarding or debug backdoor inside `air_fc` is needed or found.
  (`docs/fc-usb-duml.md` "Does air_fc itself forward DUML frames by receiver type?")

## 2026-10-25

- **`air_router_stm32f103` (m0900) deep dive closes five open items:** (1) `dataflow.md`'s
  "16-bit-id table, how reached: U" -> it's a nested dispatch level, reached by one outer-table
  stub (`0x080125dc`) tail-jumping into the inner matcher. (2) `fpga-upgrade-path.md`'s RAM flag
  `0x200000c8` "consumer not decoded" -> the IWDG-feed gate; setting it forces a hardware reset.
  (3) Flash page `0x7b00` "use not decoded" -> a live DUML get/set/commit triplet backing the
  `radio_state_S` RAM struct. (4) Flash page `0x7800` "use not decoded" -> written by Set
  Device Version (`0x0D`). (5) `dataflow.md` §5a's cmdset-9 SetFPGA/Set9363 naming "mismatch"
  -> not a mismatch; cmd `0x04` has its own dedicated handler, an earlier trace just hadn't
  checked it separately from `0x06`. Full command-table walk also gives a verified-negative
  result for CAN camera/gimbal payload semantics (m0900 never inspects them — confirmed pure
  pass-through, not just untraced). Update-Transmit mystery narrowed (hand-off mechanism fully
  traced) but not solved (what the absent bootloader does with it is still U).
  (`docs/air-router-deep-dive.md`, cross-referenced from `dataflow.md`, `fpga-upgrade-path.md`,
  `fpga-bringup.md`)
- **Terminology: "radio MCU" retired across 13 docs** -> replaced with the canonical
  `naming-map.md` names (`air_router_stm32f103` for the air-side m0900; `gnd_rc_lpc1765` for
  the ground-side m1400/m1401), since "radio MCU" pre-dated the naming scheme and wasn't a
  module name. While fixing it, found and corrected a genuine fact error in
  `control-plane-re.md` (not just terminology): one line claimed the ground MCU was "same
  STM32F103 family" as the air MCU -> it is NXP LPC1765/LPC1549, a different vendor/family
  entirely (the doc's own later section already had this right; the early mention was stale).
- **m1401 (ground radio, LPC1549 variant) analysed for the first time:** was previously noted
  only as "LPC1549 variant of m1400... not analysed further" -> a separate, richer upstream
  symbol map (`C1_FW_V01.06.0000_m1401.map`/`.idc`, o-gs/dji-firmware-tools) already vendored
  locally but not examined was found (user-prompted) to carry `get_board_version`,
  `packet_hw_receive`, `ofdm_init_instruction`, and `cmd_exec_setXX_cmdYY` handler names.
  `get_board_version` decompiled (file offset `0x11ce4`): calls a shared compare-and-log helper
  against RAM `0x2000600`; no direct caller found yet (likely a function-pointer table entry).
  Confirmed against the real re-extracted binary (same `c1.bin` verified earlier), same
  2016-03-21 build vintage as m1400. New open question: which chip family (m1400/LPC1765 vs
  m1401/LPC1549) the operator's actual GL300C uses — the live build string doesn't disambiguate,
  and neither 2016 build matches the live-reported 2017-08-28 date regardless. (`docs/
  ground-upgrade-path.md` §Q6, `docs/data-manifest.md`)
- **RC's own micro-USB port (`2ca3:0008`) identity:** initial understanding was open between
  three hypotheses — m1400's own USB peripheral, a second Cypress FX2/FX3 bridge chip (DJI
  reuses FX2LP elsewhere), or an LPC boot-ROM/ISP mode -> **resolved**: the descriptor strings
  (`DJI  CONFIF  `, `DJI    CONTROLLER`, `0001A0000000`) and `VCOM`/`MSCM` class tags are
  literal constants inside m1400's own compiled image, ruling out a second bridge chip;
  answering a real DUML GetVersion rules out a bare boot-ROM mode. Matches the aircraft FC's
  identical `VCOM`/`MSCM` pattern. **Correction, same day:** the first evidence for this was a
  grep of the wrong firmware build (`P3X_FW_V01.03.0020`'s bundled m1400 copy; its build-date
  string doesn't match the operator's `WM320_A7_LPC1 20170828/00`) -> re-grounded on the
  correct version's own IDA symbol map (`C1_FW_V01.06.0000_m1400.map`), which independently
  names the same `aDjiConfif`/`aVcom`/`aMscm` string symbols. **Resolved fully, same day:**
  re-obtained the real `c1.bin` from a live CDN URL (`dl.djicdn.com/downloads/lightbridge2/
  C1_FW_V01.06.0000.bin`), hash-verified exact, unpacked, and confirmed the same strings
  directly in the real binary at the symbol map's address (offset-adjusted). **New finding this
  surfaced:** this container's m1400 submodule (build-tagged `WM610 A7_1765 20160321/01`)
  predates the operator's live-reported build (`WM320_A7_LPC1 20170828/00`) by ~17 months — the
  container hash matches and its FPGA submodules are independently confirmed current, but DJI
  evidently updates modules independently inside one version tag, so this specific m1400 build
  is not bit-identical to what's actually running. (`docs/ground-upgrade-path.md` §Q5,
  `docs/fc-usb-port.md`, `docs/data-manifest.md`)
- **FC activation-gate addresses:** initial understanding cited `is_prod_activated` 0x08047c2c /
  `check_activation_authority` 0x08047d5e / `dji_sdk_set_key` 0x0805a964 -> corrected: those are
  from a *different build's* symbol map (V01.07.0060) and land in an unrelated MD5 routine in the
  loaded V01.11.0020 image. Re-derived for this build: activation-state read `FUN_08046d54`, fed by
  `fc_sdk_set_key` (0x08046e86), checked inside the real motor-arm logic (`FUN_08024b46` emitting
  "Product not activation,stop motor!", and the table-driven `fc_Motor_Start` path gating
  auto-takeoff). The gate-is-real conclusion is unchanged. (`docs/security-and-activation.md`,
  `docs/fc-auth-enforcement-trace.md`)
- **A9 ATSHA204 MAC/SN effect:** initial understanding = "only demonstrated effect is client/app
  authorization" -> refined: the `CheckA9Mac`/`CheckSN` result latches a persistent A9 RAM flag
  (0x109d00b8) that ≥3 other A9 functions branch on, skipping work when unauthorized, so it gates
  ≥1 on-device A9 feature path (which subsystem = I/U). Still **no** tie to the FC or flight/boot.
  (`docs/security-and-activation.md`, `docs/fc-auth-enforcement-trace.md`)
- **P4 flight-controller MCU:** initial understanding guessed a bigger STM32F4-family part ->
  corrected to Microchip/Atmel **ATSAME70Q21** (Cortex-M7). The `0x2040_0000` RAM-base
  observation was at one point withdrawn on an assumption of STM32, then shown to in fact be
  the SAM E70 signature (flash @ `0x00400000`, SRAM @ `0x20400000`, 384 KB). (`docs/prior-art.md`)
- **m0306 register library:** initial understanding described it as "DJI's own raw HAL" ->
  corrected to **ST Standard Peripheral Library (SPL / StdPeriph)**, established by code
  structure (RCC/GPIO/USART/CAN call signatures), not strings. (`docs/fc-io-inventory.md`)
- **UART base/baud:** initial understanding said the config "lives in RAM and can't be
  recovered" -> corrected: the base comes from a flash lookup table `USARTx[8]` at
  `0x803bfd8`, and the SDK/API baud is a named parameter with flash defaults
  (`api_entry_cfg.baud_rate` default **230400**, min 110, max 921600). (`docs/fc-io-inventory.md`)
- **FC slots:** initial understanding concluded "single-slot, no A/B" from the app alone ->
  corrected: the app is single-image, but the `m0305` loader/updater implements a true
  **two-slot A/B** scheme (bank-1 app `0x08020000`, bank-2 `0x08100000`), with the loader
  (sectors 0-4) excluded from the erase path. (`docs/fc-bootloader.md`)
- **ATSHA204 location:** initial understanding implied RC/`m1400`-only -> corrected: the
  primary ATSHA204 board authentication is on the **camera/A9 (`m0100`)**, with a second
  instance on the RC (`m1400`); the P3 FC (`m0306`) has no ATSHA204 code.
  (`docs/atsha204-repair-note.md`, `docs/security-and-activation.md`)
- **ATSHA204 effect:** initial understanding implied a failed/absent chip bricks the board ->
  corrected: the only enforcement RE demonstrates is **client/app authorization**
  (`cam_server` rejecting an unauthorized MAC via `DjiMsgAuthorizedMac`); whether a
  failed/absent chip halts boot or flight is unestablished (U). The real firmware-enforced
  hardware motor gate is **DJI product activation**, a separate mechanism.
  (`docs/atsha204-repair-note.md`, `docs/security-and-activation.md`)
- **Compiler/toolchain:** initial understanding recorded "compiler: U(nknown)" -> corrected to
  **IAR Embedded Workbench**, from the upstream IAR linker symbol map
  (`__iar_program_start`) for the adjacent build V01.07.0060. (`docs/fc-io-inventory.md`)
