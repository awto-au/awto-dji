# FC instrument: read-any-memory + runtime hook tracer (design)

Scope & safety: see `SAFETY.md`.

This document designs an instrumentation
tool for the P3 Pro flight controller (module **m0306**, STM32F427) that the operator
(dan@awto.au) uses to inspect their own aircraft's firmware state. It is **not** a flight
firmware: it initialises no motor/ESC driver and runs no control loop. It exists to answer
two kinds of question from the bench — "what's actually in this memory location" and "what is
this function being called with, right now" — without needing SWD/JTAG wired up (the comms
channel is DUML over the same CAN1 link the FC already speaks, or its USB device port).

Companion reading: `docs/fc-replacement-plan.md` (why/how a custom image gets onto the FC and
is safe to recover from), `docs/fc-bootloader.md` (loader/updater internals, no read-mem
command in stock DUML, the `0x77557755` image marker), `docs/fc-io-inventory.md` (pins,
peripherals, SPL identification), `docs/security-and-activation.md` (no firmware signature —
only AES + CRC + MD5 + marker gate the image), `docs/symbols/m0306.tsv` (addresses used below).
Honesty tags **V**/**I**/**U** follow `CLAUDE.md`.

## 1. Target and build model

- **MCU:** STM32F427 (Cortex-M4F). Flash base `0x08000000` (loader, sectors 0–4, never
  touched by the stock updater — **V**, `fc-bootloader.md`); app base `0x08020000` (sectors
  5–11, where m0306 itself runs — **V**). SRAM `0x20000000`; CCM (core-coupled, no DMA)
  `0x10000000`, used by the RAM-resident updater `m0305` (SP `0x1000e4e8` — **V**). Bank-2
  `0x08100000` exists on the dual-bank 2 MB die (**V**, `fc-bootloader.md`) but the app never
  references it.
- **Stack:** STM32Cube **HAL** + **FreeRTOS**, per `fc-replacement-plan.md`'s component table
  — deliberately *not* trying to match DJI's own SPL/µC-OS-III (**V** identified in
  `fc-io-inventory.md`); a clean-room app has no reason to match their register library, only
  their pin/bus facts (CAN1 PD0/PD1 AF9, etc.).
- **Transport:** DUML, either over **CAN1** (PD0 RX / PD1 TX, AF9, `can1_bringup`
  `0x08035100` — **V**) carrying the FC's normal `0x41x`-family device-type frames, or over the
  FC's **USB OTG_FS** device port (PA11/PA12 AF10, `usb_fs_bringup` `0x0803aac4` — **V**, the
  DJI-Assistant-2/upgrade link) as a CDC/vendor endpoint. Both are optional at compile time —
  see `fc/instrument/trace_pipe.h`'s transport interface — because either is sufficient and
  the design should not assume both are wired up on the bench.
- **Two ways to get this code running on the FC, same command set either way:**
  1. **Clean-room app.** Build this as a complete replacement app image at `0x08020000`
     (acceptance checklist in `fc-replacement-plan.md`: valid vector table, `0x77557755`
     marker, correct xV4 packaging, `FIRM_MATCH` fields). Full control, easiest to reason
     about, but reimplements CAN/USB bring-up from scratch.
  2. **Appended patch payload.** Keep the stock m0306 image entirely intact and append this
     code in the free flash tail (`0x080FD200–0x08100000`, ~11.5 KB free — **V**,
     `fc-replacement-plan.md`), reached by repointing one null `FlycExportParam` callback (or
     a `nullsub_*`/factory-test stub) to it. This mode **calls the stock `duml_send`
     (`0x0804f862`)** directly to transmit replies instead of bringing up its own transport —
     far less code, and every DJI driver/failsafe stays live underneath. This is the
     preferred mode for a first bench instrument because it needs no new bring-up code at
     all; the risk is entirely in the one patched callback pointer and is trivially
     recoverable (reflash stock m0306 via DJI Assistant 2, loader untouched either way).
  The command handlers (`readmem.c`, `hook.c`, `trace_pipe.c`) are written against a small
  transport interface (`fc_instrument_transport_t`: `send(bytes,len)`) so the same handler
  code works unchanged in either mode — in mode 2 that interface is a one-line wrapper over
  `duml_send`.

## 2. Command A — READ-ANY-MEMORY

### 2.1 Protocol

