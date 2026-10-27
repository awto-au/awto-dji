# UART/SPI inventory and speed cross-check, air + ground

Prompted by a direct question: for every UART/SPI link we claim exists between two chips, do
we actually have **both** ends independently measured, and do the speeds match? Answer, bluntly:
**almost never.** Every hop below has at least one side that is inferred/assumed to match the
other, not independently confirmed. This doc exists to make that visible in one place instead of
scattered across a dozen docs, each individually honest but none showing the whole chain at once.

Tags: **V** verified (both ends independently measured and compared), **V (one side)** one chip's
own code/behavior measured directly, the peer's matching value assumed not confirmed, **I**
inferred, **U** unknown. Cross-reference docs are cited per row.

## Air side

| Link | End A (measured) | End B (measured or assumed) | Speed match? | Tag |
|---|---|---|---|---|
| `air_router` USART1 ↔ `air_fc` | m0900: `USART1`, 256000 nominal / **256228 baud actual** (`dataflow.md`) | `air_fc` has **8** UARTs (`USART1/2/3, UART4/5/7/8, USART6`, `fc-io-inventory.md`); **none of them has been identified as the one receiving this traffic**, and none has had its baud independently measured for this purpose | **Not confirmed — genuinely unknown which `air_fc` UART this is, let alone its baud** | V (one side only) |
| `air_router` USART3 ↔ air FPGA | m0900: `USART3`, 256000 nominal / **257143 baud actual**, DMA, IDLE-framed RX (`dataflow.md`, `fpga-pinout-model.md`) | FPGA bitstream is undecoded (`fpga-images.md`) — the FPGA-side UART config can't be read directly; assumed to match **by elimination** (it must, for the link to work at all), not measured | Assumed, not measured | V (one side only) |
| `air_router` SPI2 ↔ air FPGA | m0900: mode 1, 4.5 MHz, 3-byte frames, CS PB12 (`m0900-buses.tsv`, `fpga-bringup.md`) | Same limitation — FPGA-side SPI slave config can't be read from the bitstream | Assumed, not measured | V (one side only) |
| `air_router` USART2 (board 7 only) | Exists, DMA-backed, confirmed this session's systematic pass (NVIC/IRQn table) | **Baud never measured or stated anywhere.** Feeds the same CAN-0x413 parse path as the main CAN pump on board 7 (`m0900-can-channels.md`) — role known, speed U | Unknown on both sides | U |
| `air_venc` (DM368, m0800) `/dev/ttyS1` | **115200 baud, confirmed this session** (traced `Enc_Serial_Init` → `Serial_Create` → the actual termios lookup table in `libcommon.so`) — real number, not assumed | **No peer has ever been identified.** Not `air_router` (its 3 USARTs are already fully assigned: FC, FPGA, board-7 aux — no spare UART for this). Not confirmed to `air_fc` either. `m0800-dm368-provenance.md` already marked this `U` before this session; still `U` | **Completely open — this is the gap worth chasing, see below** | U |
| `air_cam` (A9, m0100) `ttyS2` | Linux console (`console=ttyS2` kernel cmdline), **not a DUML link** — a BusyBox root shell respawns on it forever (`camera-linux-console-access.md`) | n/a | n/a — this one isn't part of the DUML mesh at all | V (role), not DUML |
| `air_cam` (A9) "UART0"/"UART1" (Ambarella SoC UARTs) | Strings found near a UART↔USB-CDC bridge function; which physical UART (0, 1, or `ttyS2` itself) gets bridged is **U** (`camera-linux-console-access.md`) | — | — | U |
| `air_cam` (A9) DUML channels | `air-id-and-stream-survey.md`: `DjiMsgChannelInit` sets up "**UART channels** (plural) + an IPC channel" for DUML — i.e. the camera SoC has more than one of its own UARTs doing DUML, separately from `ttyS2`'s console role, and **separately from `ttyS1`** (that's DM368's port, not A9's) | Not individually mapped to physical ports or peers | Open | U |
| `air_cam` CAN (types 1/4/8/15, incl. camera device type 8) | `air_router` passes these types through on CAN `0x412`/`0x413` without inspecting them — confirmed, verified-negative (`air-router-deep-dive.md` §6) | The camera-side CAN transceiver/driver has not been independently located in the A9 or DM368 firmware this session | The bus exists and is used; which chip actually drives it electrically is unconfirmed | V (router side only) |

## Ground side

| Link | End A (measured) | End B (measured or assumed) | Speed match? | Tag |
|---|---|---|---|---|
| ground FPGA ↔ `gnd_rc` (m1400) | — | — | DUML over a UART, **inferred only (`I`), no baud measured on either side** (`dataflow.md`, `ground-fx3-m1601.md`) | I |
| `gnd_rc` (m1400) ↔ `gnd_fx3` (m1601) | FX3 side: **115200 8N1, confirmed in FX3 code and a real capture** (`ground-fx3-m1601.md`) | m1400's matching UART/baud is **assumed to be 115200 to match**, not independently measured from the m1400 firmware itself | Assumed, not measured | V (one side only) |

## The honest summary

Across the **entire air+ground DUML mesh**, there is exactly **one link with a number on both
sides that was independently derived and actually compared**: the ground FX3's 115200 baud is a
real measurement, and `m1400`'s side is assumed to match (not unreasonable — the link visibly
works on real hardware — but still assumed, not measured from `m1400`'s own code). Every other
hop has at most one side measured. None has had both sides independently derived from their own
firmware and shown to agree down to the actual baud-generator value (the way `air_router`'s own
256228/257143 "actual vs nominal" distinction was derived for its own two UARTs).

