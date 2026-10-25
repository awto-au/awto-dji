# NXP LPC firmware reversing: the repeatable process

Checklist distilled from reversing m1400 (C1 ground RC, NXP LPC1765, Cortex-M3). Parallel to
`stm32-reversing-process.md` — same shape, different vendor. Apply it to m1401 (LPC1549 variant)
and any other LPC-family ground module. Tags: **V** verified, **I** inferred, **U** unknown.
Fact-changes go in `docs/HISTORY.md`, not inline. Doc index: `docs/README.md`.

## 0. Rule zero: cross-check prior art FIRST — confirmed, not assumed

Checked, not just believed likely: the `C1_FW_V01.06.0000_m1400.map` already vendored at
`docs/symbols/upstream/` **is sourced from o-gs/dji-firmware-tools** (GPL-3.0), same project and
licence as the STM32 maps — `PROVENANCE.md` already states this. So "where did the IDA file come
from" is answered and was already documented; it isn't a fresh finding, just a confirmation.

- No public write-up of the LPC1765/C1 ground-radio reversing was found beyond that one vendored
  `.map` (web search, 2026-10-25: o-gs's own wiki covers DaVinci/Ambarella flashing, not this
  chip). Treat this doc + `ground-upgrade-path.md` as the first consolidated LPC-side account.
- No public CMSIS-SVD file for LPC17xx was found vendored anywhere in this repo or scratchpad —
  **but one plausibly exists**: NXP's own community support points to an `LPC176x-5x SVD.zip`
  (community.nxp.com thread, 2026-10-25 search); the family name should cover the LPC1765. Not
  yet obtained or tried in Ghidra — see step 3.
- Check `docs/symbols/upstream/PROVENANCE.md`, `docs/symbols/c1_m1400.tsv`, and
  `ground-upgrade-path.md` before re-deriving anything; `grep -ri <thing> docs/` first.

## 1. Obtain and identify the module

- Same xV4 container format and `m%02d%02d` naming as the STM32 side (`xv4_extract.py`).
- **Difference from STM32:** LPC modules observed so far are **not** DJI-AES-wrapped
  (`encrypt_type=0`) — confirmed this session by entropy (6.99, not ~7.9999 ciphertext-flat) and
  a sane Cortex-M vector table at offset 0 of a bundled m1400 copy. No `xv4_decrypt.py` step is
  needed before disassembly; `ground-upgrade-path.md`'s own intro just says "static disassembly
  of `C1_FW_V01.06.0000_m1400.bin`" with no decrypt step, which is why.
