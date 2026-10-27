# m0900 (`air_router_stm32f103`) completeness pass: I/O inventory, upstream symbol port, Ghidra project, struct typing

Completeness follow-up to `docs/air-router-deep-dive.md` (read first; not restated here except
where corrected/extended). Covers the four things that doc explicitly skipped: (1) systematic
upstream-map port, (2) full I/O inventory, (3) a Ghidra project, (4) struct/global typing — plus
an attempt at the remaining unnamed handlers.

Source: `P3X_FW_V01.11.0020_m0900.bin`, SHA-256
`72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d` — **verified** against
`docs/data-manifest.md` before use. App base `0x08008000`. Tools: `scripts/re/m0900_trace.py`
(capstone), two new one-off scripts written for this pass (xref finder + peripheral-base
ranking, listed under "Reproduce"), and a new Ghidra 11.4 headless project (see §3).

Tags: **V** verified (reproducible from an address/script cited), **I** inferred, **U** unknown.

## 0. Headline results

1. **Upstream-map string-anchor port (`port_symbols.py`) finds zero matches for m0900** — not a
   bug, a real negative result: `strings -n5` on the image shows only a handful of `printf`
   *format* strings (`"Ver: %d"`, `"Fpga Boot : %d"`, `"Error: ad9363 reg17 - %.2X"`, etc.), no
   DJI-style self-naming log strings (`"call <funcname>"`) the way `m0306`'s anchor port relies
   on. §1 below.
2. **The upstream map ports cleanly anyway, by direct correspondence**, because its function
   names literally encode the `(set,cmd)` DUML key (`cmd_exec_set09_cmd0E`, `cmd_exec_set06_cmd1B`,
   `cmd_exec_set00_cmdFE`, ...) which we already have from the fully-walked dispatch table —
   **13 of the 23 "unnamed/unknown" rows in `air-router-deep-dive.md` §1b/§1a now have their
   canonical DJI name**, including all of cmd `0x0e`/`0x0f`/`0xfe` and the `0xff` catchall named
   in the task (§2).
3. **cmd `0x0c` GetDeviceStatus, decompiled fully**: board-dependent status word is
   `*(u32 *)0x080125e8` (new RAM/flash global, not yet further identified) for AD9363 boards
   (4/5), else `0`. §2.4.
4. **cmd `0xfe` (`cmd_exec_set00_cmdFE`) — resolved fully in a follow-up pass, and it's more
   significant than first described**: mode 1 writes host-supplied payload bytes directly into
   the live `radio_state_s` struct, then reloads the FPGA config from that struct and re-runs
   the radio's full bring-up sequence (`radio_first_init`) — an engineering-style "push raw
   radio state and force reload" command, not a simple status query; mode 2 silently writes one
   host byte into `radio_state_s+0x11c` with no reply. No auth/validation gate found on either
   mode. §2.4.
5. **cmd `0xff` catchall, decompiled fully**: for receiver type `0x13` (FPGA) it is a literal
   hardcoded-string reply, `"WM32X A4_FPGA 20150902|01"` (26 B) — the same string the upstream
   map names `aWm32xA4Fpga201`, confirming the string is unchanged across firmware revisions;
   for type 9 it tail-calls `FUN_080126f8` (not traced). So `0xff` is a version/ID query, not a
   true no-op catchall. §2.4.
6. **I/O inventory**: `GPIOA`/`GPIOB`/`GPIOC` are the only GPIO banks with real (non-table)
   usage; **two new pins identified** beyond the ones `air-router-deep-dive.md` already found
   (GPIOB bit4, PA0/PC15/PC14 straps): **PA4** and **PB3+PB6** configured as outputs, and a
   **PA1 pulse strobe** gated by a fail-counter in RAM — candidate role: antenna/quadrant
   switch, matching the upstream map's otherwise-unexplained `switch_active_quadrant` function
   and `active_quadrant_*`/`quadrant_*` RAM variables sitting immediately next to our own
   `0x200000c8` IWDG-stop flag. §4.
7. **Ghidra project built**: `ghproj/m0900` in the analysis scratchpad, `ARM:LE:32:Cortex`, raw
   import at `0x08008000`, 426 functions after analysis, 107 of them carrying a USER_DEFINED
   name (ported from the tsv + this pass's 23 new names), plus two typed RAM structs applied.
   §3.
8. **One upstream anchor does NOT reconcile and is reported as such, not forced**: `cmd_exec_
   flyc_unlimit_state`, positionally the third of three upstream names before the `cmd0E`/`cmd0F`
   block, does not fit cmd `0x42`'s actual behavior (a pure fan-out rewrite to receiver type 4 —
   gimbal — nothing resembling a "unlimit state" semantic, and no FLYC/cmdset-3 payload
   handling at all). §2.3.