**The specific gap worth chasing, per the question that prompted this:** `air_venc`'s (DM368)
`/dev/ttyS1` at a confirmed 115200 baud has **no identified peer at all** — not assumed-and-
unmeasured like the others above, genuinely *no candidate chip has been named*. The DUML-in-video
question this session re-confirmed (independently decompiled `AddSerialDataToFrame`, confirmed
dead code — see `m0800-dm368-provenance.md` §7 and the correction below) answers "does DUML ride
inside the H.264 stream" (no), but that is a *different* question from "where does the DUML control
link on `ttyS1` physically go." Three live candidates, none eliminated:

1. **The A9 camera SoC (`m0100`)**, over a short local UART pair on the same gimbal/camera board —
   plausible given `air-id-and-stream-survey.md`'s note that the A9 has its own "UART channels
   (plural) + IPC channel" for DUML, one of which could be this exact link. Not confirmed from
   either side.
2. **A dedicated UART↔CAN bridge chip** on the camera/gimbal board, electrically separate from
   both DM368 and A9, that puts the camera's DUML (device type 8) onto the CAN bus `air_router`
   is already known to pass through untouched. No such chip has been found in any firmware
   examined so far (DM368 and A9 are the only camera-side firmware images this project has).
3. **Unconnected / debug-only** — possible but less likely given `Enc_Serial_Init` runs
   unconditionally at boot and the protocol (`enc_serial.c`'s command/ack framing) looks like a
   real, actively-used control channel, not vestigial code (unlike the confirmed-dead
   `AddSerialDataToFrame`).

Resolving this needs either a physical continuity/logic-probe check on the real gimbal/camera PCB,
or extracting and checking the A9's own `sys` partition for a UART open call whose baud matches
115200 and whose device path plausibly pairs with DM368 — not attempted this session.

## Re-verification: DUML is not spliced into the video stream (re-confirmed independently, 2026-10-25)

The existing finding in `m0800-dm368-provenance.md` §7 ("the DM368 does not put serial data in
the video... the function is dead code") was re-checked from scratch this session, independently,
with fresh tooling (`pyelftools` + `capstone` against the real `encode_usb` binary), not by
re-reading the old conclusion:

- Decompiled `AddSerialDataToFrame` (`0x127e0`) directly. It calls `Enc_Serial_Fill_Forward_Data`
  to get a byte count, then — every 15th call — either prints a header via `printf` or loops
  byte-by-byte through `puts`-style calls. **This is debug-logging code** (it calls `printf`/
  `puts`, resolved via the dynamic symbol table — `0xbdd0`=`printf@GLIBC_2.4`, `0xbefc`=
  `puts@GLIBC_2.4`), not a function that writes bytes into an H.264 frame buffer for transmission.
- Searched the **entire** `.text` section of `encode_usb` for any `bl` instruction targeting
  `0x127e0` (`AddSerialDataToFrame`'s address). **Zero hits.** Nothing in this binary calls it.
- **Conclusion unchanged, confidence raised**: this is genuinely dead/unreachable code that would,
  if ever called, print serial-related debug text — not splice DUML bytes into the video payload.
  The earlier doc's finding holds up under an independent re-check, not just a repeated assertion.

## Reproduce

- `ttyS1` baud: traced `Enc_Serial_Init` (`encode_usb`, symbol table offset `0x151fc`) →
  `Serial_Create("/dev/ttyS1", 3, 1, 0)` → followed the baud-enum lookup table inside
  `Serial_Create` (`libcommon.so`, `0x67fc`) to its two literal-pool tables (keys `0,1,2,3,4` →
  `Bxxxx` constants `0xd,0xe,0xf,0x1002,0x1003` = 9600/19200/38400/115200/230400); enum `3` →
  `0x1002` = `B115200`. Used `pyelftools` for VA→file-offset resolution (per-section, not a single
  blind `.text`-relative offset — that was this session's one real bug, caught and fixed) and
  `capstone` (`CS_ARCH_ARM, CS_MODE_ARM`) for disassembly, both already available in this
  environment.
- `AddSerialDataToFrame` dead-code re-check: same toolchain, decompiled `0x127e0`-`0x12930`,
  resolved its two `bl` targets via the dynamic symbol table (`objdump -t`/`-T`), then scanned the
  whole `.text` section for any `bl #0x127e0` instruction (none found).
- Files used: `scratchpad/m0800/x/dji/bin/encode_usb`, `scratchpad/m0800/x/dji/lib/libcommon.so`
  (already-extracted copies from this session's working directory; not re-extracted).

## Caveats on the SPI2 and USART3 peers (added 2026-10-27, from a 2026-10-25 session)
- All evidence that the SPI2 peer is the FPGA and the USART3 peer is the FPGA UART is firmware-only. No schematic, board photo or probe confirms it. The operator states, from the circuit, that it is the FPGA (W, operator claim, not independently checked).
- GPS is not on the FPGA UART (I): `GetPushGpsInfo` (set 0x06 cmd 0x1b) is addressed to receiver type 3, which routes to USART1. Receiver types 2, 6, 13, 14, 16, 20 and 22 are the ones muxed onto USART3.