DUML command, new cmdset/cmd pair (pick an unused slot in the 723-entry catalog per
`fc-bootloader.md` — stock DUML has **no** peek/poke, confirmed by that doc's catalog scan).

Request payload:
```
struct read_mem_req { uint32_t addr; uint16_t len; };   // len capped (see 2.3)
```
Response: one or more DUML frames, each a chunk `{uint32_t addr; uint16_t chunk_len; uint8_t status; uint8_t data[chunk_len];}`, status `0 = OK`, non-zero = guard rejected this chunk (see below) with no data bytes. Chunking matches the DUML max payload (the stock upgrade path already streams `TranslateData` in chunks the same way — **V** pattern reuse, `fc-bootloader.md`).

### 2.2 What must be readable, and why each is non-trivial

| Region | Range | Why non-trivial |
|---|---|---|
| Flash (app + loader) | `0x08000000`–`0x080FFFFF` | ordinary reads; loader region (sectors 0–4) is exactly the piece `fc-bootloader.md` says is otherwise unobtainable without SWD — this command is the whole point for that case |
| SRAM | `0x20000000`+ | ordinary reads, but must not read SP-adjacent live RTOS state carelessly (see 2.4 reentrancy) |
| CCM | `0x10000000`–`0x1000FFFF` | ordinary AHB read *only if the bus matrix routes it* — CCM is **not** DMA-accessible but *is* CPU-accessible, so a straight load works, unlike a DMA-based reader would |
| OTP | `0x1FFF7800`–`0x1FFF7A0F` | one-time-programmable system memory; readable like flash but a different bank — must not attempt program/erase, read-only is safe |
| 96-bit UID | `0x1FFF7A10`–`0x1FFF7A1B` | already read by the stock app (`uid96_read` `0x0808527a` — **V**), so this is a known-safe 12-byte region to sanity-test the command against before trusting it on anything else |
| Option bytes | `0x1FFFC000`–`0x1FFFC00F` | readable as normal memory; **never write** this command — option bytes are also reachable at `0x40023C14` (`FLASH_OPTCR`) and writing either representation can brick boot config. Read-only enforced in code (see 2.3) |
| Peripheral registers | `0x40000000`+ | always mapped (no bus fault for a valid peripheral base), but some registers have **read side effects** (e.g. clearing a status flag, popping a FIFO) — documented as a caveat, not blocked, since the operator asked for raw read access |

### 2.3 BusFault guard

An address outside implemented memory (unmapped Cortex-M4 region, e.g. a bogus `addr` typo'd
by the host) causes a **BusFault**, which is fatal unless caught. Two complementary guards,
both implemented in `readmem.c`:

1. **Static whitelist** (cheap, checked first): a short table of known-good ranges — the ones
   in §2.2 — plus the on-target flash/SRAM/CCM sizes queried from `DBGMCU`/linker symbols.
   Anything outside the table is rejected *before* it is ever dereferenced, with status
   `READMEM_ERR_RANGE`, no fault risk at all. This covers the common case (host typo, or
   deliberately probing "is this mapped") cheaply.
2. **Fault-catching read** (for addresses inside a nominally-valid region that may still fault
   — e.g. a peripheral base whose exact sub-range is unmapped, or a flash address inside an
   erased/blank sector read during an in-progress upgrade): temporarily install a custom
   `BusFault_Handler`, set `SCB->CFSR`/`SCB->SHCSR` for precise fault reporting, perform the
   read inside a `setjmp`-style frame (in practice: the fault handler advances the stacked PC
   past the faulting load instruction and sets a "faulted" flag + a sentinel return value,
   mirroring the pattern ARM app notes use for "probe this address" code, e.g. a fixed-size
   `__LDR` done through an asm helper the fault handler can recognize by PC range). Restore the
   board's normal `BusFault_Handler` immediately after. This never escalates to HardFault
   (BusFault is enabled via `SCB->SHCSR |= BUSFAULTENA`) and never resets the board.

Both guards return a `status` byte in the response chunk rather than crashing; a rejected
chunk still gets a response frame so the host knows the read was refused, not silently dropped.

**Write is out of scope for this command.** `readmem` is read-only by construction — no
address is ever treated as a destination. This matters specifically for option bytes and
OTP, where an accidental write is a real brick/fuse-burn risk; the API has no write entry
point at all, so there's no code path to misuse.

### 2.4 Other caveats

- **Peripheral read side effects** (status-flag-clear-on-read registers, FIFO pop registers):
  reading one changes device state. Only an issue if the operator reads a peripheral that
  something else (DJI's own drivers, in patch mode) is concurrently using — e.g. reading
  `USART_SR`/`DR` would eat a byte the real UART driver wanted. Documented, not blocked: the
  command is a diagnostic scalpel, and the design trusts the operator to know this when
  reading live peripheral state rather than silently special-casing every peripheral.
- **Flash read during erase/program:** per `fc-bootloader.md`'s "universal constraint", a
  flash bus read while another sector is mid-erase/program can stall. Not a concern at rest
  (bench, not mid-upgrade); noted so nobody runs `read_mem` concurrently with a firmware
  upgrade.
- **CCM is CPU-only, never DMA** — confirmed fine for this command since it's a plain CPU
  load/store path, no DMA involved.

## 3. Command B — runtime function hook tracer

### 3.1 Mechanism: FPB comparator → DebugMonitor exception

The Cortex-M4 **Flash Patch and Breakpoint (FPB)** unit at `0xE0002000` has:

- `FP_CTRL` (`0xE0002000`): bit0 `ENABLE`, bit1 `KEY` (write-1-to-enable-writes-to-this-reg on
  some parts), bits[7:4]+[14:12] = number of code comparators implemented (read to discover
  how many are available — **the F427 FPB typically implements 6 instruction comparators**;
  must be read at init, not assumed, since it's an implementation-defined field).
- `FP_COMP[n]` (`0xE0002008 + 4*n`): one per code comparator. Bit31 `REPLACE` field (for Flash
  Patch remapping, unused here), bits[28:2] = the comparator address (word-aligned instruction
  address to match, for Cortex-M4's FPBv1: match on bit[1] selects upper/lower halfword of the
  aligned word — the HAL wrapper in `hook.c` hides this and takes a plain function pointer),
  bit0 `ENABLE` for this one comparator.

Programming `FP_COMP[n] = (func_addr & FP_COMP_ADDR_MASK) | FP_COMP_ENABLE` with
`FP_CTRL.ENABLE = 1` makes the core raise a **debug event** when the instruction pointer
reaches `func_addr` — but critically, **not** a halting breakpoint: wired to the
**DebugMonitor exception** (not Halt mode) when `C_DEBUGEN` (halting debug) is *off* and
`DebugMon` is configured, this becomes a *maskable, software-vectored* exception just like any
other — so the target keeps running under RTOS control, no debugger attached, no SWD needed at
runtime (SWD only needed once, to initially flash/debug this code — §5).

### 3.2 `install_hook(func_addr)` / `release_hook(func_addr)`

```
install_hook(addr):
    n = allocate_free_comparator()      // table of in-use comparators, see hook.c
    FP_COMP[n] = (addr & COMP_ADDR_MASK) | COMP_ENABLE
    FP_CTRL   |= FP_CTRL_ENABLE | FP_CTRL_KEY
    record {n -> addr} in hook table
    return n  (or error: no free comparator)

release_hook(addr):
    n = lookup comparator for addr
    FP_COMP[n] &= ~COMP_ENABLE          // disable just this comparator
    clear hook table entry
    // leave FP_CTRL.ENABLE on if other hooks are still active
```

### 3.3 `DebugMon_Handler` — capture, then resume without re-triggering

Enabling: `SCB->DEMCR` (`0xE000EDFC`) bit **16 `MON_EN`** turns on DebugMonitor generation for
FPB/watchpoint matches; `SCB->SHPR3` sets `DebugMonitor`'s priority (configurable — see 4.1 for
why this matters); the handler is the standard exception-name override, `DebugMon_Handler`.

On entry, the **stacked exception frame** (pushed by hardware onto the current stack, pointed
to by the handler's own SP convention — read via the `MSP`/`PSP` that was active, selected by
`EXC_RETURN`/CONTROL.SPSEL at entry) holds, at increasing offsets: `R0, R1, R2, R3, R12, LR,
PC (return address), xPSR`. Since the match fires **at** `func_addr`, the stacked `PC` *is*
`func_addr` and `R0–R3` are exactly the function's first four arguments per AAPCS — no stack
unwinding needed, just read the frame.

```
DebugMon_Handler:
    frame = (ExcFrame *) (CONTROL.SPSEL ? read_PSP() : read_MSP())
    addr  = frame->pc                      // == the hooked func_addr
    n     = comparator index whose addr == addr   // which hook fired
    record = { timestamp = TIM2_now(), func = addr,
               r0..r3 = frame->r0..r3, lr = frame->lr }
    if hook[n].deref_len > 0:
        record.buf = safe_copy(frame->r0 /* or configured arg */, hook[n].deref_len)
                      // reuse readmem's fault-guarded copy — a hooked function could be
                      // called with a bad pointer; must not fault inside the handler
    ring_buffer_push(record)                // trace_pipe.c; lock-free SPSC, ISR-safe

    // --- resume without re-matching the same comparator immediately ---
    FP_COMP[n] &= ~COMP_ENABLE             // turn OFF this comparator
    DEMCR |= MON_STEP                      // bit 0: single-step the *next* instruction only
    pending_restore[n] = true
    return                                  // exception returns, executes exactly one instr
                                             // at func_addr, then DebugMon fires again (step)

DebugMon_Handler (step-completion case, pending_restore[n] true):
    FP_COMP[n] |= COMP_ENABLE               // re-arm
    DEMCR &= ~MON_STEP
    pending_restore[n] = false
    return
```

The single-step-then-rearm dance exists because the comparator, left enabled, would refire on
the very same instruction the core is about to retire (the PC hasn't moved past `func_addr`
yet at exception-return) — infinite retrigger. Disabling the comparator, stepping exactly one
instruction, then re-enabling is the standard FPB/DebugMonitor idiom for a non-halting
breakpoint. `hook.c` implements this as an explicit two-phase state machine per comparator
(`HOOK_ARMED` → `HOOK_STEPPING` → `HOOK_ARMED`), not a one-shot, because a second, *different*
comparator can legitimately fire while the first is mid-step — the state machine is per-slot.

### 3.4 Ring buffer → USB/DUML drain

`trace_pipe.c`: a lock-free single-producer (the exception handler)/single-consumer (a
FreeRTOS task) ring buffer of fixed-size trace records. The ISR-side push is O(1), non-
blocking, drops-on-full (counts drops, never blocks the exception). The consumer task wakes on
a counting semaphore/task-notify bumped by the push, batches available records into DUML
frames, and sends them over whichever transport the build selected (CAN1 `duml_send`, or USB).
This is the same transport-interface indirection as command A, so hook traces and read-mem
replies share one DUML TX path.

### 3.5 What to hook for each transport, and the point of hooking instead of stopping

The use case: watch DUML traffic flow without pausing the comms stack that carries it.

- **DUML send (framing layer, transport-agnostic):** hook `duml_send` (`0x0804f862`,
  `m0306.tsv` — **V**, "DUML transmit, 16 callers") — this is the single choke point every
  outbound DUML frame passes through regardless of which physical bus carries it, so one hook
  here sees all TX traffic. For the response-building path specifically, `duml_resp_build`
  (`0x08028d18`) or `duml_resp_send` (`0x0806d334`) are hookable instead/also if the goal is
  "what did the FC answer", with the request already decoded in the caller's frame.
- **CAN1:** the FC's CAN RX/TX happens through SPL `CAN_Init`-configured hardware FIFOs and
  mailboxes under interrupt (SPL identified at `can_init` `0x0803ae02` / `can1_bringup`
  `0x08035100`, `m0306.tsv`). There is no single named "can_rx_handler" symbol recovered yet
  in the TSV; the practical hook point is wherever the CAN RX ISR hands a completed frame up to
  the DUML parser (upstream of `duml_send`'s TX counterpart), or — more robustly — hook the
  DUML-level dispatcher that receives a fully-reassembled frame, since that's bus-agnostic and
  doesn't require pinning the exact ISR symbol.
- **UART/USART:** `usart_open` (`0x080343cc`) and `uart_port_init` (`0x08034c26`) are the
  bring-up functions (**V**, `m0306.tsv`); they are *not* good hook points (called once at
  boot, not per-byte/per-frame). The actual per-frame RX/TX path for a given UART (GPS, RC/DBUS,
  OSD) runs through each driver's own ISR, which the TSV does not yet name individually
  (`fc-io-inventory.md` marks exact UART roles **U**). Until those are symbolized, hook at the
  DUML layer above them (same rationale as CAN) rather than guessing an ISR address.
- **USB:** `usb_fs_bringup` (`0x0803aac4`) is again bring-up-only. USB OTG_FS on this part uses
  ST's USB device library callbacks (`PCD_*`/class `DataIn`/`DataOut` handlers) — not yet
  symbolized here; same guidance as UART: hook the DUML dispatcher rather than the raw USB
  stack until a specific ISR/callback address is confirmed.
- **Net effect:** `duml_send` is the one address in hand today that is **confirmed** (V) and
  **transport-agnostic**, so it is the first and best hook target for "sniff DUML traffic".
  Hooking the bus-specific RX/TX ISRs is the natural next step once those addresses are
  symbolized (an exercise for `docs/symbols/m0306.tsv` expansion, not blocking this design).

**Always release the hook when done.** `release_hook(duml_send)` disables that comparator;
normal execution timing resumes exactly as before (no residual overhead — a disabled
comparator costs nothing once cleared, and nothing else was modified). Never leave a hook
installed on a comms path across a flight-relevant test, and never install one on a
control-loop function at all (see caveats below) — this instrument's whole safety premise is
that it only watches comms/memory, never the control path.

## 4. Caveats and limits (honest list)

- **DebugMonitor cannot preempt equal- or higher-priority interrupts.** It is configured via
  `SCB->SHPR3` like any exception; if the function being hooked executes at/under an ISR whose
  priority is numerically ≤ DebugMonitor's configured priority, the debug event is **pended**,
  not taken immediately — the capture is delayed until that ISR returns, and timestamps/latency
  measurements taken from inside the handler will be skewed by that delay. Set DebugMonitor's
  priority as high (numerically low) as the system tolerates, but it still cannot win against
  something configured strictly higher — document, per hook, what priority the hooked function
  normally runs at.
- **Hooking adds latency to the hooked call** — the exception entry/exit plus the
  single-step-resume round trip is tens of cycles at minimum, more if the ring buffer push or a
  `deref_len` memory copy is involved. **Never hook a control-loop function** (attitude/rate
  loop, motor mixer, ESC output) — not because it's technically forbidden by the hardware, but
  because this instrument's whole bench-safety argument depends on it never touching anything
  timing-critical. **Never run any hook with props on.** This is enforced by convention (no
  control-loop symbol is ever a valid `install_hook` argument in this codebase; see the
  README's banned-address guidance) rather than by a runtime check, because a runtime address
  blacklist would need the full control-loop symbol set to be authoritative, which it isn't yet.
- **Limited comparators.** The F427 FPB's code-comparator count is read from `FP_CTRL` at
  startup, not hardcoded — expect on the order of 6 on this part family, which bounds
  simultaneous hooks to that count minus any FPB usage by other debug tooling. `hook.c`'s
  `allocate_free_comparator()` returns an explicit "no free slot" error rather than silently
  overwriting another hook.
- **Single-step-resume race.** Between "disable comparator, enable MON_STEP" and the step
  actually completing, an *interrupt* can land on the stepped instruction's context; this is
  normal (it's just an instruction boundary) but means the "one instruction" may itself be
  interrupted — correctness isn't affected (the step still completes before further progress
  at that PC), but the *measured* gap between hook-fire and resume can include an arbitrary
  ISR's duration. Not a safety bug, a measurement-fidelity caveat.
- **Needs the SWD port free for anything *other* than this mechanism.** DebugMonitor mode and
  halting-debug (SWD breakpoints via `C_DEBUGEN`) are mutually exclusive ways to use the same
  FPB hardware — if an SWD debugger is attached and has halting-debug enabled, it owns the FPB
  comparators and this code's `install_hook` will conflict with/be overridden by the external
  debugger's own use of them. This tool is specifically the way to get hook-style tracing
  *without* consuming the SWD connection, so a bench session can have both an SWD session (for
  initially flashing/debugging this very instrument) and, once SWD is detached, this tool's
  own independent use of the same comparators — but not both at once.
- **BusFault guard interacts with the hook mechanism** only in that both use exception-level
  code; they are independent exception types (`BusFault_Handler` vs `DebugMon_Handler`) with no
  shared state beyond both being core-exception-priority code, so no special ordering is
  required between Commands A and B.

## 5. Bench-safety summary

Scope & safety: see `SAFETY.md`.