## 1. Why the string-anchor port script found nothing (for the record)

```
python3 scripts/re/port_symbols.py docs/symbols/upstream/P3X_FW_V01.07.0060_m0900_air-radio.map \
    firmware/P3X_FW_V01.11.0020_m0900.bin
# -> candidates=71  anchored=0
```
`m0900` is confirmed **not** AES-wrapped (per `docs/code-provenance.md`, used as-is) so that
precondition for the script holds — the zero-match result is about the *content*, not a
decrypt-order mistake. `strings -n5` on the raw image turns up only `printf`-style format
strings (`"Ver: %d"`, `"Fpga Boot : %d"`, `"Fpga Cfg : OK"`, `"Fpga Cfg : Error"`,
`"Error: ad9363 reg17 - %.2X"`, `"Error: ar8003 reg7C - %.2X"`, `" ID: %.2X ..."`,
`"set alter:%d"`, `"WM32X A4_FPGA 20150902|01"`), never the `"call <funcname>"`-shaped debug
strings that make the anchor method work for `m0306`. **V** (reproducible: `strings -n5
firmware/P3X_FW_V01.11.0020_m0900.bin`). This firmware line's release build strips function-name
logging entirely (or never had it) — `m0900` needs a different porting method, which turned out
to already be available: direct correspondence (§2).

## 2. Upstream symbol port — by direct (set,cmd)-encoded naming + positional correspondence

### 2.1 Method

The upstream map (`P3X_FW_V01.07.0060_m0900_air-radio.map`, 125 lines) lists DJI's own linker
symbols for an earlier (`V01.07.0060`) build of the same source. Its `cmd_exec_set<SS>_cmd<CC>`
names **encode the exact DUML `(set,cmd)` key** these handlers are keyed on — a key
`air-router-deep-dive.md` §1 already recovered byte-for-byte by walking our (`V01.11.0020`)
dispatch table. So instead of string-anchoring, each upstream name was matched to our table by
**(set,cmd) value**, not by address or position — the strongest possible anchor, independent of
how much the two builds' code has moved:

| upstream name | (set,cmd) it encodes | our handler (from the walked table) | match |
|---|---|---|---|
| `cmd_exec_set09_cmd0E` | set 0x09, cmd 0x0E | `0x0801205a` (GPIOB bit4 setter) | **V** — key matches exactly |
| `cmd_exec_set09_cmd0F` | set 0x09, cmd 0x0F | `0x08012086` (GPIOB bit4 readback) | **V** |
| `cmd_exec_set09_cmd04` | set 0x09, cmd 0x04 | `0x080120e2` (SetFPGA) | **V** |
| `cmd_exec_set09_cmd05` | set 0x09, cmd 0x05 | `0x08012102` (GetFPGA, already named) | **V** |
| `cmd_exec_set09_cmd06` | set 0x09, cmd 0x06 | `0x08012122` (Set9363, already named) | **V** |
| `cmd_exec_set09_cmd07` | set 0x09, cmd 0x07 | `0x0801216a` (Get9363, already named) | **V** |
| `cmd_exec_set09_cmd12` | set 0x09, cmd 0x12 | `0x080121b4` (radio SET, already named) | **V** |
| `cmd_exec_set09_cmd13` | set 0x09, cmd 0x13 | `0x08012210` (radio GET, already named) | **V** |
| `cmd_exec_set00_cmd07` | set 0x00, cmd 0x07 | `0x08012320` (Enter Loader, already named `duml_enter_loader`) | **V** |
| `cmd_exec_set00_cmd08` | set 0x00, cmd 0x08 | `0x080123b8` (Update Confirm, already named) | **V** |
| `cmd_exec_set00_cmd0A` | set 0x00, cmd 0x0A | `0x080123e6` (Update Finish, already named) | **V** |
| `cmd_exec_set00_cmd0B` | set 0x00, cmd 0x0B | `0x08012428` (Reboot Chip, already named) | **V** |
| `cmd_exec_set00_cmd0C` | set 0x00, cmd 0x0C | `0x08012458` (GetDeviceStatus) | **V** |
| `cmd_exec_set00_cmd0D` | set 0x00, cmd 0x0D | `0x080124bc` (Set Device Version) | **V** |
| `cmd_exec_set06_cmd1B` | set 0x06, cmd 0x1B | `0x080124f0` (GetPushGpsInfo) | **V** |
| `cmd_exec_set00_cmdFF` | set 0x00, cmd 0xFF | `0x0801253a` (the "catchall") | **V** — see §2.4 for what it actually does |
| `cmd_exec_set00_cmdFE` | set 0x00, cmd 0xFE | `0x08012592` | **V** — see §2.4 |

