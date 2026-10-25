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

## FC external-control API recovered (2026-10-25, Ghidra + decrypted strings)

The decrypted image keeps `[SDK/USER]`/`[USER]` debug strings that name each handler. Naming
functions from the string they log (`scripts/re/ghidra/fc_apimap.py`, 15 handlers) gives the
FC's **onboard/external control surface** — this is the DJI Onboard-SDK-style API baked into
the FC (`docs/symbols/m0306.tsv`):

- **Control authority / mode**: `fc_api_ctrl_mode_cmd_status_request` (0x08055cb8),
  `fc_api_ctrl_mode_serial_open_nav` (0x08055b9c, "open navigation" = external control),
  `fc_api_ctrl_mode_emergency_brake_handler` (0x08055b2e). Logs show a request/grant model:
  `REV REQ CMD AND SET AGENCY`, `SEND ACK REQ CMD REFUSE` — the FC can *refuse* a control
  request, and tracks an "agency" (who holds control).
- **Go-to / waypoint**: `fc_api_mission_planner_wp_set_info` (0x08055d48),
  `..._wp_data_upload` (0x08055d8a), `..._wp_request_cmd` (0x08055dbe).
- **Hotpoint / Follow-me missions**, `GH_SET_TAKEOFF_HEIGHT`, `ACT.Takeoff`, `landing.API_landed`.
- **Activation / key**: `fc_sdk_set_key` (0x08046e86), `reg_user_activation` — an activation
  gate likely sits in front of the control API (consistent with DJI SDK activation).

So the FC **does** expose position/waypoint and external-navigation control, behind a
request→grant "agency" authority model with activation. This maps onto the companion-agent
plan: drive these `api_ctrl_mode_*` / `api_mission_planner_*` handlers.

**Still open (next):** (1) read `fc_api_ctrl_mode_cmd_status_request` to see **what it checks
before granting** — sender device-type, activation state, RC mode — the key question for both
the onboard-agent and the patch paths; (2) the continuous-setpoint command path (joystick /
`serial_open_nav`) payload; (3) which bus the requests arrive on (USART vs CAN) using the SVD
MMIO labels.

## Control-authority gate decompiled (2026-10-25) — answers the sender-check question

`fc_api_ctrl_mode_status_request_handler` (0x08055680) is the grant/refuse logic. To grant
external control it requires, in order:
1. `fc_ctrl_register_requester` (0x0805cb70) resolves the sender via `fc_sender_channel_lookup`
   (0x0804748c); returns 0 (reject) only if that is `0xff` (unknown channel/device). It indexes
   a per-device-type table by `(sender>>16)&0x1f` and records the requester. **Validity check,
   not an identity allowlist.**
2. No other active "agency" holds control (or it is the same requester).
3. **`fc_ctrl_gate_mode_read` (0x08064d38) == 2** — a single RAM mode byte at `0x200001d5`,
   written by `fc_ctrl_mode_set_a/b` (0x08064c9c/0x08064d9c) from the RC/flight-mode state.
   Its value is even printed in `SEND ACK REQ CMD REFUSE`.

On grant it sets the agency holder, `*(mode_struct+0x20)=1`, and ACKs 2; otherwise ACKs 1.

**Answer to "can the FC be controlled from an onboard sender":** structurally yes — the FC
accepts a control request from any sender that (a) arrives on a channel its lookup accepts and
(b) while the mode-gate byte is 2. It does **not** check the requester against an identity
allowlist. The deciding factor is the mode gate (RC switch / flight mode), not the origin.
- **Companion-agent path:** the A9-originated request must come in on an accepted channel and
  the mode gate must read 2. Both are testable on hardware.
- **Patch path:** the gate is one compare (`== 2`) behind `fc_ctrl_gate_mode_read`; but the
  module is AES-encrypted and whole-image load integrity (m0305/bootloader) is not yet assessed.

Not yet done: the continuous-setpoint (joystick / `serial_open_nav`) payload, and what sets the
mode byte to 2 (confirm it is the RC mode switch).

## How to use the FC control API (enable chain, 2026-10-25)

Working within the stock API (no patching). The enable chain, decompiled:

1. **Arbitration** `fc_ctrl_arbitrate` (0x08064c9c) scans a 2-entry priority table (0x080ef3d8):
   device code 1 (pred 0x08064c88) and device code 2 = API/nav (pred `fc_ctrl_src2_pred_api`
   0x08064c92). The first predicate returning 1 wins; its code becomes the gate byte 0x200001d5.
2. **API/nav becomes active (code 2)** iff `fc_ctrl_src2_pred_api` returns 1, i.e.
   **bit 2 of the mode-flags byte at 0x200001d6 is set**. (What sets that bit — RC mode switch
   position vs an app/activation request — is the one remaining unknown in the chain.)
3. **Request agency**: `fc_api_ctrl_mode_status_request_handler` (0x08055680) grants only while
   the gate byte == 2 and the sender resolves to a valid channel (no identity allowlist).
4. **Open navigation**: `fc_api_ctrl_mode_serial_open_nav` (0x08055b9c) opens the nav channel,
   and only succeeds when the active device is already 2.
5. **Then** drive `fc_api_mission_planner_wp_*` (waypoint go-to) / joystick / hotpoint / follow.

So for the onboard agent: get the aircraft into the state that sets flags-bit 2 (the API
control condition), request agency on an accepted channel, open nav, then stream setpoints.
No firmware change required if that bit can be set the normal way.

## Next step (proper disassembly, not one-line scans)

Trace from a byte entry point to the dispatch, following indirect calls:
`USART1 ISR 0x0803a45d → RX ring → frame assembler → (DUML validator 0x080304fc) → handler
registration table → set-0x03 handlers`. This is a Ghidra-scale job on the decrypted image
(decompile + xref graph); the capstone one-liners here located the anchors but not the full
graph. Once the set-0x03 handler cluster is found, enumerate IDs and read each handler's inputs
(which read height/range/GPS state) at the message level only.
