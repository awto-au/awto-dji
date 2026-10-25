# m0101 — ThreadX camera loader, reversed

Issue awto-au/awto-dji#37 (`m0101` half — the `m0100` Linux-side consolidation is a
separate agent's scope, not touched here).

Prior state: `code-provenance.md:25` had only the toolchain fingerprint (`IAR` + `ThreadX`).
`air-id-and-stream-survey.md`'s module table already had one thin row (arch guess, two
string offsets, no function-level work) — this doc supersedes that row with a full Ghidra
pass, the NAND partition map, the firmware-update control flow, and the cross-module link
to `m0100`'s UEG layer. Tags: **V** verified in bytes/code (address cited), **I** inferred,
**U** unknown.

## Scope & reproduction

- Firmware: `P3X_FW_V01.01.0006` (container), module `m0101`, internal sub-version
  `v01.05.2735` (string at file offset `0x0`; the container-level `.ini` reports the same:
  `target=m0101 version=01.05.2735`). File `P3X_FW_V01.01.0006_m0101.bin`, 411,084 bytes.
  Unpacked with `dji_xv4_fwcon.py` per `docs/data-manifest.md`.
- Also present locally, not separately analysed here (same `.ini` role string, worth a diff
  pass later): P3XW 01.00.4539-ish, P3C, P3SE, P3S0008 `m0101` images.
- Method: `strings -t x` triage, then a full Ghidra 12.2 headless pass
  (`scripts/re/m0101_ghidra_disasm.py`, post-script `scripts/re/ghidra/DumpM0101.java`).
  Static analysis only, no live hardware touched.
- Repro: `python3 scripts/re/m0101_ghidra_disasm.py` (log `tmp/logs/m0101_ghidra_disasm.log`,
  headless log `tmp/logs/m0101_ghidra_headless.log`, dump `tmp/m0101_ghidra/m0101_dump.txt`).
  Ghidra project archived at `re/ghidra-projects/m0101_threadx_loader.tar.gz`
  (`scripts/re/ghidra_archive.py`).

## 1. Chip / architecture — V

- **ARM Cortex-A9, ARMv7-A, little-endian**, IAR toolchain. String at file offset `0x64544`:
  `Copyright (c) 1996-2014 Express Logic Inc. * ThreadX Cortex-A9/IAR Version G5.6.5.1 SN:
  3675-264-0901 *` — this names the core directly (ThreadX ships a core-specific port; the
  banner string embeds which one was linked). This is **not an MCU** — confirms the task
  brief's "don't assume" instruction was warranted; it's the application-class core inside
  the **Ambarella A9SE** camera SoC, the same SoC that runs Linux as `m0100` (per the
  container `.ini`: `# Stores firmware for camera 'Ambarella A9SE' Ldr`).
- ARM exception-mode name strings present (`USER_32`, `FIQ_32`, `IRQ_32`, `SVC_32`, `ABT_32`,
  `UND_32`, `SYS_32`, `UK*_32` for the reserved modes) plus a full ARM data-abort/undefined/
  prefetch-abort crash-dump format string (`pc : [<%08lx>]  lr : [<%08lx>] ... Flags: %c%c%c%c
  IRQs %s FIQs %s Mode %s%s`) — standard ARM32 register-set crash handler, consistent with
  Cortex-A9 (also rules out AArch64/Thumb-only cores).
- **Ghidra confirms real code, not a data blob**: `ARM:LE:32:v7` (Ghidra's generic ARMv7-A
  language — no Cortex-A9-specific variant exists; A9 is a standard ARMv7-A core, no special
  ISA extensions needed) auto-analysis found **1,308 functions, 86,510 instructions** over
  the 401 KB image.
- **Base address: U.** No Ambarella A9SE loader-header spec was found publicly in this
  session's time budget, and the file has no ELF/program headers (`file` reports it as raw
  `data`) — loaded into Ghidra at base `0x0`, so every address cited below (including the
  Ghidra ones) is a **file offset**, not a real runtime address. Function boundaries and
  call graph (found from prologue patterns, not base-dependent) are still valid; absolute
  literal-pool loads inside the Ghidra dump are not.