17 handlers confirmed this way (two, `cmd0D`/`set06cmd1B`, were previously tagged "V" only via
the table walk with no name; they now have their DJI name too). This is the bulk of the
"systematic port"; the remaining upstream names needed position, not key-matching (§2.2/§2.3).

### 2.2 Positional correspondence for the inner (`0x0901..0x0914`) sub-table

Upstream names `cmd_exec_set00_cmd01a` / `cmd_exec_set00_cmd01b` sit immediately before the
`cmd04..cmd13` block in the upstream map, suggesting two *separate* functions per receiver type
(9 vs 0x13) for DUML `set 0x00 cmd 0x01` in `V01.07.0060`. Our `V01.11.0020` dispatch table has
**one** handler, `cmd_exec_set09_default` (`0x0801226e`), serving *both* keys (type 9 and type
0x13 share a handler — confirmed again by decompile, §2.4's last listing: it branches
internally on `*(byte*)(param1+5)&0x1f`). **Does not reconcile 1:1 — flagged, not forced.**
Between `V01.07.0060` and `V01.11.0020` DJI merged the two type-specific `cmd 0x01` handlers
into one. **V** (decompiled; the branch is explicit).

### 2.3 Positional correspondence for the `0x42`/`0x43`/`0x44` family — one does NOT reconcile

The upstream map lists three names in address order right before the `cmd0E` block:
`cmd_exec_osd_general`, `cmd_exec_osd_home`, `cmd_exec_flyc_unlimit_state`. Our dispatch table
(ascending handler address) has exactly three siblings in the same slot: `0x08011ed4` (cmd
`0x43`), `0x08011f98` (cmd `0x44`), `0x08012012` (cmd `0x42`).

- **Structural match confirmed by decompile**: `0x08011f98` (decompiled this pass) does the
  identical pattern `air-router-deep-dive.md` already described for `0x08011ed4` — rewrite
  receiver-type byte to 2, CRC-fix, `can414_send`, then rewrite to 1, CRC-fix, `can414_send`
  again (a two-step type-2-then-type-1 fan-out). Both are genuinely "OSD"-family twins, which
  **is** consistent with `cmd_exec_osd_general`/`cmd_exec_osd_home` being two near-identical
  sibling functions. **But which upstream name belongs to which of `0x08011ed4`/`0x08011f98` is
  not disambiguated by this evidence — reported as (V the family match, U the individual
  name↔address assignment)**, rather than guessing.
- **`cmd_exec_flyc_unlimit_state` does NOT reconcile with `0x08012012` (cmd `0x42`)**:
  `0x08012012` (decompiled this pass) is a single flat rewrite-and-forward — receiver type set
  to `4` (gimbal), CRC-fix, one `can414_send` — no FLYC/cmdset-3 payload interpretation, no
  "unlimit state" semantics visible anywhere in the function body. This is exactly the
  structural mismatch the task asked to report rather than force. **Open**: either the upstream
  name is positionally misattributed in this 3-name block relative to our table, or DJI
  repurposed this slot between firmware revisions. Not resolved this pass.

### 2.4 Full decompiled text for the previously-unnamed/partial handlers (task item 5)

From the new Ghidra project (§3), decompiled in full (60s timeout each, no truncation):

**`cmd_exec_set00_cmdFE` (`0x08012592`, cmd `0xfe`)** — fully resolved, both structurally and
semantically, in a follow-up pass (2026-10-25). **This is not a minor status command — it's a
direct write into the live `radio_state_s` struct that forces an FPGA reconfigure and a full
radio re-init, outside the normal `0x0901`/`0x0902` Get/Set-Config and `0x12`/`0x13`
start/stop commands.**

- `0x080010af4` is not an uncatalogued global — it's a **pointer variable whose value is
  `0x20001ab4`, the exact base address of the already-typed `radio_state_s` struct**
  (confirmed: `mem.getInt` on `0x08010af4` reads `0x20001ab4` directly). Every write through
  it in both modes below lands inside the live radio-state struct this project already types.
