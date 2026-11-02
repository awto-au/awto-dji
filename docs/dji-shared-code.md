# Cross-module shared code and system-wide inventory

Cross-cutting pass over every reversed MCU/SoC module (#36 m0900, #41 m0400, #61 intel
i6050, #84 session-key trace), prompted by the observation that DJI's own firmware likely
reuses code/constants across modules, and that per-module findings should cross-check each
other instead of living as N independent guesses. Tags: **V** verified (bytes/instructions
cited), **I** inferred (same shape, not byte-proven), **U** unknown. Method: `docs/re-rules.md`.

**Scope note:** read-mostly. No existing `docs/symbols/<module>.tsv` or module-specific doc
was edited. Any rename proposed here is a *proposal* — a later pass applies it to the
module's own TSV.

**Stale-input flag (checked `git log -1 --format=%cI -- <path>` and `git status` at read
time, 2026-11-02):**

| Module | State when read | Risk |
|---|---|---|
| `m0306` | **Actively mid-flight.** `docs/symbols/m0306.tsv` and `m0306-structs.h` modified but uncommitted; `m0306-duml-handlers.tsv`, `m0306-names.tsv`, `m0306-vectors.tsv` untracked (new, not yet landed); `re/ghidra-projects/m0306_flight_controller/` project files modified. Everything cited from m0306 below is a **snapshot of a moving target** — re-check against the committed version before relying on an m0306 address. | high |
| `m0400` | TSV/struct/doc committed 2026-11-02 14:53-15:11 (same session, "naming pass" + "rename-first driver" commits). `re/ghidra-projects/m0400_gimbal/` project files show as modified in `git status` (likely an open/dirty Ghidra session, not necessarily new content) — addresses used here matched the committed dump. | low-medium |
| `m1400`/`c1_m1400.tsv` | Committed 2026-11-02 14:53 ("session-key trace #84"). `re/ghidra-projects/m1400_radio/` project files also show modified. Same caveat as m0400. | low-medium |
| `m0900` | Committed 2026-11-02 13:35/14:53. Not in `git status` modified/untracked list at read time — settled. | low |
| `intel_i6050_fw1.5.tsv` | Committed 2026-11-02 12:43 (#61). Settled. | low |
| `air_modules.tsv` | Committed 2026-10-24. Settled, old. | low |
| `m0101`, `cam_server`/`rpc_trans`/`viz_tracking` (m0100 Linux) | Docs committed, Ghidra projects archived as `.tar.gz` (not live project dirs) — settled. | low |

---

## Goal 1: shared DJI code across modules

Checked by (a) matching constant pools (CRC seeds/tables), (b) instruction shape *plus*
literal immediates together, (c) byte-identical compiled output where a library origin is
already established in one module. Shape alone, without shared constants, is explicitly
called out as weak (I), not claimed as V.

### 1.1 DUML CRC8/CRC16 tables — V, byte-identical, the strongest finding this pass

Extracted the literal table bytes directly from each unpacked firmware image (scripts/re
below) and compared by SHA-256, not just by seed value:

| Table | Modules | Address each | File offset (base) | SHA-256 (first 16 hex) | Strength |
|---|---|---|---|---|---|
| DUML CRC8 (256 B, seed `0x77`) | `m0900`, `m0400`, `m1400` | `0x0801a208` (m0900) / `0x0801b8d7` (m0400) / `0x000249d2` (m1400) | base `0x08008000` / `0x08008000` / `0x0` | `04265e73941eab6a` — **identical across all 3** | **V** |
| DUML CRC16 (512 B, seed `0x3692`) | `m0900`, `m0400`, `m0306` | `0x0801a308` (m0900) / `0x0801b6d4` (m0400) / `0x080ef734` (m0306) | base `0x08008000` / `0x08008000` / `0x08020000` | `638dbc5f735cced0` — **identical across all 3** | **V** |

Reproduce: `python3 scripts/re/crc_table_crosscheck.py` (log
`tmp/logs/crc_table_crosscheck.log`). Reads only already-unpacked firmware images on disk
(not committed to the repo, per `HANDOVER.md` "DATA NOT IN THE REPO" — re-fetch via
`docs/data-manifest.md`'s hashes to reproduce independently).

**Caveat, stated precisely:** a CRC lookup table is a deterministic function of
(polynomial, bit order, reflect-in/out) — *any* correct implementation of the same
CRC-8/CRC-16 parameters produces byte-identical table contents, independent of whether the
C source was copy-pasted. So this is **V evidence that all four chips (STM32F103, STM32F4x,
STM32F427, LPC1765) use the exact same CRC parameters for DUML**, which is new (not
previously shown byte-for-byte across this many modules) but weaker than "literal copy-paste
of the containing function" would be. `docs/fc-device-dll.md` already showed the DUML
CRC8/CRC16 *constants* match the Windows `DJIDevice.dll`; this pass adds the **firmware-side
cross-MCU table-byte match**.

**The surrounding calc-loop code is NOT byte-identical — each chip hand-ports its own
walker over the shared table:**

| Fn | Module | Address | Size (B) | Shape |
|---|---|---|---|---|
| `duml_crc8_calc` | m0900 | `0x08011df8` | 22 | `ldrb/eors/ldrb/subs/bcs` loop, args `(buf,len,seed)` |
| `duml_crc8_append` / `crc8_calc` | m0400 | `0x08009410` / `0x0800dfb4` | 36 / 30 | split append+calc, args `(buf,len,init)` |
| `crc8_update` | m1400 | `0xeb10` | — | `(seed,data,len-1)` arg order, used only by `init_chip_uid` (UID checksum, not DUML framing) |
| `duml_crc16_calc` | m0900 | `0x08011e54` | 38 | `ldr/subs/bcc/ldrb/eors/ldrh/eor` |
| `crc16_calc` | m0400 | `0x0800df80` | 46 | same general shape, different register allocation |
| `duml_crc16` | m0306 | `0x0804f024` | 30 | same shape, STM32F427/Cortex-M4 code-gen |

Best name/table owner: **`m0900`'s `duml_crc8_calc`/`duml_crc16_calc` are the clearest-named
pair** (already V, `m0900-naming-pass.md` §6); propose applying the same `duml_crc8_calc`/
`duml_crc16_calc` names to m0400's `crc8_calc`/`crc16_calc` (currently generic, same role) and
to m1400's `crc16_update`/`crc8_update` (currently named for the UID use site only, even
though the table is the DUML one) — **not applied here**, proposal only; a later pass edits
those TSVs directly.

### 1.2 DES/3DES session-key cipher — m0900 ↔ m1400, already flagged I by issue #84, re-confirmed as *not* distinguishing evidence on the S-box

| Fn | Module | Address | Note |
|---|---|---|---|
| `des_key_schedule`/`des3_crypt_block` | m0900 | `0x0800cc08`/`0x0800cd4c` | V code, I purpose |
| `des3_key_schedule`/`des3_crypt_block` | m1400 | `0x1a8b8`/`0x1a908` | "same shape as m0900" (already I-tagged in `c1_m1400.tsv`, issue #84) |
| `des_sbox` table | m0900 `0x08015e5c` / m1400 `0x2ead4` | "same layout" per `c1_m1400.tsv` | **Not meaningful shared-code evidence** — FIPS 46-3 S-boxes are a published international standard; any correct DES implementation anywhere has byte-identical S-boxes regardless of code provenance. Downgrading this specific sub-claim from "evidence of shared code" to "expected, not distinguishing." |

The real shared-code claim here is the **session-key protocol** (cs9/cmd0 handler shape,
3DES-of-a-constant-under-a-random-key derivation) matching between `m0900:radio_session_key_init`
and `m1400:duml_set9_cmd00_session_key_rx` — already traced and I-tagged under issue #84
(`m1400:0xce94`). Not re-derived here; this pass only corrects the S-box sub-point.

### 1.3 Checked, no match found (negative results, stated per Goal 1's instruction not to claim shape-only as evidence)

| Candidate | m0900 | m0400 | Verdict |
|---|---|---|---|
| Ring buffer push/pop | `ring_push` `0x0800c274` (32 B), explicit size/mask `ByteRing` struct | `ringbuf_push` `0x0800a3cc` (66 B), power-of-2 `mask` struct | **Different sizes, different struct layout — not shared code**, independently written per chip. Same generic C idiom (shape-only I, not claimed as more). |
| CAN queue registration skeleton | `can_queue_init` `0x0800b3ec` (124 B): generic N-slot table, any StdId, TX/RX symmetric | `can_rings_init` `0x0800a36c` (58 B): exactly 2 fixed ids (0x412/0x413), asymmetric helpers (`can_send`/`can_send_urgent`/`can_send_split8`/`can_send_4xu16`/`can_rx_dispatch`) | **Different architecture, not shared code.** Same bus concept (CAN1, DUML-over-CAN), independently designed register layer per chip. |
| CAN TX/RX IRQ skeleton | `can1_tx_irq` `0x0800b298` (132 B) | no single generic equivalent — m0400 has 5 separate `can_send*` entry points plus a 1298-byte `can_rx_dispatch` switch | **Not comparable; not claimed as shared.** |

### 1.4 DUML frame parse/dispatch skeleton — shared *protocol*, not shared *code* (I, shape-only, stated as such)

Every MCU implements the identical wire shape (`0x55` sync, 10-bit length, header CRC8 seed
`0x77`, trailer CRC16 seed `0x3692`, version nibble) — confirmed independently per module in
`m0900-can-channels.md` §4, `m0400-naming-pass.md` §3, `fc-message-path.md`, `c1_m1400.tsv`
`port_send`/handler rows. But the **parser state machines differ per chip**: m0900's
`duml_parser_feed` is a single byte-wise state machine shared by every port; m0400's
`duml_assemble_can`/`duml_assemble_usart2`/`duml_assemble_uart4` are three near-duplicate
5-state machines (one per port, not factored into one shared function even within the same
chip); m0306 validates only the CRC16 trailer (`duml_frame_crc_ok`) with header CRC8
handling not located this pass. **Conclusion: one shared protocol spec, independently
hand-ported per chip/team — not literal shared code**, consistent with the CRC table finding
(shared constants, not a shared source file for the framing logic around them).

### 1.5 Not checked / out of scope this pass

- Flash parameter store: m0900 has none found; m0400 has a 128-slot wear-levelled store
  (`flash_param_save/load`, `m0400-naming-pass.md` §4); m0306's equivalent
  (`FlycExportParam`, `data/m0306-param-defaults.tsv`) is structurally different (834-field
  table, not a wear-levelled log) — no byte-level comparison attempted, different enough in
  shape that a match is unlikely; flagged rather than guessed.
- `intel_i6050` (Intel WiMAX modem firmware, #61) is **excluded** from this comparison: it
  is Intel's own codebase (traced strings: `GeHdi_Ul.c`, `RxGainCalib_Evp_Kp.c`, WiMAX Forum
  PKM/TLS labels), not DJI application code. Its own trace-ring-buffer (`trace_ring_ctl`,
  `0x00e4c220`) and `base64_encode` are Intel/WiMAX-stack artifacts with no DJI-side
  counterpart to compare against.

---

## Goal 3: whole-system inventory (MCU + Linux userspace + RTOS kernels + loose code)

Per owner direction: treat the MCU firmware, the `m0100` Linux userland, and the RTOS
kernels underneath each MCU/SoC as one system, not siloed per-chip.

### 3.1 Linux userspace (`m0100`, Ambarella A9SE) — checked against DUML framing: no shared protocol found (V, negative)

Cross-checked `cam_server`'s and `rpc_trans`'s IPC protocol (`docs/camera-linux-reversing.md`)
against the MCU-side DUML framing (§1.4 above):

- **No `0x55` sync byte, no CRC8/CRC16 check, no DUML cmdset/cmdid field anywhere in
  `cam_server`'s dispatcher (`FUN_0000b1c8`) or `rpc_trans`'s (`RPC_Ctrl_Svr_ProcRecv`,
  `0x8acc`).** Both dispatch on a flat `u16`/byte "Control Message Type" field
  (`cam_server`: 9-entry branch table on offset `+0x10`; `rpc_trans`: `msg->+0x8`, values
  1=TimeSync, 2=USB-query) inside an Ambarella `ambaipc_*`/UDT message envelope — a
  completely different, Ambarella-SDK-level IPC transport, not DUML. **V, checked and
  negative**: this Linux-side control plane and the DUML wire protocol are two unrelated
  protocol stacks that happen to both live on the camera SoC; no shared framing, CRC, or
  constant was found between them.
- **USB mode-switch (`docs/camera-linux-reversing.md` §6) does not tie into the CAN/UART bus
  topology** (`docs/dji-bus-topology.md`): it is a Linux-only pair of mechanisms — the RTOS
  GPIO mux (A9 vs DM368 ownership of the shared USB port, already on the RTOS side per
  `air-id-and-stream-survey.md`) and the A9's own `/proc/ambarella/uport` host/device
  controller-role switch — neither touches CAN1 (0x412-0x415) or any UART covered in the bus
  topology doc. `cam_server`'s `fxload -d 0547:1002` push and `m1500`'s own USB VID:PID
  (`0547:1002`, already in `naming-map.md`) are the one point of contact, already captured
  there; not re-derived.
- **Net: Goal 1's "shared code" question gets a clean negative for the Linux/MCU boundary.**
  The camera SoC runs two independent protocol stacks (DUML on the MCU/CAN/UART side, Ambarella
  `ambaipc` on the Linux side) with no shared framing code or constants found between them in
  this pass.

### 3.2 "Loose code" sweep — catalogued, not all resolved

Per owner's ask to catalog analysed-but-unlinked findings rather than leave them orphaned:

| Item | Where it lives | Status |
|---|---|---|
| m0101's second ThreadX code region, file offset `~0x58000-0x64000` (~45 KB) | `docs/m0101-threadx-reversing.md` §8.4 | Flagged in its own doc as "not investigated further" — already catalogued, not orphaned, just open. Noting here so it isn't lost in a future cross-module pass: this is the single largest un-function-bounded code region found across all modules read this pass. |
| `scripts/fpga/` (Mistral netlist analysis) | `docs/data-manifest.md` "Derived artifacts" | Explicitly marked **void** (superseded m2001 decode, pluribus #114) — correctly flagged as dead, not orphaned. |
| `cam_server_old`, `monhotplug` (disabled predecessor binaries on the m0100 rootfs) | `docs/camera-linux-reversing.md` §1/§1b | Already catalogued in-doc as reference/dead-code; not orphaned. |
| `viz_tracking`'s trigger mechanism | `docs/camera-linux-reversing.md` §8 | Explicitly left open in its own doc (re-checked twice, genuinely not found) — catalogued, not resolved. Not tied to any bus/CAN topology; it is a pure-software IPC/netlink consumer of the live-view buffer. |
| `boot_done` dead reference (6 init-script call sites, no binary/applet) | `docs/camera-linux-reversing.md` §9 | Resolved as "genuinely missing," catalogued. |
| m0400 unreferenced strings `motor_stop`, `record_enc`, `read_backup` | `docs/m0400-naming-pass.md` §6 | Already flagged in-doc as no-xref, owner U — catalogued, not orphaned. |

No genuinely *undocumented* orphan code was found this pass beyond what's already flagged
inside its own module/Linux doc — the repo's existing discipline of "flag as open" rather
than silently dropping a finding held up under this check.

### 3.3 RTOS kernel inventory (bare-metal vs RTOS, per module)

| Module | Chip/core | RTOS | Version evidence | Kernel primitive locations |
|---|---|---|---|---|
| `m0900` (air radio) | STM32F103, Cortex-M3 | **none — bare metal**, tick-driven main loop (`TickState`, TIM2/TIM3 compare slots) | n/a | n/a |
| `m0400` (gimbal) | STM32F4x, Cortex-M4F | **none — bare metal**, `tick_flag`-gated `main_loop` at 1999 Hz | n/a | n/a |
| `m0306` (flight controller) | STM32F427, Cortex-M4F | **µC/OS-III** | String fingerprint only this pass: `"uC/OS-III Idle Task"`/`"... Tick Task"`/`"Task Q"`/`"Task Sem"` (`docs/fc-io-inventory.md:69`, `docs/control-plane-re.md:602-603`) | Not located to specific addresses in the docs read this pass — string-level ID only, no PendSV/SysTick disassembly match recorded for m0306 (contrast m1400 below). Candidate follow-up: locate `OS_CPU_PendSVHandler`-shape code in `m0306_dump.txt` the way it was found for m1400. |
| `m1400` (ground RC MCU) | LPC1765, Cortex-M3 | **µC/OS-III** (same RTOS as m0306) | Two independent proofs, both V: (1) same string fingerprint at offsets `0x1238C`/`0x13AE0`/`0x123E4`/`0x123EC`; (2) **PendSV vector (vector 14, flash `0x23B46`) disassembled instruction-for-instruction matches the µC/OS-III Cortex-M3 port's `OS_CPU_PendSVHandler`** (save r4-r11 to TCB, task-switch hook, swap current/high-ready TCB pointers at RAM `0x100004E0`/`0x100004E4`, restore, `msr psp; orr lr,lr,#4; bx lr`); SysTick vector (`0x1C914`) matches the standard `OSIntEnter();OSTimeTick();OSIntExit();` tick template (`docs/control-plane-re.md` "RTOS correction" section). | **This is the strongest RTOS evidence in the repo** — not just a string match, an instruction-level port match. Good next target for a real `mcu_libmatch.py` compile-diff (Cortex-M3, matches m0900/m1400's toolchain family) once that tool is generalized past m0400. |
| `m0101` (camera loader, Ambarella A9SE) | ARM Cortex-A9 (ARMv7-A) | **ThreadX**, exact version string | `"Copyright (c) 1996-2014 Express Logic Inc. * ThreadX Cortex-A9/IAR Version G5.6.5.1 SN: 3675-264-0901 *"` (file offset `0x64544`, `docs/m0101-threadx-reversing.md` §1) | 4 object-create primitives located by ThreadX's own stable magic-ID constants (`TX_THREAD_ID` etc, scheme fixed since Express Logic days): `_tx_thread_create` `0xc1e0`, `_tx_semaphore_create` `0xccec`, `_tx_mutex_create` `0xd638`, `_tx_event_flags_create` `0xe060` (`docs/m0101-threadx-reversing.md` §8.1). A **second, Ghidra-unanalyzed ThreadX region** at file offset `~0x58000-0x64000` has further ID hits but no function boundaries yet (§8.4, also in §3.2 above). |
| `m0100` (camera Linux) | Ambarella A9SE | **Linux** (not an RTOS in the MCU sense) | kernel partition present, TI-DVSDK-style for the sibling `m0800`; not re-derived here | n/a — userland is the relevant layer, covered in §3.1 |

**Compile-diff follow-up, catalogued not attempted:**

- **µC/OS-III (m0306, m1400):** Cortex-M, same toolchain family `mcu_libmatch.py` already
  targets for m0400's libgcc/CMSIS match (#41) — once that tool is generalized past m0400,
  m1400's PendSV/SysTick vectors are the best starting candidate (already instruction-shape
  matched, just needs a real compiled µC/OS-III Cortex-M3 port byte-diffed in to go from I to
  V on individual kernel functions). **Do not duplicate `mcu_libmatch.py`** — this is a
  pointer for whoever generalizes it, not a new tool.
- **ThreadX (m0101):** different toolchain entirely — Cortex-A9 **IAR**, not GCC. Checked
  whether this exact version is on the now-open-sourced `github.com/eclipse-threadx/threadx`:
  **no** — `gh api repos/eclipse-threadx/threadx/tags` shows the earliest available tag is
  `v6.0_rel` (repo created 2020-05-11), using Eclipse's `6.x` numbering. The firmware's
  embedded version, `G5.6.5.1`, uses Express Logic's pre-acquisition numbering scheme and
  predates the Eclipse Foundation baseline — **it is not on GitHub**, so a byte-exact
  compile-diff would need Express Logic's original commercial G5.6.5.1 SDK for IAR/Cortex-A9,
  not the open-source repo. Shape-only (I) matching via magic-ID scan (already done, §8.1
  above) is likely the practical ceiling here without that specific historical SDK.

---

## Reproduce

- `python3 scripts/re/crc_table_crosscheck.py` — CRC8/CRC16 byte-identity check (§1.1), log
  `tmp/logs/crc_table_crosscheck.log`.
- `gh api repos/eclipse-threadx/threadx/tags` — confirms ThreadX G5.6.5.1 predates the
  open-source baseline (§3.3).
- Everything else in this doc is read from already-committed TSVs/docs, cited inline.