- **Gotcha, live right now (#60):** the real `C1_FW_V01.06.0000_m1400.bin` is not currently in
  this analysis environment — only its `.map`/`.idc` symbol files survived from an earlier
  session. Verify by the SHA-256 in `data-manifest.md` once re-obtained; don't assume a
  differently-named bundled copy (e.g. from an older combined `P3X_FW_*` package) is the same
  build without checking its own build-date string first (caught and corrected this session —
  see `HISTORY.md` 2026-10-25).

## 2. Determine core and load base

- Read the first 8 bytes: initial SP, then reset vector (same recipe as STM32 step 2).
- **Difference from STM32:** LPC17xx SP lands in **`0x10000000+`** (on-chip local SRAM, 32 KB on
  the 1765/256 KB-flash part), not `0x2000_0000+`. Flash base is `0x00000000`, but the *app*
  loads at a positive **offset**, not base 0 — m1400's app is at flash offset `0xA000`
  (`ground-upgrade-path.md` "Addressing (correction)": image-offset addresses in the `.map`/TSV
  are file offsets; flash address = offset + `0xA000`, confirmed against the reset-handler jump).
- The region below the app offset (`0x0000-0x9FFF` here) is the **resident bootloader area**,
  not in the container — same shape as the STM32 FC's loader-below-app pattern, different
  offset/size. `Q4` in `ground-upgrade-path.md` has the full argument for why it's inferred to
  exist and roughly how big it can be.
- No Cortex-A analogue needed on this side (no LPC module here runs Linux).

## 3. Load into Ghidra — not yet done for any LPC module

- **Gap, not yet closed:** no Ghidra project exists for m1400 (or m1401). All LPC work so far
  (`ground-upgrade-path.md`) used `scripts/re/mcu_trace.py`, a capstone-based disassembler —
  lighter than Ghidra, no decompiler, no persistent project.
- Language for when this is built: `ARM:LE:32:Cortex`, raw binary, base = flash offset
  `0xA000` (step 2) for the app; a separate load would be needed for the bootloader region once
  obtained via SWD.
- **Peripheral labelling has no equivalent to `fc_setup.py` yet.** The STM32 side applies a
  CMSIS-SVD file for register names; no SVD has been obtained or tried for LPC17xx here. NXP's
  own `LPC176x-5x SVD.zip` (step 0) is the candidate — fetch it, confirm it covers the 1765, then
  write an `lpc_setup.py` analogous to `fc_setup.py` (MMIO blocks + SVD labels). Until then,
  peripheral base addresses are cited as bare literals in the docs (works, just unstructured).
- **Known peripheral bases already recovered by hand** (worth seeding the SVD-less labelling
  with, from `ground-upgrade-path.md`/`id-entry-point.md`): legacy SPI0 `0x40020000`, GPIO
  FIOSET/FIOCLR region (P0/P1/P2/P3 pins named per-use, no single base cited yet), flash sector
  table at image offset `0x25460`.

## 4. Identify the register library — already done, it's NXP's own, not ST's

- **Different question on this chip, already answered.** STM32 asks SPL vs HAL vs LL; LPC's
  flash-programming path instead asks **LPCOpen vs bare register ops**, and it's LPCOpen: the
  vendored `.map` names `Chip_IAP_EraseSector`/`CopyRamToFlash`/`BlankCheckSector`/`Compare`/
  `PreSectorForReadWrite` and `iap_entry` (`0x1FFF1FF1`) verbatim — NXP's own boot-ROM IAP
  wrapper names, not DJI's. This is **documentation status**, not a fresh ID step: the names
  come from NXP's public LPCOpen library, carried into the symbol map, not from string-anchoring
  DJI's own code (contrast step 5, which is DJI-specific).
- No register-access idiom hunt is needed here the way `RCC_GetClocksFreq` anchors SPL on STM32
  — the IAP entry point itself (`iap_entry`) is the one fixed, vendor-documented anchor; wrapper
  call sites fall out from its callers.

## 5. String-anchored function naming — same method, one new technique to carry forward

- Same Part A (`port_symbols.py UPSTREAM.map OUR_dec.bin`) / Part B pattern as STM32 step 5. One
  format gotcha: the vendored LPC file set includes both a `.map` (plain `address<TAB>name`
  text, directly compatible with `port_symbols.py` as-is) and an `.idc` (IDA script calling
  `MakeName(addr, "name")` per line) — the `.idc` needs a small regex adapter to pull `(addr,
  name)` pairs before it's usable the same way; not yet written.
- **New technique found this session, not LPC-specific — fold into step 5 generally:** USB
  (and other) string *descriptors* are UTF-16LE, not plain ASCII, so a bare `strings` pass misses
  them. A small ASCII-run-over-UTF-16LE regex catches them:
  `re.compile(rb'(?:[\x20-\x7e]\x00){4,}')`, then `.decode('utf-16le')`. This is how the m1400
  USB-port identity strings (`DJI  CONFIF  `, `VCOM`, `MSCM`) were found in a raw byte scan
  without IDA/Ghidra at all — cheap, and worth running on *any* MCU image before assuming a
  string isn't there.
- Record names in `docs/symbols/c1_m1400.tsv` the same way (`addr name note source`).

## 6. Parameter table — likely doesn't apply the same way

- m1400 has not been found to export an FC-style `FlycExportParam` array. What exists instead:
  a config page at flash sector 9 (`ground-upgrade-path.md` "Other flash pages written by the
  app" — 16 B device-version record, an 0x86 B config block compared against RAM and rewritten
  on change) and sectors 7/8 with undecoded read/write wrappers. Treat this as the LPC-side
  analogue to chase, not assume it mirrors the FC's table layout.

## 7. I/O inventory — the one sharp gotcha already paid for

- **Corrected once already, worth stating as a standing rule:** don't scan only the modern SSP0/
  SSP1 blocks (`0x40088000`/`0x40030000`) and conclude "no SPI" if those come back empty — the
  LPC17xx also has a **legacy SPI0** block at `0x40020000`, and that's the one DJI actually used
  here (`id-entry-point.md`'s own correction, `ground-upgrade-path.md` Q2). Check both generations
  of the peripheral before ruling a bus absent.
- Otherwise same shape as STM32 step 7: literal-pool base loads rank peripheral usage; pins come
  out of the init-call arguments once the calling convention is known (`PINSEL0/1` register
  writes here, not `GPIO_PinAFConfig`).

## 8. Struct typing — not yet started

- No LPC-side equivalent of `fc_structs.py` exists yet. The config-page layout (step 6) and any
  DUML record structs decoded along the way (`c1_m1400.tsv`) are the natural first candidates
  once there's a Ghidra project to apply them in (step 3's gap).

## 9. Go deeper on demand

- Same pattern: pick an anchor (e.g. `iap_entry`, the DUML local-dispatch switch at `0x53c8`, the
  USB descriptor table once located), walk callers, record. `ground-upgrade-path.md`'s own Q1-Q5
  are exactly this, done via `mcu_trace.py` rather than Ghidra scripts — a fine substitute until
  step 3 is built, just without a decompiler's variable/type recovery.

## 10. Verify, tag, record

- Identical discipline to STM32 step 10: V needs a reproduction, cite exact offsets, log
  fact-changes in `HISTORY.md` as "initial -> corrected" (this doc's own step-5 USB finding was
  corrected once this session for exactly that reason — wrong firmware build grepped first).

## Per-module quick start

1. `grep -ri <module> docs/ docs/symbols/` (step 0) — confirm what's already vendored/known.
2. Confirm encrypt_type (likely 0, step 1); read SP/reset, compute the app's flash offset (2).
3. If a Ghidra project doesn't exist yet, start with `mcu_trace.py` (capstone) rather than
   blocking on step 3's SVD gap; upgrade to Ghidra once `lpc_setup.py` exists.
4. Check the vendored `.map`/`.idc` for LPCOpen/IAP names first (4) — likely already answers
   "what's the flash-driver library."
5. Port DJI-specific names via strings, including the UTF-16LE scan (5).
6. Chase the config-page/record layout if relevant (6); I/O inventory checking **both** SPI
   generations (7); struct typing once a project exists (8); targeted dives (9); record (10).