- **Mode 1** (`FUN_080109a4`, fully decompiled):
  ```c
  void FUN_080109a4(undefined4 *payload)
  {
    radio_state_s *rs = (radio_state_s*)0x20001ab4;   // = DAT_08010af4's value
    *(uint32*)rs       = payload[0];                  // first word of the struct <- host payload
    *(uint8*)((int)rs+4) = *(uint8*)((int)payload+4);  // + one more host byte
    FUN_08010286();            // if rs->first_init_flag (+0x109) != 0: run FUN_0800baf4(), then clear it
    *(uint32*)((int)rs+5) = *(uint32*)((int)rs+1);     // internal copy, unaligned
    fpga_cfg_load(rs);         // reload FPGA config FROM the struct just overwritten
    FUN_0800e820();            // board-dependent calibration/atten lookup, writes rs+0x80-ish
    radio_first_init();        // re-run the radio bring-up sequence
  }
  ```
  So mode 1 takes host-supplied bytes, pokes them into the start of `radio_state_s`, conditionally
  re-runs the one-shot first-init step (`FUN_08010286` gates on the `first_init_flag` at `+0x109`,
  the same field the typed struct already names), reloads the FPGA from the now-modified struct,
  and finally calls `radio_first_init()` again — i.e. **forces the radio through its full
  bring-up sequence a second time with host-injected state**. The 1-byte reply only fires for
  receiver-index 1/2. **V** (fully decompiled, every callee resolved).
- **Mode 2** (already known, re-confirmed with the corrected base): silently writes one
  host-supplied byte to `radio_state_s + 0x11c` — inside the struct's `pad_11c` gap, immediately
  before the `0x0913`-written fields at `+0x128`/`+0x12a`/`+0x12c` — **no reply at all**.
- **I**: this reads as an engineering/bring-up command — "push raw radio state and force a
  reload" — rather than anything a normal flight session would send (normal operation goes
  through the documented Get/Set Config and radio start/stop commands, which validate and
  CRC-round-trip through flash page `0x7b00`; this command writes straight to the live struct
  with no flash round-trip and no payload validation visible in either mode). Not proven to be
  DJI-factory-only — no gating/auth check of any kind was found before either write — just
  structurally distinct from every other named command in the table.
- **U, still open**: `FUN_08010286`'s callee `FUN_0800baf4` (the actual first-init body) and
  `FUN_0800e820`'s calibration-table semantics were read (see `scratchpad/m0900_followup5_dump.txt`)
  but not fully traced to a board-level meaning; `radio_first_init`'s own body (pre-existing name,
  not re-decompiled this pass).
- Reproduce: `scratchpad/ghscripts/m0900_followup.py`/`_2.py`/`_3.py` (ad hoc, not committed) —
  read the pointer value at `0x08010af4`, decompiled `FUN_080109a4`/`FUN_08010286`/`FUN_0800e820`.

**`cmd_exec_set00_cmdFF` / "catchall" (`0x0801253a`, cmd `0xff`)** — resolved, and it is not a
no-op:
```c
void cmd_exec_set09_catchall(int param_1)
{
  if (receiver_type == 9)      FUN_080126f8(payload);
  else if (receiver_type == 0x13)
      FUN_080128aa(payload, "WM32X A4_FPGA 20150902|01", 0x1a);   // literal 26-byte string
  len = FUN_0801286c(payload) + 1; if (len > 0x20) len = 0x20;
  if (receiver-index bits 5-6 in {1,2})
      packet_make_response(..., payload, len);
}
```
For the FPGA receiver (`0x13`) this hands back a **hardcoded firmware-ID string**,
`"WM32X A4_FPGA 20150902|01"` — the same string the upstream map's `.rodata` symbol table names
`aWm32xA4Fpga201` at its own `0x08013160`, i.e. this literal is unchanged from `V01.07.0060` to
`V01.11.0020`, 4+ years apart (the `20150902` date is a build/format stamp baked at an earlier
point, not re-stamped per release). For receiver type 9 it tail-calls `FUN_080126f8`, not traced
this pass. **V**: this is effectively "Get Board/Firmware ID" for the FPGA-side query, not an
inert catchall. **U**: `FUN_080126f8`'s (type-9) behaviour.

**`cmd_exec_set00_cmd0C` / GetDeviceStatus (`0x08012458`)** — fully resolved:
```c
void cmd_exec_set00_cmd0C_getdevicestatus(uint *param_1)
{
  status_byte = 0; status_u32 = 0;
  type = receiver_type;
  if (type == 9) { status_u32 = 0; }
  else if (type == 0x13) {
      if (board in {4,5}) status_u32 = *(u32 *)0x080125e8;    // AD9363 boards: real value
      else if (board in {6,7,2}) status_u32 = 0;
      else /* goto reply without writing status_u32 at all */ ;
  } else /* goto reply without writing status_u32 */ ;
  // builds + sends the reply packet (gated on the usual index-bits-5/6 check)
}
```
**Resolved in the follow-up pass (2026-10-25):** `0x080125e8` is a pointer variable, not a
direct status word — its value is `0x200000fc`, a RAM address. That address is read/written
**exclusively** inside `fpga_boot_status` (pre-existing name, `0x0800cfd0`) — the known FPGA
bring-up handshake state machine already referenced in `fpga-bringup.md` — and nowhere else (4
refs total, all inside that one function). So for AD9363 boards (4/5), GetDeviceStatus is
literally reporting the **live FPGA bring-up handshake status code** `fpga_boot_status` last
wrote, not an opaque flash constant. **V** (pointer value read directly, confirmed single-writer
by reference count).

