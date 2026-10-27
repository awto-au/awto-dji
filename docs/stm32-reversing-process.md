# STM32 firmware reversing: the repeatable process

Checklist distilled from how m0306 (P3 flight controller, STM32F427) was reversed. Apply it to
the remaining modules (m0305 loader, m0400 gimbal, ESCs m11xx/m12xx, m0900, m0100 ...).
Tags: **V** verified, **I** inferred, **U** unknown. Fact-changes go in `docs/HISTORY.md`, not
inline. Doc index: `docs/README.md`.

## 0. Rule zero: cross-check prior art FIRST, at every step

We repeatedly re-derived things that were already named. Before each step below, look here:

- `docs/symbols/upstream/` (o-gs/dji-firmware-tools IAR `.map` files; `PROVENANCE.md` says
  which revision each covers, and `anchors_P3_V01.07.0060.tsv`). Addresses differ per revision,
  so match by name/structure, not address.
- `docs/prior-art.md` (what upstream already ships: `dji_xv4_fwcon.py`, `dji_flyc_param_ed.py`,
  `arm_bin2elf.py`; what is genuinely new here).
- Existing `docs/symbols/*.tsv` and docs (`fc-io-inventory.md`, `fc-bootloader.md`,
  `air-id-and-stream-survey.md`, `security-and-activation.md`). `grep -ri <thing> docs/` first.

## 1. Obtain and identify the module

- Container is xV4 (magic `0x12345678`, 0x34-byte entries from 0x40). List modules:
  `python3 scripts/re/xv4_extract.py CONTAINER.bin [OUTDIR [m0306 ...]]`.
  Module name = `m%02d%02d` of (target & 0x1f, target >> 5).
- Decrypt: `python3 scripts/re/xv4_decrypt.py CONTAINER.bin m0306 OUT.bin`. It reads
  `encrypt_type` from the entry (byte 1 high nibble); type 1 = AES-128-CBC, IV 0, cipher reset
  every 256 B; key is upstream's public module key.
- Verify: the script MD5-checks against `decrypted_md5` and aborts on mismatch. Never analyse
  an unverified blob.
- Gotchas: output is truncated to `decrypted_len` (stored length is block-padded); firmware is
  not in the repo (`HANDOVER.md`, `docs/data-manifest.md` for hashes); other encrypt types
  (e.g. SIMPLE=3) are not handled by this script; some modules (P3SE m0100) do not split.

## 2. Determine core and load base

- Read the first 8 bytes of the decrypted image (the decrypt script prints them): initial SP and
  reset vector. SP in `0x2000_0000..` + reset in `0x0802_xxxx` = STM32 app; SP `0x2002ff00` =
  192 KB SRAM class.
- Identify the family from the addresses: flash `0x08000000` + CCM `0x10000000` => STM32F4;
  flash `0x00400000` + SRAM `0x20400000` => Microchip SAM E70 (the P4 FC, **not** STM32; see
  `docs/prior-art.md`).
- Base is NOT always flash base. m0306 loads at `0x08020000` (low 128 KB is the resident loader,
  not in the OTA package; `docs/fc-bootloader.md`). Take base from reset vector alignment and
  confirm by checking that literal-pool pointers land inside the image.
- m0100 sys partition is a different animal: ARM Cortex-A9 (Ambarella), split with
  `amba_fwpak`, runtime base `0x0E600000`. Do not use the M-class recipe (no vector table).
- Gotcha: the m0305 updater shows a second slot (bank 2 `0x08100000`); a single image does not
  show A/B.

## 3. Load into Ghidra (headless) at the right base and processor

- Language ARM:LE:32:Cortex, raw binary, base address from step 2. Thumb mode: radare2 uses
  `-a arm -b 16 -m 0`.
- Run `scripts/re/ghidra/fc_setup.py` (Jython post-script): creates MMIO blocks for the
  peripheral ranges, applies CMSIS-SVD register labels and known names, re-exports functions.
  `fc_consolidate.py` creates SRAM/CCM blocks so RAM labels have somewhere to live and applies
  the whole TSV.
- Gotcha: no blocks => RAM/peripheral references show as unresolved constants and the
  decompiler loses types. Create blocks before any decompile pass.
- Gotcha: Ghidra scripts here are Jython, write output to a scratchpad dir, and are best kept
  bounded (see `fc_lib_id.py`: walk neighbours, decompile <=16 functions; full-image reference
  sweeps are slow).

## 4. Identify the register library (SPL vs HAL vs LL)

- By code structure, not strings. Anchor on `RCC_GetClocksFreq` (decodes `RCC_CFGR[SWS]`,
  PLL formula, AHB/APB prescaler table): `fc_lib_id.py` decompiles the cluster around it.
- Second independent probe via init path: `fc_lib_id2.py` decompiles callers of the RCC clock
  enable fn and the 2-arg helpers they use, to see the init-struct layout.
- Idioms: `RCC_xxxPeriphClockCmd(mask, NewState)` (2 args, bitmask + enable) + `GPIO_Init(port,
  &struct)` + `GPIO_PinAFConfig(port, pinsrc, af)` + `USART_Init` / `CAN_Init` struct fills =
  SPL. HAL has handle structs and `HAL_xxx_Init(&handle)`; LL is bare inline register ops.
- m0306 = ST StdPeriph (V). An earlier note said "raw DJI HAL"; see `docs/HISTORY.md`.
  Knowing the library lets you name ~all init functions and decode struct fields from the
  public headers.

## 5. String-anchored function naming

