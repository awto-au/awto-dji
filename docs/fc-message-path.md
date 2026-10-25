# m0306 (flight controller) message handling — entry points and DUML path

Scope: find how the FC receives and dispatches DUML, what it accepts, and whether it checks the
sender — treating IMU/fusion/motor code as a black box. Tags: **V** verified, **I** inferred,
**U** unknown. Base `0x08020000`, Thumb-2, µC/OS.

## Prerequisite: m0306 is AES-encrypted in shipping firmware (V)

m0306 in P3 1.11.0020 is `encrypt_type=1` (module AES-128). The raw module is 8.0-entropy; the
real code only appears after decryption. Decrypt with the public DJI module key:

```
python3 scripts/re/xv4_decrypt.py P3X_FW_V01.11.0020.bin m0306 m0306_dec.bin
```

Verified: output MD5 matches the xV4 entry's `decrypted_md5`; vector table SP `0x2002ff00`,
reset `0x08021965` (matches `code-provenance.md`). All addresses below are in the decrypted image.

## Byte entry points (V, vector table)

Received bytes enter through interrupts; the FC populates both CAN controllers and several
USARTs:

| IRQ | Peripheral | ISR | Likely peer (I) |
|---|---|---|---|
| 19/20/21 | CAN1 RX0/RX1/SCE | `0x08035301` / `0x0803530f` / `0x08035359` | gimbal / ESC / center board |
| 63/64 | CAN2 RX0/RX1 | `0x080355bd` / `0x080355c9` | second CAN segment |
| 37 | USART1 | `0x0803a45d` | link side toward m0900 (app/RC DUML) |
| 38/39 | USART2/USART3 | `0x0803a463` / `0x0803a469` | GPS / other sensors |
| 52/53/71/82/83 | UART4/5/USART6/UART7/8 | `0x0803a46f` … `0x0803a487` | sensors / debug |

So the FC is a multi-bus DUML node. App/RC commands arrive from m0900 (which routes FC-type
traffic out its USART1, `m0900-can-channels.md`) into one of these — most likely USART1 (I).

## DUML framing and validation (V)

- **CRC16 function** `0x0804f024`: standard DUML CRC16, table at `0x080ef734` (pool word
  `0x0804f0a8`). 19 call sites.
- **Frame CRC validator** `0x080304fc(buf, len)`: computes CRC16 over `len-2` and compares the
  trailing u16; returns 1 on match. This is the DUML integrity gate.
- **A second, internal framing** uses `0xAB … 0xCD` markers (`0x080304e2`) alongside DUML's
  `0x55` — I: inter-MCU/CAN transport vs the external DUML `0x55` frames.
- **Response build + send**: e.g. `0x08028d30` assembles a frame (writes `0xAA` markers,
  recomputes CRC16 via `0x0804f024`, sends via `0x0804f862`).

## Not yet resolved (the actual command map)

- **The (set, id) → handler dispatch is not a flat table.** Scans for `{set,id,handler}` arrays
  found only a false positive (instruction bytes at `0x080A60EC`). Dispatch is a switch
  (`tbb`/`tbh`) or a registered per-channel callback — the DUML validator `0x080304fc` has no
  direct `bl` callers, so it is invoked via a function pointer / handler-registration table.
- Consequently the **go-to / position vs attitude / velocity command IDs**, their payloads, and
  **whether the handler checks the sender byte** (the key question for both the companion-agent
  and the FC-patch paths) are **U** from static work so far.

## Ghidra pass (2026-10-25): setup done, DUML primitives named, dispatch is table-driven

Decrypted m0306 imported into Ghidra 11.4 (Raw Binary, ARM:LE:32:Cortex, base 0x08020000),
auto-analysis = **3969 functions**. STM32F427 SVD applied (1574 MMIO registers labeled) and
known symbols seeded — tooling in `scripts/re/ghidra/` (fc_setup.py applies SVD+names,
fc_dispatch.py hunts the dispatcher), named set in `docs/symbols/m0306.tsv`.

Findings:
- `duml_crc16` (0x0804f024) has 16 call sites; `duml_send` (0x0804f862) 16; `duml_resp_build`
  (0x08028d18) builds + CRCs + sends a response. These are the DUML primitives (V).
- The DUML frame validator (0x080304fc) has **zero references** — inlined at each call site,
  not a shared callee.
- The only large `switch`-based function in the crc16 call graph, `FUN_08031062` (10 switches),
  dispatches an **internal event queue keyed on u16 type codes 0x29xx** — not the DUML (set,id)
  surface. So the DUML command dispatch is **table-driven** (handler lookup by set/id), which is
  why it shows no switch and the validator has no refs.

## Next step (proper disassembly, not one-line scans)

Trace from a byte entry point to the dispatch, following indirect calls:
`USART1 ISR 0x0803a45d → RX ring → frame assembler → (DUML validator 0x080304fc) → handler
registration table → set-0x03 handlers`. This is a Ghidra-scale job on the decrypted image
(decompile + xref graph); the capstone one-liners here located the anchors but not the full
graph. Once the set-0x03 handler cluster is found, enumerate IDs and read each handler's inputs
(which read height/range/GPS state) at the message level only.
