# fc/instrument — STM32F427 bench instrumentation tool

```
================================================================================
  BENCH DIAGNOSTIC ONLY — PROPS OFF, NO FLIGHT.
  This is NOT flight firmware. It initialises no motor/ESC driver and runs
  no control loop. It exists to read memory and trace comms-function calls
  on the bench, on the operator's own Phantom 3 Pro flight controller
  (m0306, STM32F427). Do not fly on this image/payload. Do not install a
  hook on any control-loop/motor-mixer/ESC-output function. See
  docs/fc-instrument-design.md section 5 for the full safety summary.
================================================================================
```

## What's here

| File | Design doc section | Purpose |
|---|---|---|
| `readmem.h` / `readmem.c` | §2 | Command A: DUML read-any-memory, with a static-whitelist guard and a (TODO-marked) BusFault-catching guard. Read-only by construction — no write entry point exists. |
| `hook.h` / `hook.c` | §3 | Command B: FPB comparator + DebugMonitor exception hook manager — `install_hook`/`release_hook`, the handler, the single-step-resume state machine. |
| `trace_pipe.h` / `trace_pipe.c` | §3.4 | Lock-free SPSC ring buffer (ISR producer, FreeRTOS task consumer) draining `hook_record_t`s out over the shared transport interface. |
| `README.md` | — | This file. |

Full rationale, the register bit-fields, the BusFault/DebugMon exception
mechanics, the "which function to hook for CAN/UART/USART/USB" guidance, and
the caveats list all live in **`docs/fc-instrument-design.md`** — read that
first; this README is build/integration notes only.

## How this maps to the design doc

- §1 (target/build model) → the transport-interface split: every file here
  calls a plain `(const uint8_t *bytes, uint16_t len)` send function
  (`fc_instrument_send_fn`), installed via `readmem_set_transport()` /
  `trace_pipe_set_transport()`. The two build modes (clean-room app, or an
  appended patch payload calling the stock `duml_send` at `0x0804f862`)
  differ only in what that one function does. Neither `readmem.c`,
  `hook.c`, nor `trace_pipe.c` contains any DUML framing — that is
  intentional, so the same handler code works unmodified in either mode.
  DUML framing (SOF `0x55`, CRC8 seed `0x77`, CRC16 seed `0x3692`) belongs
  in the glue code around whichever transport function you provide, mirror
  the already-verified codec in `app/packages/duml` (Dart) or
  `rust/awto_dji_core` (Rust).
- §2 → `readmem.h`/`.c`.
- §3 → `hook.h`/`.c`, `trace_pipe.h`/`.c`.
- §4/§5 (caveats, bench-safety) → enforced partly by code (read-only
  `readmem`, explicit error statuses instead of crashing) and partly by
  **convention + this banner**, not by a runtime address blacklist — see
  "Banned hook addresses" below for why and what's still a TODO.

## Build notes

This code is written to be **structurally and logically correct** against
the real Cortex-M4/FPB/DebugMonitor register semantics, but it does **not**
build as-is: every piece that needs the real toolchain, CMSIS headers,
FreeRTOS, or hand-written assembly is marked `TODO(bringup)` inline. The
main ones, gathered here for a bring-up pass:

1. **`readmem.c`**: the actual fault-recovery sequence inside
   `BusFault_Handler` (fixing up the stacked exception frame's PC) needs a
   small recognizable assembly probe helper and real vector-table/weak-
   symbol wiring — sketched in comments, not yet written in asm.
2. **`hook.c`**: `DebugMon_Handler` needs a naked-asm trampoline to recover
   the correct stack pointer (MSP vs PSP, from `EXC_RETURN`/`LR` bit 2)
   before calling into `debugmon_c_handler()` — sketched in comments.
   Also: `DEBUGMON_PRIORITY_PLACEHOLDER` must be set against this
   firmware's real interrupt priority map, not left at its placeholder
   value, before relying on timing results (§4.1's preemption caveat).
3. **`trace_pipe.c`**: FreeRTOS semaphore calls are forward-declared, not
   `#include <FreeRTOS.h>`'d, and the ISR-vs-task-context semaphore API
   (`...FromISR`) needs to be the one actually used from `hook.c`'s
   exception-context caller — flagged inline where it matters.
4. **Framing**: every outbound byte stream in this directory is raw
   `(bytes, len)` — wrap in real DUML frames in the glue layer, per the
   transport-interface note above.
5. **Command dispatch wiring**: nothing in this directory registers
   `readmem_handle_request` / `install_hook` / `release_hook` against an
   actual DUML command ID yet — that's the integration glue for whichever
   build mode (clean-room DUML dispatcher, or the appended-payload's
   repointed `FlycExportParam` callback / `nullsub_*` stub per
   `docs/fc-replacement-plan.md` and `docs/fc-bootloader.md`'s "Approach-B
   hijack candidates").

None of the above changes the register-level logic (FP_CTRL/FP_COMP bit
layout, DEMCR bits, the whitelist table, the resume state machine) — that
part is written to be correct now and reviewable now; the TODOs are purely
hardware/toolchain bring-up work.

## Banned hook addresses — current status

`install_hook()` in `hook.c` does **not** currently check `func_addr`
against a control-loop/motor-path address list before arming a comparator,
because no such list is yet authoritative in `docs/symbols/m0306.tsv` (the
symbols recovered so far are comms/config/mission-layer, not the
rate-loop/mixer internals). The safety constraint "never hook a
control-loop function" is therefore enforced **today only by this banner
and by the operator's own judgement about what address they pass in** —
not by code. This is flagged explicitly (see the `TODO(bringup, policy)`
comment in `install_hook`) rather than silently assumed solved. Before
this tool is used beyond "hook `duml_send` and release it again", either:

- expand `docs/symbols/m0306.tsv` with the control-loop/motor-mixer
  addresses so `install_hook` can reject them outright, or
- keep manual discipline and only ever hook the comms-layer addresses
  listed in `docs/fc-instrument-design.md` §3.5 (`duml_send 0x0804f862`
  and whichever comms dispatcher you've symbolized since).

## Recovery

Both build modes leave the stock loader (flash sectors 0–4, `0x08000000`)
untouched (per `docs/fc-bootloader.md`), so recovery in either mode is: **reflash
stock `m0306` via DJI Assistant 2**. There is nothing in this directory
that can brick the loader itself.