- **ThreadX API call sites: U (not resolved this pass).** Two ThreadX task-name strings were
  found (`RootTask` @ `0x7a2c`, `AmbaPrintTask` @ `0x67fc`) confirming `tx_thread_create()`
  is called with these names somewhere in the image, but the commercial ThreadX build here
  has no exported `tx_thread_create`/`tx_queue_*`/`tx_semaphore_*` symbol strings (typical
  for a release build — Express Logic's own API names don't get linked as debug strings).
  Pinning down the actual `tx_thread_create` entry point would need FunctionID/byte-pattern
  matching against a reference ThreadX G5.6.5.1 Cortex-A9/IAR build, which wasn't attempted
  here — flagging as future work rather than guessing.

## 2. What this loader does — V (strings) + I (role)

This is **not a generic second-stage bootloader** — it's a dedicated, self-contained ThreadX
RTOS image whose entire job is **SD-card-triggered full-NAND firmware re-flash**. Evidence:

- It's one of its own NAND partitions. The firmware carries the full NAND partition table as
  string literals at file offset `0x5e3c`-`0x5f24`: `Bootstrap`, `Partition Table`,
  `Bootloader`, **`SD Firmware Update Code`**, `System Software`, `DSP uCode`,
  `System ROM Data`, `Linux Kernel`, `Linux Root FS`, `Linux Hibernation Image`, `Storage1`,
  `Storage2`, `Index for Video Recording`, `User Settings`, `Calibration Data`. `m0101`'s own
  role (per its `.ini` comment, "Ldr") lines up with the `SD Firmware Update Code` slot, not
  `Bootloader` — i.e. it's a dedicated recovery/update stage, distinct from the primary
  bootloader that normally hands off to Linux. (**I** — the self-reference is strong
  circumstantial evidence, not a direct "this partition = this binary" proof; no boot-mode
  entry condition was found to confirm when it's invoked over the normal boot path.)
- Core control-flow strings (file offsets, `strings -t x`):
  - `0x4c5c` `Verifying image CRC ... 0x%x != 0x%x failed!` / `0x4c8c` `...done`
  - `0x4ce4` `firmware model name doesn't match!` — checked against `0x4cdc` `FC300X`
    (DJI's internal model code for the Phantom 3 Professional camera — matches the legacy
    path string below)
  - `0x4da8` `firmware header is illegal!`, plus a header dump format: `length: %d`,
    `crc32: 0x%08x`, `ver_num: %d.%d`, `ver_date: %d/%d/%d`, `img_len: %d`,
    `mem_addr: 0x%08x` — the on-disk firmware-file header layout it parses.
  - `0x4ee0` `Program "%s" to NAND flash ...`, with backup (`Back up partion data`), erase
    (`Erase partition "%s"!`), and reboot (`0x5084` `DjiFwUpdaterReboot`, `[DJI]
    Reboot......`) following a successful write.
  - Two ThreadX worker tasks named in strings: `0x5168` `DjiFwUpdaterLedTask` (status LED
    during the flash) and `0x51bc` `AmbaFwUpdaterTask` (the main update state machine).
  - Firmware file paths it looks for on the SD card: `0x554c` `C:/P3X_FW_V??.??.????.bin`
    (current naming, matches this repo's own unpacked filenames) and the legacy
    `0x553c` `C:/FC300XFw.bin` — direct proof this same code path shipped across at least
    two DJI model-name eras for this camera line.
  - NAND chip identified by string: `0x53d4` `Micron MT29F2G08ABADA_256MB_PG2K` (256 MB,
    2 KB page SLC/MLC NAND) — the physical flash this loader's NFTL/NAND driver stack
    targets.
- **Ghidra confirms this is live code, not dead strings**: `AmbaNFTL_Init` (string @ `0x6654`)
  has a real call-site xref from `FUN_00013768` at instruction `0x137cc` inside the Ghidra
  dump — the NAND-flash-translation-layer init path is reachable code, matching the strings
  triage. (Most of the other target strings in `tmp/m0101_ghidra/m0101_dump.txt` showed up
  as defined data but without a Ghidra-resolved xref — likely referenced via a computed/
  table lookup Ghidra's auto-analysis didn't propagate, e.g. a ThreadX task-create table —
  not evidence those code paths are unreachable, just that this pass didn't trace them.)
- Underneath the updater logic sits a full Ambarella platform driver stack, all present as
  named functions in strings: `AmbaNAND_*` (raw NAND program/erase/read/ReadID), `Nftl*`
  (flash translation layer: bad-block handling, logical/physical block tables), `AmbaFS_*`
  (FAT12/16/32 + exFAT filesystem, `AmbaFS_CreateBootArea`), `AmbaSD_*`/`AmbaRTSL_SD*` (SD
  card driver incl. UHS/SDIO/MMC4 mode negotiation), `NandFS_*` (NAND-backed filesystem).
  This is boilerplate Ambarella SDK/BSP code `[lib]`-grade, not DJI application logic — it's
  what you'd expect any Ambarella A9SE SD-card firmware-updater stage to carry.

## 3. Cross-module link: the `Dji*Ueg*`/`Dji*Uec*` state machine — V (strings), I (role)

- `m0101` exposes four functions by name that read as a **persistent update-state API**:
  `0x545c DjiUegFwStageSet`, `0x54d4 DjiUegFwStageGet`, `0x54e8 DjiUecFirmwareDetect`,
  `0x5624 DjiUecSucceedHandle`, `0x5678 DjiUecFailHandle`. The handle functions rename the
  firmware file on success/failure (`_updated` / `_damaged` suffix strings nearby), and the
  stage set/get pair round-trips through NAND meta (`AmbaNAND_SetMeta`/`GetMeta`,
  `[DJI_UEG] %s: Read Back Check Fail. Write[%d] Read[%d]`) — i.e. a write-then-read-back
  verified flag surviving reboot.
- **This is the same naming family as `m0100`'s UEG (Upgrade Engine) layer**, already
  partially documented in `air-id-and-stream-survey.md` ("Upgrade engine (UEG)" section) for
  the Linux side. Checked directly: `strings tmp/air/.../m0100.bin` (both the P3X0006 and
  P3XW unpacks) carries `DjiUegFwCamLdrEntry`, `DjiUegFwCamAppEntry`, `DjiUegFwCamBstEntry`,
  `DjiUegFwConfirmSet/Get/Proc`, `DjiUegFwFailHandle`, `DjiUegFwFinishProc`, and a debug
  command string `Clear all update stage: t dji ueg clr.`. The `CamLdr` entry name is a
  direct match for this module's own role (camera **Ldr**, per its container `.ini`).
- **Read as (I):** `m0101` is the ThreadX-side half of one shared firmware-update state
  machine; `m0100` (Linux) is the orchestrator that drives USB/network-pushed updates for
  the *other* modules (radio, FPGA, gimbal, FX2LP — see its firmware table in
  `air-id-and-stream-survey.md`) and hands off to `m0101` specifically for the camera's own
  SD-card-triggered re-flash, using the shared `DjiUeg*`/`DjiUec*` NAND-meta flag as the
  cross-reboot handshake. Not independently proven (no capture of the flag's NAND offset or
  a live trigger), but the shared naming convention plus matching role strings
  (`CamLdrEntry` / this module's own `Ldr` tag) make it a strong inference, not a guess.
- The `m0100` side also has `DjiUegFpgaCleanUpHandle`/`DjiUegFpgaFinishHandle` (FPGA-specific
  UEG handlers) — confirming the FPGA update path is real and lives in the UEG framework,
  but **on the `m0100` side, not here**. Out of scope for this doc (the `m0100` consolidation
  is the other agent's half of #37); noted only because it's the direct answer to "does
  `m0101` touch FPGA" below.

## 4. FPGA-related info — V (negative)

**No FPGA/bitstream/Cyclone/Lattice/config-flash strings or NAND-partition entries anywhere
in this module.** `grep -i 'fpga\|bitstream\|lattice\|cyclone'` over the full strings dump
returns zero hits. This module does not touch the FPGA update path. Relevant to issues #18
(config-flash writer still unidentified) and #19 (firmware-push engine): **ruled out as the
answer for either** — the FPGA-specific UEG handlers live in `m0100` (see §3), not `m0101`.

## 5. Technical / diagnostic / developer surface — V (partial), I (no hidden shell found)

- A real debug console exists: `AmbaPrintTask` (ThreadX task, string @ `0x67fc`) emits
  ANSI-colour-coded log lines (`\x1b[0;31m`...`\x1b[0;37m` escape codes present as strings)
  with a `[%08u]` timestamp and `[%s:th%d:%d]` thread-id prefix format — a standard
  Ambarella BSP debug-UART logger, write-only from what's visible in strings.
  `K_ASSERT at %s %d` assertion strings are scattered through the NAND/NFTL/SD driver stack.
- **No interactive command/shell parser was found in this module.** Unlike `m0100`'s
  `t dji ueg clr` debug-console command (found while cross-checking §3, on the Linux side),
  nothing in `m0101`'s strings looks like a tokenised command table or shell prompt — this
  loader looks purely automatic (SD-card-present → file-found → verify → flash → reboot),
  with print-only diagnostics. Absence-of-evidence caveat: a command parser using a binary/
  opcode protocol rather than text tokens wouldn't show up in `strings` at all; this wasn't
  independently checked via code (no time budget left this pass) — flag as **U**, not ruled
  out, just not found.

## 6. Switch/mux mechanisms — V (negative, SD-protocol only)

The only "switching" logic in this module is SD/MMC bus-mode negotiation at the protocol
level: `AmbaRTSL_SDSwitchFunc`, `SDSetupUhsMode`, `UHS Switch Group1/3 0x%x, 0x%x`,
`Mmc4DetermineBusWidth` — standard SD4.0/UHS-I speed-class negotiation with the inserted
card, not a DJI-specific mode mux. No RF-path, USB-path, or video-path mux strings found
(contrast with `m0100`, which does carry `DjiMsgStUsbSwitchStatusSet` /
`DjiUegDm368StreamControl` per the existing air-id survey) — nothing here is relevant to
issues #18/#25's switch/mux thread.

## 7. Firmware-update specifics — V

Putting §2's strings in flow order (**I** for the exact ordering/branching, each individual
step is **V**):

1. `DjiSDInit` detects an SD card in the slot (`Card doesn't exist %u!, can't update the
   firmware.` / `Card In Slot.`), retries init once (`Try to reinit the SD card`), checks
   filesystem format is supported.
2. Starts a boot-up watchdog (`[DJI] Start WDT of %d seconds for boot up......`) and prints
   its own version banner (`[DJI] SD Updater Version [v%02d.%02d.%04d] Build %s %s`, built
   `Apr 23 2015 21:16:59` for this binary — toolchain build timestamp, not a functional fact,
   noted only to date this specific build).
3. Looks for `C:/P3X_FW_V??.??.????.bin` (or legacy `C:/FC300XFw.bin`) on the card
   (`AmbaFS_fopen`), reads and validates the header (length/crc32/ver_num/ver_date/img_len/
   mem_addr fields), rejects on model-name mismatch (`FC300X` check) or bad CRC.
   - No signature check in this path: header fields, model name and CRC32 only (V).
4. Reads the firmware's own embedded partition-table info (`no partition info in firmware!`
   if absent), gets/allocates the current NAND partition table (`Can't get ptb, erase it`),
   backs up media partitions first (`Back up partion data`, `AmbaFS_CreateBootArea`).
5. For each target partition: erase (`Erase partition "%s"!`, `AmbaNFTL_ErasePart`), program
   from the image (`Program "%s" to NAND flash ...`), fail path logs `Firmware %s program
   fail.` and leaves the card's status via `DjiUecFailHandle` (renames file `_damaged`).
6. On success: `DjiUecSucceedHandle` renames the file `_updated`, sets the UEG stage flag
   (`DjiUegFwStageSet`) with a read-back verify, runs the LED task throughout
   (`DjiFwUpdaterLedTask`), stops the watchdog (`[DJI] Stop WDT.`), and reboots
   (`DjiFwUpdaterReboot` → `[DJI] Reboot......`).
7. Partitions it can write span the **entire NAND**, not just the camera app: `Bootstrap`,
   `Partition Table`, `Bootloader`, `System Software`, `DSP uCode`, `System ROM Data`,
   `Linux Kernel`, `Linux Root FS`, `Linux Hibernation Image`, plus the non-boot data
   partitions (`Storage1/2`, `Index for Video Recording`, `User Settings`,
   `Calibration Data`). I.e. an SD-card firmware file pushed through this path can
   **re-flash everything** on the camera SoC, including what later becomes `m0100`'s own
   Linux kernel/rootfs — consistent with this being the full-recovery path, not an
   incremental updater.

## Confidence summary

| Question (from #37) | Answer | Confidence |
|---|---|---|
| Chip/arch | ARM Cortex-A9 (ARMv7-A), IAR + ThreadX G5.6.5.1 | **V** |
| Base load address | unknown | **U** |
| Role | dedicated SD-card full-NAND firmware re-flash stage, not a generic bootloader | **I**, well-supported |
| ThreadX API call sites identified | not resolved this pass (task names found, not `tx_thread_create` itself) | **U** |
| Debug/test/diagnostic surface | print-only ANSI debug task (`AmbaPrintTask`); no interactive shell found | **V** (what's there) / **U** (absence of a binary-protocol shell not ruled out) |
| FPGA touch | none — lives in `m0100`'s UEG layer instead | **V** (negative) |
| Firmware-update specifics | full flow reversed from strings + partial Ghidra xref confirmation | **V/I** |
| Switch/mux mechanisms | SD/UHS bus-mode negotiation only, nothing DJI-specific | **V** (negative) |

## 8. Follow-up pass (second agent, 2026-10-24) — the 3 open items from #37

Reused the first pass's Ghidra project/dump (no re-run needed). Method: ThreadX's public
ABI (github.com/eclipse-threadx/threadx, `common/inc/tx_*.h`) defines a fixed magic 32-bit
"ID" constant per object type (`TX_THREAD_ID=0x54485244` etc) that every create/validate
function reads or writes — these are stable across ThreadX versions and not DJI-specific, so
they work as byte-pattern anchors even with zero symbols. Capstone (ARM:LE:32:v7) linear
sweep for every `LDR Rd,[PC,#imm]` literal load, resolved to its target, found every place
in the image these constants are touched. Repro: `scripts/re/m0101_threadx_api_scan.py`
(log: `tmp/logs/m0101_threadx_api_scan.log`).

### 8.1 ThreadX primitive call sites — V (resolved, supersedes §1's "not resolved this pass")

Found **4 ThreadX object-create primitives**, each by its magic-ID *write* (not a
read+compare — every other hit on these constants is a validate-pattern
`cmp r1,r2; bne fail`, the generic "is this ID stamped" check every other thread/semaphore/
mutex/event-flags API function does first; only the create function ever *writes* the ID):

| Primitive (candidate) | create fn entry | ID write site | magic ID |
|---|---|---|---|
| `_tx_thread_create` | `0xc1e0` | `0xc2cc` (`str r0,[r4]`) | `TX_THREAD_ID` |
| `_tx_semaphore_create` | `0xccec` | `0xcd24` | `TX_SEMAPHORE_ID` |
| `_tx_mutex_create` | `0xd638` | `0xd670` | `TX_MUTEX_ID` |
| `_tx_event_flags_create` | `0xe060` | `0xe08c` | `TX_EVENT_FLAGS_ID` |

`_tx_thread_create` cross-checked independently three ways (not just the ID write):
calling convention has 2 extra stack args beyond r0-r3 at `[sp,#0x28]`/`[sp,#0x2c]`
(`_tx_thread_create(thread,name,entry_fn,entry_input,stack_start,stack_size,priority,
preempt_threshold,time_slice,auto_start)` — exactly 10 params, the 5th/6th land there); a
`bl` right after loading `stack_start` with `r1=0xef` (`0xc210`) matches ThreadX's
`TX_STACK_FILL` (`0xEFEFEFEF`) stack-poison pattern; and right after the ID write, a
load-increment-store on a global immediately followed by `cmp r0,#0; bne` matches
`_tx_thread_created_count++` / "first thread created" special-case from ThreadX's own source.

Each primitive is called from exactly **one** Ambarella-style convenience wrapper (checks a
magic struct-size constant, `0xbc`=188 bytes for the thread one, before calling through —
classic Ambarella KAL ABI-compat guard):

| Wrapper (`AmbaKAL_*Create` candidate) | calls | called from |
|---|---|---|
| `0xa30c` (thread) | `0xc1e0` @ `0xa500` | `0x9cd4` @ `0x9d18` (4 call sites, see below) |
| `0xa8c4` (semaphore) | `0xccec` @ `0xa9d4` | — |
| `0xacd0` (mutex) | `0xd638` @ `0xadf8` | — |
| `0xaf38` (event flags) | `0xe060` @ `0xb040` | — |

**Negative/unresolved sub-result:** could not tie the `RootTask`/`AmbaPrintTask`/
`AmbaFwUpdaterTask`/`DjiFwUpdaterLedTask` name *strings* (§1) to these call sites directly.
Checked exhaustively — zero hits for all 4 string addresses across every ARM addressing
mode that could carry an absolute/relative reference: direct 32-bit pointer anywhere in the
file, `LDR Rd,[PC,#imm]` literal loads, `ADD/SUB Rd,PC,#imm` (ADR-style), and `MOVW+MOVT`
pairs. The one further-up generic task-spawn helper found (`0x9cd4`, called from exactly 4
sites: `0x1231c`, `0x1239c`, `0x14938`, `0x62c20`) passes r0/r1 values that don't decode
cleanly as a flat name pointer either (r0 values land ~0x330b8-0x3adc0 *past* the 401 KB
file — plausible as `.bss`-resident TCB globals under base 0x0, consistent with §1's base
question, but not confirmable without the base). **Flag as genuinely unresolved, not
guessed**: either the name strings reach `tx_thread_create` through a path this sweep can't
see (e.g. an indirect/computed call, which a linear `bl #imm` scan structurally cannot find),
or these 4 call sites are unrelated tasks and the named ones are created elsewhere (e.g. via
the direct, wrapper-bypassing caller of `_tx_thread_create` found at `0x62fc4` — see 8.4).

### 8.4 New finding: a second, Ghidra-unanalyzed ThreadX code region — U, flagged for future work

A second cluster of ThreadX ID-validate patterns (and one direct, wrapper-bypassing
`_tx_thread_create` call, `0x62fc4`) sits around file offset `0x58000`-`0x64000` (~45 KB:
`TX_THREAD_ID` reads @ `0x587b4`/`0x58a94`, `TX_TIMER_ID` @ `0x62fb4`/`0x63300`,
`TX_EVENT_FLAGS_ID`/`TX_MUTEX_ID`/`TX_SEMAPHORE_ID` reads @ `0x63550`/`0x6361c`/`0x637ac`).
**None of this region is covered by the first pass's Ghidra function list** — bisecting any
address in it against the 1,308-function table lands on a function hundreds of KB away
(Ghidra's auto-analysis never flowed into this region, so it has no identified function
boundaries at all despite clearly being valid ARM code per manual capstone disassembly).
Could be a second statically-linked ThreadX personality/support library, or code Ghidra's
call-graph discovery simply never reached. Not investigated further this pass — would need
a manual "force-disassemble + create function" pass in Ghidra, or a code-coverage diff
against the function list, to resolve.

### 8.2 Base load address — still U, with one correction to the first pass's own evidence

- **Correction:** the first pass's Ghidra function list shows `Reset`/`UndefinedInstruction`/
  `SupervisorCall`/.../`FIQ` at file offsets `0x0`-`0x1c`, which could misread as "the real ARM
  exception vector table lives at offset 0, so base=0 is confirmed." It is not that — these
  are Ghidra's own default placeholder labels for the generic ARM processor module, created
  regardless of what's actually there. Checked the real bytes: file offset `0x0` is the ASCII
  version tag `v01.05.2735\0...` (confirmed via hex dump), not branch/LDR vector instructions.
  Noting this so a future pass doesn't reuse that function-list entry as vector-table evidence.
- **Attempted two independent resolution methods this pass, both negative:**
  1. Brute-force: for every aligned 4-byte value V in the file, treat `V - stringOffset` as a
     candidate base, keep only candidates consistent across all 4 task-name strings
     simultaneously. ~30 "matches" out of 11,910 candidates — all false positives: they
     cluster on `0xe59e......`, which is just the top byte of ARM's unconditional `LDR`
     encoding (`0xE5......`), i.e. the search was matching instruction bytes, not real
     pointers. No credible base emerged.
  2. Checked whether the header-like bytes at file offset `0x40`-`0x47` (`length`=`0x64548`,
     matching `file_size (0x645cc) - 0x84`-byte header exactly) carry a `mem_addr` field per
     the firmware-header format documented in §2/§7 (the *external* SD-card container
     format) — they don't line up with that struct; this file's own leading 0x84 bytes are a
     different, smaller header (redundant two-copy layout, 0x20 bytes apart, matching only on
     a CRC-sized field), not the container header. No load address recovered from it.
  - Bonus, unrelated to base resolution but found along the way: bytes `0x48`-`0x83`
    (immediately after that header) are a flat `uint32[]` list — `0x800, 0x40000, 0x40000,
    0x100000, 0x2000000, 0x500000, 0xf00000, 0xa00000, 0x3c00000, 0x1e00000, 0, 0x500000,
    0xc00000, 0x500000` — plausible real NAND partition **sizes** lining up positionally with
    §2's partition **name** list (`Bootstrap, Partition Table, Bootloader, SD FW Update Code,
    System Software, DSP uCode, System ROM Data, Linux Kernel, Linux Root FS, Linux
    Hibernation Image, Storage1, Storage2, ...`). Not verified against a second firmware build
    for consistency — flag as **I**, worth a follow-up diff pass, not the base answer.
  - **Verdict: base address remains U.** No public Ambarella A9SE loader-header spec, and
    both attempts above to derive it from the image's own bytes came back empty-handed —
    stating this plainly rather than guessing a round number.

### 8.3 Debug/input surface — upgraded from U to a stronger, well-supported negative (I)

- Full `strings` triage (558 strings ≥4 chars) has **zero** hits for `uart`, `usb`, `i2c`,
  `spi`, `debug`, `dbg`, `console`, `shell`, `getchar`, `scanf`, `parse`, `token`, or
  `readline` (case-insensitive) anywhere in the module. The only `cmd`-adjacent strings are
  SD/MMC protocol command names (`AmbaRTSL_SDSendOpCondCmd1`, `AmbaRTSL_SDSendOPCondAcmd41`,
  `cmd error %d`) — these are the loader **issuing** SD-card bus commands outward, not an
  inbound channel into the loader.
- Combined with §5's "no interactive shell token table" finding: this module carries **no
  named driver for any input-capable peripheral at all** (UART/USB/I2C/SPI), only the SD-card
  host-controller stack used to read the firmware file (already documented in §2/§7).
- **Still can't be 100% ruled out** — a register-level binary protocol with no debug strings
  at all would be invisible to this method, and that residual case wasn't checked at the
  instruction level this pass either. But the complete absence of *any* named serial-capable
  peripheral driver is stronger evidence than the first pass had (which only checked for a
  text-shell token table) — there is no identified peripheral left to carry such a protocol.
  Upgrading from the first pass's **U** to **I, well-supported negative**.

## Artifacts

- `scripts/re/m0101_ghidra_disasm.py`, `scripts/re/ghidra/DumpM0101.java` — repro (first pass).
- `scripts/re/m0101_threadx_api_scan.py` — repro for §8.1/8.2 (ThreadX magic-ID literal scan).
  Log: `tmp/logs/m0101_threadx_api_scan.log`.
- `tmp/m0101_ghidra/m0101_dump.txt` — function list (1,308), target-string xrefs (gitignored,
  regenerate via the script above).
- `re/ghidra-projects/m0101_threadx_loader.tar.gz` — archived Ghidra project (committed).