Also resolved: cmd `0xff`'s receiver-type-9 reply (`FUN_080126f8`) copies a **fixed 32-byte RAM
blob** at `0x20004fc0-0x20004fe0` into the response — not a hardcoded string like the type-0x13
case. The end-pointer (`0x080127d0` → `0x20004fe0`) is read in two places and **written nowhere**
in the application code traced, meaning that 32-byte region is populated by the C-runtime
`.data` initializer at boot (copied from flash), not computed at runtime. **U**: the blob's
actual content/meaning — would need the flash `.data`-table entry for this RAM range, not
chased this pass.

**`duml_set03_id42_fwd` (`0x08012012`, cmd `0x42`)** and **`cmd_exec_osd_home_candidate`
(`0x08011f98`, cmd `0x44`)** — decompiled text supporting §2.3's non-reconciliation, included
there.

## 3. Ghidra project

Built this pass — **none existed for m0900 before** (`air-router-deep-dive.md`'s own "Method
note" confirms this).

- **Location**: `ghproj/m0900` under the analysis-environment scratchpad (the task's designated
  scratchpad, not the repo — matches `stm32-reversing-process.md` step 3's convention).
- **Import**: `analyzeHeadless ./ghproj m0900 -import firmware/P3X_FW_V01.11.0020_m0900.bin
  -loader BinaryLoader -loader-baseAddr 0x08008000 -processor ARM:LE:32:Cortex`. Auto-analysis
  ran clean (two benign "pcode error, unable to resolve constructor" warnings at `0x08014f40`/
  `0x080143a0`, inside data tables the disassembler mis-swept as code — matches the known
  "densely packed handler region decodes out of phase" issue `air-router-deep-dive.md`'s Method
  note already flagged for the capstone tool; harmless for everything named here, all of which
  resolved through table reads or direct branches, not that region).
- **No CMSIS-SVD applied**: only an **STM32F427** SVD is present in the scratchpad (for `m0306`,
  a different chip); no STM32F103 SVD was available, so MMIO register names were *not* applied
  via SVD — the peripheral base **addresses** used for naming/labeling throughout this doc come
  from the reference manual's numeric map (RM0008, hand-entered in the inventory script, §4),
  not from an imported SVD. **Noted as open**: importing a real F103 SVD if one turns up would
  let Ghidra auto-label every MMIO register bitfield, not just the bases.
- **Applied**: 107 function names (84 from the pre-existing symbol tsv + upstream names already
  known by address, 23 new from this pass, §2/§4), two new structure data types
  (`radio_cfg_page_s`, `radio_state_s` — §5) placed at their RAM addresses, and 4 RAM labels.
  426 functions total after analysis (most still auto-named `FUN_*`/`LAB_*` — far more remain
  to be identified in a future pass; this one focused on the task's specific open items).
- Used for: the full-text decompiles in §2.4 (the capstone tool can print disassembly but not
  decompiled C — these needed the decompiler to resolve the branch structure of `cmdFE`/
  `cmdFF`/`cmd0C` reliably), and for building/checking the struct placements in §5.

## 4. Full I/O inventory

### 4.1 Peripheral usage ranking

Literal-pool peripheral-base-reference count (mirrors `fc_io_inventory.py`'s method, adapted to
the STM32F103 (RM0008) memory map — script in "Reproduce"):

| Peripheral | Base | pool-word refs | Note |
|---|---|---:|---|
| GPIOA | 0x40010800 | 9 (+7 more via xref sweep, §4.2) | heaviest-used bank |
| GPIOB | 0x40010c00 | 7 (+3 more via xref sweep) | second-heaviest |
| GPIOC | 0x40011000 | 4 (+1 more via xref sweep) | lighter |
| TIM3 | 0x40000400 | 3 | — |
| USART2 | 0x40004400 | 3 | board-7-only aux UART (known) |
| TIM1 | 0x40012c00 | 3 (11 fn-level xrefs — see note) | — |
| FLASH_IF | 0x40022000 | 3 (27 fn-level xrefs) | flash unlock/program (0x7400/0x7800/0x7b00 pages, known) |
| TIM4/5 | 0x40000800/0xc00 | 2 each | — |
| USART3 | 0x40004800 | 2 | FPGA UART (known) |
| CAN1 | 0x40006400 | 2 (5 fn-level xrefs) | primary inter-MCU bus (known) |
| AFIO | 0x40010000 | 2 | pin remap |
| ADC1 | 0x40012400 | 2 | — |
| TIM8 | 0x40013400 | 2 | — |
| USART1 | 0x40013800 | 2 | FC UART (known) |
| RCC | 0x40021000 | 2 (27 fn-level xrefs) | clock enable (known, `set_sysclk`) |
| TIM2/6/7, IWDG, SPI2/3, UART4/5, EXTI, GPIOD-G, ADC2/3, SPI1 | various | 1 each | **table entries only** (see below) — not independently driven |

**Method caveat (why some counts look higher below than above):** a flat word-scan over the
whole image (the table above) undercounts real usage, because many "1-ref" peripherals
(TIM3/4/5/6/7/8, UART4/5, GPIOD-G, SPI1/3, ADC2/3) appear **only inside small static lookup
tables** — contiguous runs of base words at `0x08009ff4..0x800a00c` (TIM1/3/4/5/6/7/8),
`0x08009670..0x8009688` (GPIOA-G), `0x08009c00..0x8009c08` (SPI1/2/3), `0x0800aa18..0xaa28`
(USART1-5), `0x08008608..0x8008610` (ADC1-3) — a DJI/StdPeriph-style generic "peripheral-N →
base" array, not individual driver call sites, exactly the pattern `fc-io-inventory.md` flags
for the FC's own `USARTx[8]` table. A second pass with a proper code-sweep xref finder (not just
a flat word scan — script in "Reproduce") gives the *real* per-function usage, reproduced below
for GPIOA/B/C, TIM1/CAN1/FLASH_IF/RCC: 16/10/5/11/5/27/27 distinct instruction sites
respectively. **V** (both counting methods are reproducible scripts, cited).

### 4.2 GPIO pin map — extends `air-router-deep-dive.md`'s GPIOB-bit4 / strap-pin findings

Already known (not re-derived, from `air-router-deep-dive.md` and `fpga-bringup.md`): GPIOB ODR
bit4 (`0x40010c0c`, DUML cmd `0x0e`/`0x0f`), board-strap pins **PA0/PC15/PC14**
(`board_straps_read`, `0x0800c0bc`), **PB3** FPGA-reset (`fpga_gpio_init`/`fpga_reset_pulse`,
`0x0800ce14`/`0x0800ce48`), **PA13** (set low at boot, same function), SPI2 on **PB12**(CS)/
**PB13/14/15** (`spi2_init`, `0x0800b536`), CAN1 on **PA11(RX)/PA12(TX)** (`can_init`,
`0x0800b31c`), USART1/3 generic bring-up (`uart_init`, `0x0800aca0`).

**New this pass** (xref-traced from the real literal-pool loads, GPIO_Init-style wrapper calls
through `FUN_080094e2`, pin-mask byte confirmed by decompile at the struct's `+3` offset):

| Function | Addr | Pin(s) | Config | Role (I unless noted) |
|---|---|---|---|---|
| `gpiob_pb4_config` | `0x0800b70c` | **PB4** | output, pin-mask `0x10` | config counterpart of the already-known DUML cmd `0x0e`/`0x0f` GPIOB-bit4 toggle/readback — this is the `GPIO_Init` call that sets PB4 up as an output in the first place, not the runtime toggle itself. **V** the pin; **I** the purpose (same hypothesis space as before — the upstream map's RAM cluster `active_quadrant_*`/`quadrant_*` right next to our own `0x200000c8` flag, §4.3, is a *stronger* candidate than the earlier "FPGA-bypass select" guess, but still not confirmed) |
| `gpioa_pa4_config` | `0x0800b79c` | **PA4** | output, pin-mask `0x10`, mode byte `2` (differs from PB4's mode byte `3`) | new pin, role **U** — not tied to any named command path by this pass |
| `gpiob_pb3_pb6_config` | `0x0800ba78` | **PB3 + PB6** | output, pin-mask `0x48` (bits 3,6) | configures PB3 (already known FPGA-reset pin) together with the **new** PB6 in one call — alternate/board-dependent init path alongside the separate single-pin PB3 setup in `fpga_gpio_init`; **I** which board selects this path (no board-version branch inside this function itself, unlike the next two) |
| `gpioa_crh_board_cfg_a` / `_b` | `0x0800b60c` / `0x0800b6ac` | **PA pins 8-15** (GPIOA CRH, i.e. the high byte-lane) | board-version-gated (`get_board_version() ∈ {4,5}` vs `{6,2}` vs `7`, mirroring the AD9363-vs-Artosyn board split `fpga-bringup.md`/`phy-params.md` already established) | board-dependent high-pin-group GPIOA config — **I** exact pin(s); consistent with (not newly proving) the existing board-split model |
| `pa1_pulse_strobe` | `0x0800b7cc` | **PA1** | ODR bit1 pulsed low (~10 delay units) then high (~500 units), gated on a RAM counter `[0x200000a4+4] >= 0x4b` (75), and the counter is zeroed again after the pulse fires | **V** structure (fully decompiled, §2.4-style); **I** role — candidate: antenna/quadrant-switch relay or a secondary reset, given the upstream map's otherwise-unused `switch_active_quadrant` function name and RAM vars `active_quadrant_state`/`quadrant_state`/`active_quadrant_num`/`quadrant_num` at `0x200000C4-C7` sitting immediately before our own known `0x200000c8` IWDG-stop flag (§4.3) — **not proven**, the counter-threshold-of-75 trigger condition itself is not yet traced to a caller |
| `rcc_apb2_enable_by_gpio_port` (`0x08009436`) / `_b` (`0x0800c054`) | — | — | generic "enable AHB2/APB2 clock bit for whichever of GPIOA/B/C this port-base equals" dispatcher, called by several of the above | confirms a **DJI-style generic GPIO-port→RCC-bit mapper** exists (bit `0x4`=GPIOA, `0x8`=GPIOB, `0x10`=GPIOC — exactly `RCC_APB2ENR`'s `IOPAEN`/`IOPBEN`/`IOPCEN` bit positions), i.e. the same kind of index-driven generic driver layer `fc-io-inventory.md` found for the FC's `USARTx[8]` table, now confirmed on the air-router side too |

### 4.3 RAM layout cross-check against the upstream map (new corroboration)

The upstream `V01.07.0060` map's RAM symbol table (`0005:` segment, its `.bss`) gives:
`active_quadrant_state`/`quadrant_state`/`active_quadrant_num`/`quadrant_num` at
`0x200000C4-C7`, `ofdm_board_version_flags` at `0x200000D8`. **`0x200000D8` is the exact same
address** our own tsv already names `board_version` (from `air-router-deep-dive.md`'s prior
work) — a direct, address-exact cross-check (not an inference): same RAM offset, same meaning,
two different firmware builds. **V.** The quadrant-state cluster sits in the 4 bytes immediately
before our own already-known `0x200000c8` ("stop feeding IWDG" flag) — i.e. this whole RAM
region's layout is stable across `V01.07.0060`→`V01.11.0020`, which is what makes the
`pa1_pulse_strobe`/`switch_active_quadrant` connection above a *reasonable* inference rather than
a stretch, even though it isn't proven. **I** for the connection; **V** for the address-exact
`board_version` match and the layout stability it implies.

## 5. Struct/global typing

Applied to the Ghidra project (§3) as real `Structure` data types, not just offset comments:

### `radio_cfg_page_s` (0x200019b8, 252 bytes)
The DUML `0x0901`/`0x0902` (get/set config) round-trip target, persisted to flash page `0x7b00`
(`air-router-deep-dive.md` §1a). **New this pass**: `0x20001ab4` (`radio_state_S`) minus
`0x200019b8` = **exactly 0xFC (252)** — i.e. this struct's 252 bytes sit **immediately
contiguous** with the start of `radio_state_s` in RAM; the persisted config page is not a
separate region, it is laid out directly before the live radio state struct. **V** (address
arithmetic, both addresses independently established in `air-router-deep-dive.md`). Left as an
opaque 252-byte blob (its field layout is not recovered — would need tracing every one of
`0x0913`'s multi-field writer uses against this exact struct, not attempted this pass).

### `radio_state_s` (0x20001ab4), typed from the tsv's existing offset notes
```c
struct radio_state_s {
    char   pad_0[0xc];
    uint32 cfg_word;        // +0x0c: bit21 fixed-ch flag, bits 7-11/18-20/27-29 fields, bit31 atten-select
    char   pad_10[0x84-0x10];
    uint32 channel_index;   // +0x84
    uint32 channel_count;   // +0x88
    char   pad_8c[0x94-0x8c];
    float  channel_mhz;     // +0x94
    char   pad_98[0x109-0x98];
    uint8  first_init_flag; // +0x109
    char   pad_10a[0x119-0x10a];
    uint8  active_flag;     // +0x119
    uint8  started_flag;    // +0x11a
    uint8  tx_atten_idx;    // +0x11b: written to AD9363 0x073/0x075 via tcx_config_update1
    char   pad_11c[0x128-0x11c];
    uint32 field_128_cmd0913; // +0x128
    uint32 field_12a_cmd0913; // +0x12a (unaligned — matches the firmware's own byte-packed access)
    uint32 field_12c_cmd0913; // +0x12c
};  // sizeof == 0x130
```
All offsets **V**, sourced directly from `docs/symbols/m0900_V01.11.0020.tsv`'s existing
`radio_cfg_word` row and `air-router-deep-dive.md`'s `0x0913` field trace — this pass's
contribution is making it a real typed `Structure` in the Ghidra project (so decompiled call
sites read `radio_state->tx_atten_idx` instead of `*(byte*)(s+0x11b)`) and placing it at its RAM
address, plus the `radio_cfg_page_s` discovery above. The gaps (`pad_*`) are genuinely unknown
fields, not laziness — no further bytes in this struct were traced to a specific use this pass.

### RAM labels applied
`0x200000d4` → `gpiob4_state_cache` (existing finding, now a named symbol in the project);
`0x200000c8` → `iwdg_stop_feed_flag` (existing); `0x200000d8` → `board_version` (existing,
cross-checked §4.3); `0x200000a4` → `pa1_pulse_table_ptr_or_idx` (new, gates `pa1_pulse_strobe`,
§4.2 — name reflects that its exact role, counter vs pointer, is still **U**).

## 6. What stayed open despite the attempt

- **Resolved in the 2026-10-25 follow-up** (previously listed here as open): `FUN_080109a4`
  (cmdFE mode-1 callee — turned out to be a direct `radio_state_s` write + FPGA reload + radio
  re-init, §2.4), `FUN_080126f8` (cmdFF type-9 callee — a fixed 32-byte RAM blob copy, content
  still unidentified), and the global at `0x080125e8` (resolved as a pointer to `fpga_boot_status`'s
  own state variable, §2.4).
- Still open from that same follow-up: `FUN_0800baf4` (the real first-init body gated by
  `radio_state_s->first_init_flag`), `FUN_0800e820`'s calibration-table semantics, and the
  content of the 32-byte RAM blob at `0x20004fc0` (would need the flash `.data`-init table, not
  chased).
- The `0x42`/`0x43`/`0x44` individual name↔address assignment within the "OSD family" trio
  (§2.3) — structurally confirmed as a family, not individually disambiguated.
- `cmd_exec_flyc_unlimit_state` has no reconciling address in our table at all (§2.3) — reported
  per the task's instruction not to force it, rather than mis-assigned to `0x42`.
- PA4's role (§4.2) and the exact board/path selector for `gpiob_pb3_pb6_config` vs the
  single-pin `fpga_gpio_init` PB3 setup — new pins found, not yet explained.
- `pa1_pulse_strobe`'s trigger: what sets the `[0x200000a4+4] >= 0x4b` condition, and who calls
  the function at all (no caller found in this pass — same "no direct BL caller, may be
  table/tail-called" situation `air-router-deep-dive.md` flagged for `tcx_tune_caller`).
- No STM32F103 CMSIS-SVD was available in the environment to auto-label MMIO bitfields in the
  Ghidra project (§3) — peripheral bases are hand-labeled from RM0008, not SVD-sourced.

## Reproduce

- Firmware: copy to `firmware/P3X_FW_V01.11.0020_m0900.bin` (gitignored; hash must match
  `data-manifest.md`).
- Upstream port attempt (negative result, §1): `python3 scripts/re/port_symbols.py
  docs/symbols/upstream/P3X_FW_V01.07.0060_m0900_air-radio.map
  firmware/P3X_FW_V01.11.0020_m0900.bin`
- Peripheral base ranking (§4.1, flat scan): a ~50-line script enumerating the RM0008 base
  table and counting literal-pool word matches — same method as `scripts/re/fc_io_inventory.py`,
  adapted to F103 bases (not committed as a repo script this pass; the base table is reproduced
  in §4.1's row list and is trivial to re-run against the inventory method already in the repo).
- Code-sweep xref finder (§4.1's "fn-level xrefs", §4.2's pin sites): a capstone linear sweep
  recording every `ldr rN,[pc,#imm]` whose literal-pool target equals a given peripheral base,
  then walking backward from each site to the nearest `push {..,lr}` to name the containing
  function — same primitives `scripts/re/m0900_trace.py`'s internal `sweep()`/`func_start()`
  already use, reused directly against the full PERI base table instead of just `SPI1_BASE`/
  `SPI2_BASE`.
- Ghidra project (§3): `analyzeHeadless <scratchpad>/ghproj m0900 -import
  firmware/P3X_FW_V01.11.0020_m0900.bin -loader BinaryLoader -loader-baseAddr 0x08008000
  -processor ARM:LE:32:Cortex`, then a Jython postScript applying the name list (§2/§4) and the
  two structs (§5) via `-process "P3X_FW_V01.11.0020_m0900.bin" -noanalysis -postScript
  <script>`.
- Full decompiles (§2.4): a second Jython postScript using `ghidra.app.decompiler.
  DecompInterface` against the function addresses listed, 60s timeout each.