- DJI logs its own function names ("call api_ctrl_mode_..._handler", "[SDK] x"). Whatever
  references the string is almost always that function.
- Part A (no Ghidra): `python3 scripts/re/port_symbols.py UPSTREAM.map OUR_dec.bin > anchors.tsv`
  finds each upstream name as a substring of a C string in our image.
- Part B (Ghidra): `scripts/re/ghidra/fc_port_names.py` maps string vaddr -> referencing
  function -> applies the name. Confidence: log-style string with the code loading it inside
  the function = high; bare-name string in a `{fn_ptr, name_ptr}` table = medium (check
  neighbouring words for a thumb pointer).
- Also: `fc_autoname.py` (ISR names + unique-string functions), `fc_apimap.py` (command
  handlers from debug strings), `fc_curate.py` (revert weak names; keep only meaningful).
- Gotcha: only rename `FUN_*`, and only when exactly one function references the string.
  Names that are junk words (`unknown`, `start`, `send`) are worse than none.
- Record names incrementally in `docs/symbols/<module>.tsv` (`addr name note source`) and
  re-apply with `fc_consolidate.py`. The TSV is the source of truth, the Ghidra DB is not.

## 6. Parameter table extraction

- m0306 exports a `FlycExportParam` array (60 B/entry: name ptr, RAM value ptr, size, type id,
  36 B limits, attribute, callback). Dump: `python3 scripts/re/fc_param_table.py m0306_dec.bin
  [--defaults]` gives name -> RAM addr -> type -> size and, with `--defaults`, float
  min/max/default (834 params).
- Ghidra side: `fc_paramtab.py`, `fc_params_apply.py` label the RAM variables; results live in
  `docs/symbols/m0306-params.tsv`.
- Gotcha: the 36 B limit block is three parallel `{min,max,default}` views (float @+0x10, int32
  @+0x1c, uint32 @+0x28). Pick the view by type or you get garbage limits. Upstream's
  `dji_flyc_param_ed.py` does this too; ours only adds RAM-address cross-links.
- Callbacks give you the setter for each parameter: free named entry points.

## 7. I/O inventory

- Cheap, no Ghidra: `python3 scripts/re/fc_io_inventory.py m0306_dec.bin`. STM32 code reaches
  peripherals via literal-pool base loads (`ldr rN,[=BASE]`); counting pool words equal to
  each base address ranks usage (TIM2 63 refs = time-base, etc.). Role is **I**.
- Ghidra: `fc_io.py` (peripheral refs + config immediates), `fc_clk.py` (decompile RCC init
  writers; PLL words are runtime constants, read them from the constant loads feeding the
  writers).
- Pins/AF/baud come from the SPL callers: `fc_spl_callers.py` takes the identified
  `GPIO_Init`, `GPIO_PinAFConfig`, `USART_Init`, `CAN_Init` addresses, decompiles every caller,
  and the pin map falls out of the arguments (CAN1=PD0/PD1, CAN2=PB12/PB13, SDIO PC8-12/PD2 AF12,
  OTG_FS PA11/PA12 AF10).
- Gotcha: UART base is not in RAM; it is a flash lookup table (`USARTx[8]` @ `0x803bfd8`).
  Baud is usually a named parameter with a flash default (step 6), not an immediate. Anything the
  firmware computes at runtime stays **U** until traced.
- Results: `docs/fc-io-inventory.md`.

## 8. Struct typing

- Define the core structs once and apply them so members decompile as named fields:
  `scripts/re/ghidra/fc_structs.py` (category `/fc`), exported with `fc_structs_export.py`
  to `docs/symbols/m0306-structs.h`. Add `fc_proptypes.py`, `fc_tables.py` for table layouts.
- Start from upstream headers/structs (step 0) and SPL init structs (step 4), then extend from
  decompiled field offsets. Re-decompile callers afterwards to propagate names.
- Gotcha: wrong struct size silently shifts every later field. Check against an array stride
  (param entry = 60 B) before applying.

## 9. Go deeper on demand

Targeted decompile-and-dump scripts are the pattern: pick an anchor, walk callers, dump C to
scratchpad, read it, record. Examples: `fc_dispatch.py` (DUML RX dispatcher via `duml_crc16`
callers), `fc_ctrlmode.py`/`fc_gate.py` (control authority), `fc_loader_reads.py` (UID/loader
handoff), `m0305_*.py` (loader/flash), `m0100_mac.py` (A9 MAC functions, base `0x0E600000`).
Use `docs/symbols/air_modules.tsv`-style TSVs for other modules.

## 10. Verify, tag, record

- Tag every claim **V / I / U**. V needs a reproduction (script + offset/address). Do not state
  inference as proof (e.g. MCU-layer cleartext is V; over-the-air encryption is not ruled out).
- Cite exact offsets and commands in the doc so the claim can be re-derived.
- When a finding overturns an earlier one, write the correction as "initial -> corrected" in
  `docs/HISTORY.md` and keep the doc stating only the current fact.
- Add new docs to `docs/README.md`; add vendored upstream material to
  `docs/symbols/upstream/PROVENANCE.md` with licence note (GPL-3.0).

## Per-module quick start

1. `grep -ri <module> docs/ docs/symbols/` (step 0).
2. Extract + decrypt + MD5 (1). Read SP/reset, pick base and core (2).
3. Ghidra load, `fc_setup.py`-style setup (3). Library ID (4).
4. Port upstream names via strings (5). Params (6) if the module has a table.
5. I/O inventory (7), structs (8), then targeted dives (9). Record as you go (10).
