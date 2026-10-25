# Front micro-USB (m0306 / `air_fc_stm32f427` flight controller): why it never answers DUML

Firmware: `P3X_FW_V01.11.0020_m0306.bin` (STM32F427IIH6, app base `0x08020000`, SP
`0x2002ff00`, reset `0x08021965`, RTOS strings identify **Micrium uC/OS-III**). Reproduce
disasm: `python3 scripts/re/mcu_trace.py --img firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin
--base 0x08020000 --load 0x08020000 dis <addr> <n>`.
Scope & safety: see `SAFETY.md`.
Tags: **V** verified (code/Renode), **I** inferred, **U** unknown.

## Headline finding

**V.** All five USB-OTG NVIC vectors point at the CPU's `Default_Handler`, which is a bare
infinite self-loop — not CDC/DUML code of any kind:

| Vector | IRQn | Vector-table offset | Handler |
|---|---|---|---|
| OTG_FS_WKUP | 42 | `0x08020000+0xe8` | `0x080219a1` |
| OTG_HS_EP1_OUT | 74 | `+0x168` | `0x080219a1` |
| OTG_HS_EP1_IN | 75 | `+0x16c` | `0x080219a1` |
| OTG_HS_WKUP | 76 | `+0x170` | `0x080219a1` |
| OTG_HS | 77 | `+0x174` | `0x080219a1` |

(odd = thumb bit; aligned target `0x080219a0`, disasm: `b #0x80219a0` — self-branch.) By
contrast USART1/2/3 (IRQn 37/38/39), TIM6/7 (56/57), UART4/5 (82/83), DMA2_Stream7 (71) each
point to a distinct real handler — a table of 6-byte `movs r0,#IRQn; b.w #0x803f6ec` stubs at
`0x0803a45d`-`0x0803a511` (a generic RTOS ISR-entry trampoline, one per serviced IRQn) — so
this firmware does implement real interrupt handling elsewhere; USB OTG is a genuine,
deliberate gap, not an artifact of the search method.

**V (Renode, dynamic confirmation).** Forced NVIC enable+pend on OTG_HS (IRQn 77), since Renode has no STM32 OTG device-controller peripheral model. Same "forced register state instead of full peripheral emulation" method used for m0900's AD9363 SPI writers, `docs/fpga-bringup.md`.
- Commands: `sysbus WriteDoubleWord 0xE000E108 0x2000` (ISER2 bit13) then `0xE000E208 0x2000` (ISPR2 bit13), `emulation RunFor "00:00:00.001"`.
- Result: `cpu PC` = `0x080219a0` and stays there after another 1ms step. The CPU parks in `Default_Handler` permanently the instant any OTG_HS interrupt is actually taken, exactly as the static disasm predicts.
- Reproduce: `python3 scripts/re/m0306_probe.py` (log `tmp/logs/m0306_probe.log`); platform `renode/platforms/m0306.repl`.
- The platform extends stock `platforms/cpus/stm32f429.repl` (closest public SVD match to the real F427). Unlike m0900's F103 it did not need an RCC_CFGR tag workaround, since the stock F4 repl already models `STM32F4_RCC`.

## Does the firmware ever even arm USB OTG at the NVIC?

**V (Renode).** Booted the real image from its own reset vector, then read NVIC `ISER1`
(`0xE000E104`) / `ISER2` (`0xE000E108`) at t=2000ms simulated (`renode/scripts/
m0306_probe_long.resc`, log `tmp/logs/m0306_probe_long.log`): `0x871018A1` / `0x000803F3`.
Decoded enabled IRQn set: `{32,37,39,43,44,52,56,57,58,63,64,65,68,69,70,71,72,73,83}` —
USART1(37)/USART3(39)/TIM6(56)/TIM7(57)/UART5(83)/DMA/I2C channels are all armed (positive
control: normal driver init *did* run by this point) but **none** of OTG_FS_WKUP(42) /
OTG_HS_EP1_OUT/IN(74/75) / OTG_HS_WKUP(76) / OTG_HS(77) are ever present, at any of the
sampled points up to 2s simulated boot. So the gate is two deep: even if the dead vector
weren't dead, the firmware never unmasks the interrupt that would reach it.

**V (Renode, side note, not chased further).** By t=2000ms the CPU was found spinning in an
SD-card status poll (`PC 0x0805b102`, reading `SDIO:STA 0x40012C34`, which Renode's generic
SVD model always returns as `0`) — an environment-dependent stall, the same category as
m0900's board-strap gate, just for an SD logger rather than a radio. Flagged as open; all the
non-USB peripherals above were already armed before this point, so it's unlikely to be
hiding a later USB-enable, but not proven.

**V (Renode).** At the earlier 50/100/150/200ms samples (`renode/scripts/m0306_probe.resc`,
log `tmp/logs/m0306_probe.log`) PC was pinned at `0x0806816c` (`b #0x8068154`), a tight loop
calling two helpers then a third, immediately adjacent to a function that references the
literal string **"uC/OS-III Idle Task"** (`0x0806854c`) — this is the RTOS's own idle task,
i.e. "nothing else is runnable yet", not a hang; ISER was still all-zero at this point, which
is why the longer run above was needed.

## Is USB OTG initialized at all?

**V (static call graph).** Yes, once, at boot, not from a loop. Two independent one-shot
chains, both starting a handful of instructions after reset (`0x08021965`):
- `~0x0802023a → 0x08081f60 → 0x08087c04 → 0x08037cb8 → 0x0803c91c → 0x0803c094`
  ("select USB core": a library function parameterized by core id, 1 = OTG_FS @
  `0x50000000`, else = OTG_HS @ `0x40040000`).
- `0x080202e2 → 0x0806ffac → 0x08087d22 (tail) → 0x08087c26` ("device start"), called twice
  from inside `0x08087d22` and from nowhere else.

`0x40040000` has exactly **one** literal-pool reference in the whole 885 KB image (inside the
"select core" function above); `0x50000000` (OTG_FS) has **zero** — confirms OTG_HS
(embedded FS-PHY) is the core actually wired up, and that the whole USB stack is linked-in,
live, boot-time-only code, not dead library cruft. This explains why the port enumerates and
DTR/RTS get asserted on real hardware (`tmp/logs/probe_fc_usb.log`): a one-shot
init/enumerate sequence runs; nothing then services it again.

## What the "DJI CONTROLLER" / "VCOM" / "MSCM" strings turned out to be

**V.** Not receive-path code. File `0x84ab4` (`addr 0x080a4ab4`): two RAM pointers
(`0x2001ccec`, `0x200297f8`) followed by fixed-width string fields — `"DJI CONTROLLER\0"`
(`0x080a4abc`), `"DJI\0"` (`0x080a4acc`), `"0001A0000000\0"` (`0x080a4ad0`), `"VCOM\0"`
(`0x080a4ae0`), `"MSCM\0"` (`0x080a4ae8`). ~12 tiny functions at `0x080a49ce`-`0x080a4ab4`
each call one copy helper (`bl 0x08037b36`) to copy one field into the RAM struct — these are
the descriptor-string **initializers** run during the boot-time USB init above, not a
CDC_Receive-equivalent. `fc_usb_xrefs.py` found zero literal-pool refs to the *string*
addresses themselves (`tmp/logs/fc_usb_xrefs.log`) because code addresses the struct by its
RAM base, not by re-loading each string's flash address — a dead end worth recording so it
isn't re-walked.

## Interpretation (not proven by code)

**I.** `"VCOM"` vs `"MSCM"` read as two USB personalities (CDC-ACM vs mass-storage).
- `"Assistant protect"` / `"assistant connect changed:last(%u) != current(%u)"` / the config key `"assistant_timeout_0"` (all string-verified, V for existence) look like a boot-time "Assistant window".
- Known DJI A3-family behavior: a short post-power-on window during which DJI Assistant PC software can attach; after a timeout with no handshake the firmware moves on.
- Combined with the Renode findings above, the likeliest explanation for "accepts bytes, never replies": the probe connects to a FC that is **already past** that window (or one that, in this firmware image, never enables OTG-interrupt service at all).
- The hardware OTG peripheral still ACKs USB transport-layer traffic (control transfers for enumeration, bulk-OUT framing) regardless of software, but nothing ever reads the result into a DUML parser.
- **Not verified**:
  - the actual content of the one-shot boot init (I did not find/trace the consumer of `assistant_timeout_0`, nor a receive-processing function reachable from either call chain above);
  - whether the operator's physically connected FC runs this exact firmware build (image `.ini` version `02.04.5170`; other P3X FC images checked in `docs/air-id-and-stream-survey.md` cross-check table have **no** UID literal and may differ in this area too).

## The receiver=0x0e / "GL300C" reply content, re-examined (2026-10-25)

The "Breakthrough" section's `GL300C`/`WM320 A7_LPC1 20170828/00` reply at receiver `0x0e`
raised an architecture question: does m0306 locally fabricate that identity, or genuinely
forward the request to the real `air_router_stm32f103`? Two concrete findings, neither fully closing it:

- **V, decompiled `duml_resp_send` (`0x0806d334`), existing Ghidra project
  (`scratchpad/ghproj/m0306`).** The reply-builder's sender byte is built from the *request's
  own receiver byte* (`*(byte*)(param_1+5)`), not a validity check against "am I this type":
  `if ((~bVar2 & 0x1f) == 0) bVar2 = 3;` — i.e. only the broadcast wildcard (`0x1f`, all 5 type
  bits set) gets special-cased to answer as FLYC (device type 3); **every other receiver value
  is echoed straight back as the reply's claimed sender**. This is a permissive echo, not an
  identity check — on its own it would explain the reply's *header* claiming to be from `0x0e`,
  but says nothing about where the *payload content* (`GL300C`, the version string) comes from.
- **V, `GL300C`/`WM320 A7_LPC1 20170828/00` are NOT literal strings anywhere in m0306's own
  decrypted flash** (`scratchpad/dec/P3X_FW_V01.11.0020_m0306.bin`, full `strings` sweep) —
  rules out "stale shared-codebase boilerplate string" as the explanation.
- **V, found instead:** `REQ_APP_WM610` (`0x8064530`) and a parameter/debug-name cluster
  `g_real.wm610_app_command.function_command_0` / `..._state_0` (`0x80f74ca`/`0x80f828a`) —
  naming consistent with the `g_config.*`/`g_real.*` debug-name convention already established
  for the 834-entry param table (`fc-io-inventory.md`/`fc_param_table.py`), not raw code. This
  is a real, named mechanism in m0306 for talking to a WM610-family (shared-Lightbridge) device
  — consistent with, though not proof of, the forward-to-radio-MCU hypothesis.
- **U, dead end by the documented method, not yet solved another way:** `mcu_trace.py str`
  found **zero literal-pool xrefs** to either string — the same "code addresses the struct by
  RAM base, not by re-loading the string's flash address" dead end already recorded above for
  `VCOM`/`MSCM`. The right next step is the **param-table route**, not string-xref: find this
  cluster's entry in the `FlycExportParam` array by its debug name (same method
  `fc_param_table.py` uses for the other 834 entries) to get its RAM address, then trace who
  reads/writes *that* address — not attempted this session.
- **Net effect: narrowed, not solved.** The reply's claimed sender (`0x0e`) is now explained
  (permissive echo, V). Whether the reply's *content* is live-forwarded from the real `air_router_stm32f103`
  over an internal bus, or populated from a cached/shared RAM table the FC maintains about
  paired components, remains **U** — but "stale copy-pasted string" is now ruled out, and a
  real WM610-communication mechanism (not previously documented) is confirmed to exist.

## Open / not resolved

- **U**: no CDC-receive-equivalent function was located by tracing forward from either boot
  chain; time budget did not allow a full reverse-trace from the DUML SOF (`0x55`) framer
  back to confirm it never has a USB-fed case.
- **U**: what gates/reads `assistant_timeout_0` and the "Assistant protect" / "Device lock
  protect" state strings; not disassembled this session.
- **U**: the SDIO stall's effect, if any, on code that runs after it in real boot order.
- **U**: whether the exact firmware on the operator's aircraft matches this image byte-for-
  byte.

## Public corroboration (2026-10-24)

- **W** (`o-gs/dji-firmware-tools` wiki, "Firmware m0306" page, "Interfaces" section, <https://github.com/o-gs/dji-firmware-tools/wiki/Firmware-m0306>, by the project's maintainer): "Hooking a PC to the micro-USB connector in front of the drone gives access to an UART interface... The interface also allow injecting commands to the drone, as long as they meet the DUML binary packet format.” Same 115200 8N1 as we use.
  - No special unlock/handshake byte sequence for *this* port (the FC's front USB) is documented anywhere public found this session (wiki, forums, GitHub issues). The wiki states it should just work.
  - **Update (2026-10-24, later same day):** `camera-linux-console-access.md` (a *different* port, the camera's Ambarella Linux) has since added two things:
    - a firmware-side trace of a matching RTOS file-gate (specific disassembled addresses, see that doc's “SD-card diagnostic logging marker” section);
    - a card-side result: `MISC/LOG/CameraLogCur.log` now exists, 42,466 bytes.
  - This is real evidence, but it doesn't establish that the marker *specifically* caused that file; causation is still unproven, per that doc's own “Update” note.
  - `0x40003000` itself is still only confirmed as the example argument to the `t dji console [addr]` shell command, not as an established filename convention.
  - Still worth corroborating independently rather than treating either doc's framing as settled.
- This is independent confirmation the port is *supposed* to answer DUML, which makes
  this repo's total silence the anomaly to explain, not evidence the port is DUML-dead
  by design. Strengthens the "Assistant window" / boot-timing hypothesis below over the
  "dead ISR, nothing ever reads this" one — though both remain open.
- **W**, same source: the "Firmware m0306" page's repair companion,
  <https://github.com/o-gs/dji-firmware-tools/wiki/P3-Flight-Controller-aka-MC-repair>,
  independently describes this same port as the basic alive-check for the FC MCU ("it
  will provide a serial interface with startup logs on the USB output"), consistent with
  what we see, but does not mention commands failing to get a reply as a known issue.

## Breakthrough, live hardware (2026-10-24): the port answers, reliably, once caught

Prior sessions concluded this port never replies. That conclusion was an artifact of
probing with a tool that gives up the moment the USB device drops — which is exactly
what happens around a power-cycle, the one time a reply might appear. Built
`scripts/re/duml_watch.py` (reopens the port in a loop instead of exiting on
disconnect, sends the heartbeat ping continuously, logs everything to
`captures/sessions/2026-10-24/duml_watch.log`) and ran it across an operator-triggered
power-cycle of the aircraft.

- **V**: at 12:03:50, within the watch window, the port answered a bare ping
  (General `0x00/0x0c`, receiver `0x0e` / "OSD") with a clean CRC-valid ACK, and kept
  answering every ~0.5 s for the full remaining ~4.75 minutes of the run (574 pings
  sent, 574 clean ACKs, zero drops) — not a brief window, a sustained link once caught.
- **V**: GetVersion (`00/01`) and GetDeviceInfo (`00/ff`) at receiver `0x0e` returned
  **`GL300C`** / **`WM320 A7_LPC1 20170828/00`** — byte-identical to what the RC itself
  reports at the same receiver over its own port (`docs/identity-queries.md`).
  **Correction to the architecture model**: receiver `0x0e` on this port is not the
  flight controller - it is the aircraft's own `air_router_stm32f103` (an m0900-family chip,
  same firmware build as the RC's), reached the same way DUML reaches the RC's radio
  MCU. The "front USB port = flight controller" framing in this doc's title and earlier
  sections needs qualifying: USB on this port reaches `air_router_stm32f103` by default; the FC
  itself may sit behind it, not be it.
- **V**: a receiver sweep (camera `0x01`, FLYC `0x03`, gimbal `0x04`, center board
  `0x05`, remote controller `0x06`, and indexed variants) against the *same live,
  confirmed-responsive* port got **no reply from anything except `0x0e`** - bracketed
  by two more `0x0e` pings that both succeeded, so the silence on other receivers isn't
  the link dying mid-sweep. Whether that's because this port's DUML only routes to the
  `air_router_stm32f103` (not relayed onward to FLYC/camera/gimbal), or those other receiver
  addresses are simply wrong for this bus, is **U**.
- **U**: GetSerialNum (`00/51`, payload `04`/FlycNum) at `0x0e` got no reply - consistent
  with `0x0e` being `air_router_stm32f103`, which (like the RC) doesn't implement that query.
  The aircraft's own serial/FlycNum still needs a receiver that reaches the FC, which
  this port hasn't shown yet.
- Reproduce: `python3 -I scripts/re/duml_watch.py /dev/ttyACM11 --minutes 10`, then
  power-cycle the aircraft while it runs; once connected, additional one-shot queries
  can be sent concurrently with `scripts/duml_probe.py` against the same port/receiver.

### Follow-up probing on the same live session (2026-10-24, continued)

All against the confirmed-responsive port, receiver `0x0e` unless stated. Sender kept
at PC (`0x0a`) throughout except one explicit check.

- **V**: `GetSerialNum` (`00/51`) at `0x0e` got no reply for payload `01`/`02`/`03`/`04`
  (BoardNum/ChipId/ModuleNum/FlycNum) - confirms, doesn't just repeat, the earlier
  single-payload result: `0x0e` implements none of the four index variants.
- **V**: RC-cmdset `GetMaster` (`06/07`) at `0x0e` replied `00` - "not connected to a master", same bit pattern the RC itself reports on its own port (`docs/identity-queries.md`).
  - Read with caution: this is RC role/pairing-role state (`cpu-reversing-proof.md`'s dual-remote state machine), not aircraft-ID binding.
  - We're on a USB cable, not the RF link, so "no master" here may just mean "no RF session active over USB", not that the aircraft is unpaired.
  - `RcGetName` (`06/09`) and `RcGetConnectMaster` (`06/0d`) at `0x0e` both got no reply.
- **V**: sender spoofed to `0x0e` (OSD) instead of PC, receiver still `0x0e` - no reply.
  Not evidence of anything specific (self-addressed self-sender is an odd combination
  generally), logged so it isn't retried.
- **V, new**: a receiver sweep extended to decimal-TTII type values beyond the known `DeviceType` table (camera 1, app 2, flightController 3, gimbal 4, centerBoard 5, remoteController 6, pc 10, osd 14) turned up **wire address `0x14` (type 20, index 0, not in any catalog here)**.
  - It answers `GetDeviceState` (`00/0c`) with `e30000000000`: same payload style the RC gave on its very first reply after a fresh port open (`docs/p3-usb-observations-2026-10-23.md`).
  - `GetVersion` (`00/01`) at `0x14` replied with an unpopulated-looking record (`00100000...` then a run of `fe ff ff ff fe ff ff ff 01 00 00 00 00`, no readable hardware-name string like `GL300C`).
  - **I**: looks like a default/placeholder responder for an unclaimed dispatch slot, not a confirmed real distinct device.
  - `GetDeviceInfo` (`00/ff`) at `0x14` got no reply.
  - **U, not resolved:** whether `0x14` is a real third component or an artifact of how the dispatcher answers addresses nobody explicitly claimed. Worth one more pass with a wider `GetDeviceState` payload decode and a couple of neighbouring type values (19, 21), to see if "every unclaimed slot answers identically" or specific to 20.
  - Every type value actually tried this session is in `captures/sessions/2026-10-24/duml_watch.log` and the shell history above. Re-run rather than re-guess.
- Everything above ran on a single sustained connection (no further disconnects),
  confirmed live before and after each batch.

## Suggestion for the operator (not an instruction — their hardware, their call)

If DJI Assistant-style access over this port is wanted, the one thing worth trying on real
hardware (not run here, and `probe_fc_usb.py` may be running concurrently) is sending a DUML
packet **immediately after power-on** (within the first ~1-2 s), rather than after the
aircraft has already settled — consistent with an Assistant-window hypothesis. This is a
suggestion for a parallel manual test, not something this session executed.

## Reproduce

- Static: `python3 scripts/re/mcu_trace.py --img firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin
  --base 0x08020000 --load 0x08020000 dis 0x80219a0 4` (dead vector target);
  `... who 0x803c094 4` (USB-init call graph); `... lit 0x40040000` / `... lit 0x50000000`
  (OTG core base refs).
- String xrefs: `python3 scripts/re/fc_usb_xrefs.py firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin
  "DJI CONTROLLER" "0001A0000000" "assistant protect" "usb work in MSC mode"` (log
  `tmp/logs/fc_usb_xrefs.log`).
- Renode: `python3 scripts/re/m0306_probe.py` (short window + forced-IRQ test, log
  `tmp/logs/m0306_probe.log`); `renode --console --disable-xwt -e "include
  @renode/scripts/m0306_probe_long.resc"` (2s ISER sweep, log
  `tmp/logs/m0306_probe_long.log`).

## Independent re-verification (2026-10-23)

Adversarial pass requested by the operator, skeptical of the headline finding. Re-derived
everything from raw bytes rather than trusting the numbers above; content above is unchanged.

**1. VTOR remapping (SCB->VTOR, `0xE000ED08`) — V, risk ruled out for m0306 and m0305.**
Raw 4-byte-word search plus a MOVW/MOVT-pair sweep (same method `mcu_trace.py`'s `lit` uses)
for `0xE000ED08` across the full image: **zero hits** in `P3X_FW_V01.11.0020_m0306.bin` (885 KB)
and **zero hits** in `_m0305.bin` (43 KB, the candidate loader). m0305's only
`0x08020000`-valued word (file offset `0xa4ac`) sits inside an obvious flash-sector-boundary
table (`0x08000000, 0x08004000, 0x08008000, 0x0800c000, 0x08010000, 0x08020000, 0x08040000...`
— STM32F42x sector map), not a jump/VTOR target — m0305 reads as a flash programmer, not a
vector-relocating bootloader. **U**: a third module or boot-ROM/option-byte path could still
set VTOR before either image runs; not excluded, but the specific feared mechanism ("m0306
reprograms its own vector table") is falsified for m0306's own code.

**2. RTOS-level indirection — V, finding holds, mechanism is more specific than stated.**
Counted the full vector table independently (240 entries, file offset `0x40`-`0x400`): **44**
distinct IRQn point at the exact self-branch address `0x080219a1` — a shared, generic
unused-IRQ catch-all, not something OTG-specific. Re-disassembled the "real handler" trampoline
at `0x0803a45c` onward: confirmed genuine `movs r0,#IRQn; b.w 0x803f6ec` stubs, serving ~20
IRQn (31-34, 37-40, 47, 48, 52, 53, 71-73, 82, 83, ...) — none of the 5 headline OTG IRQn
(42, 74-77) appear in it. But a **third pattern**, not considered in the original pass, exists:
IRQn67 has its own direct, non-trampoline, non-default handler (see #5) — real multi-branch
code at `0x08087c3a` (`bl 0x803c298` / `bl 0x803c2b8` to read status, dispatch to
`0x802a256`/`0x8029e60`/etc.), the shape of a standard STM32 HAL `PCD_IRQHandler`. So USB OTG
on this chip is not uniformly "dead" — one of its NVIC lines runs real code.

**3. Firmware version mismatch — V, finding strengthened, not weakened.**
`m0306.bin` exists on disk for 4 more variants beyond the analyzed image:
`tmp/air/P3X0006/P3X_FW_V01.01.0006_m0306.bin`, `tmp/air/P3C/P3C_FW_V01.08.0100_m0306.bin`,
`tmp/air/P3SE/P3SE_FW_V01.01.0000_m0306.bin`, `tmp/air/P3XW/P3XW_FW_V01.00.0010_m0306.bin`.
Independently parsed vector tables + disassembled targets in all 5: **every one** has
OTG_FS_WKUP(42)/OTG_HS_EP1_OUT(74)/EP1_IN(75)/WKUP(76)/OTG_HS(77) pointing to a self-branch at
that build's own Default_Handler (`0x080219a0` / `0x0807161c` / `0x08021988` / `0x08021988` /
`0x08020f1c` respectively), with USART1(37) always real. Not a one-build artifact — consistent
across 5 independent builds spanning the P3X/P3X0006/P3C/P3SE/P3XW line.

**4. Re-derive raw facts — V, matches the doc; one labeling nit found in the process.**
Parsed the vector table and disassembled `0x080219a0` directly from the file, not from the
doc's numbers: all 5 values = `0x080219a1`, reset vector `0x08021965`, SP `0x2002ff00`,
target instruction `b #0x80219a0` — identical to the doc. While doing this: the doc's
peripheral **names** for some control-group IRQn don't match Renode's own authoritative
`platforms/cpus/stm32f4.repl` (the platform the Renode runs used) — IRQn56/57 are
DMA2_Stream0/1, not TIM6/TIM7 (those are 54/55); IRQn71 is USART6, not DMA2_Stream7 (that's
70); IRQn82/83 are UART7/UART8, not UART4/UART5 (those are 52/53). The IRQn *numbers* and
their "points to a real handler" status are correct; only the English names attached to them
in the doc's contrast table are off. Doesn't affect the finding.

**5. NVIC ISER sweep / is 2s long enough — finding is WRONG AS STATED, revise.**
Extended the simulated boot 5x past the original cap: `renode/scripts/m0306_probe_10s.resc`
(20x500ms steps to 10s, log `tmp/logs/m0306_probe_10s_stdout.log`). Result:
- The 5 headline vectors (IRQn 42, 74, 75, 76, 77) stay unmasked=false through the full 10s —
  that specific claim holds up to 10s (5x the original window), not just 2s.
- But ISER2 changes between t=5500ms and t=6000ms: `0x000803F3` -> `0x000803FB`. IRQn67 goes from disabled to enabled.
  - **IRQn67 is OTG_FS** (the FS core's combined global interrupt) per the standard STM32F427/437 reference manual's interrupt vector table (public ST documentation, not checked against anything in this repo).
  - **Correction (lead session, 2026-10-23):** this was originally claimed as "confirmed against the stock `stm32f429.repl`/`stm32f4.repl` IRQ map". Checked independently: **neither stock Renode platform file names or models USB-OTG at all** (consistent with the earlier, separately-confirmed finding that Renode has no STM32 OTG peripheral model).
  - The IRQn67=OTG_FS identification itself is still very likely correct (matches well-known public ST silicon numbering), but it rests on that external reference, not on anything verifiable in this repo's Renode files. Tag it **I**, not **V**, on that specific point.
  - There are **six** OTG-related IRQn on this chip family (42, 67, 74, 75, 76, 77), not five. The 6th is the one most USB device stacks actually use for day-to-day RX/TX servicing.
- That vector's handler (`0x08087c3a`, independently disassembled) is real code, not
  Default_Handler (see #2).
- The doc's SD-card stall side-note ("not chased further") is not a permanent hang: PC moves
  through 6+ distinct addresses from t=3000ms-6000ms (real forward progress past the stall),
  then settles into the uC/OS-III idle-task loop from ~6500ms on (same address family as the
  original short-window probe's idle-task finding). Full boot takes ~6s, 3x the original 2s
  check window.
- So "the interrupt is never even unmasked during a 2s simulated boot" is true only because
  (a) 2s was too short to see this firmware finish booting, and (b) the check didn't cover
  IRQn67, which does get unmasked once boot completes.

## Overall verdict: needs revision — core claim holds, "total dead end" framing does not

- **Holds, V, independently reproduced:** the 5 specific vectors in the headline table
  (OTG_FS_WKUP, OTG_HS_EP1_OUT/IN, OTG_HS_WKUP, OTG_HS) do point to the CPU's self-branch
  Default_Handler, byte-for-byte as stated, reproduced from raw bytes, reproduced across 5
  separate firmware builds, and confirmed unmasked=false through a 10s (not just 2s)
  simulated boot. VTOR relocation is ruled out as the explanation (#1).
- **Wrong as framed:** "all five USB-OTG NVIC vectors" / "the interrupt is never even
  unmasked" understated the chip's USB-OTG interrupt surface and overstated the boot-window
  check. A 6th OTG-related vector (IRQn67, OTG_FS) exists, was not checked, has a genuine
  non-default handler, and does get unmasked — just after the firmware finishes booting
  (~6s), which the original 2s window didn't reach.
- **Practical effect on "does the port ever answer DUML" — still U, likely unchanged:** 5 of
  6 OTG vectors are genuinely dead either way, and whether IRQn67's live handler
  (`0x08087c3a` -> `0x8029f26`) ever does anything DUML-relevant, or whether the OTG_FS
  peripheral it's nominally for is even clocked (RCC), was not traced this session. The
  doc's bottom-line "accepts bytes, never replies" conclusion is not contradicted by this
  pass, but it was resting on an incomplete vector census and a boot window that ended
  before boot finished — both should have been caught before being stated as **V**.
- **Not re-chased this session (U):** whether `0x8029f26` reaches anything DUML-relevant;
  whether OTG_FS's AHB/APB clock is ever enabled; whether IRQn 42/74-77 unmask at some point
  past 10s (not tested).

Reproduce: `python3 scripts/re/mcu_trace.py --img firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin
--base 0x08020000 --load 0x08020000 lit 0xe000ed08` (empty = no VTOR write found); vector/IRQ67
disasm and the 5-variant comparison were done with ad hoc Python (capstone) reading the `.bin`
files directly, not checked in; `renode --console --disable-xwt -e "include
@renode/scripts/m0306_probe_10s.resc"` (log `tmp/logs/m0306_probe_10s_stdout.log`).

## IRQn67 handler (`0x8029f26`): structural match against ST's HAL_PCD_IRQHandler (2026-10-23)

Followed up on `0x8029f26` (the function IRQn67's handler at `0x08087c3a` tail-jumps into).
Goal: move past "looks like a standard PCD_IRQHandler" (a shape guess) to something checked
against real reference source. No pre-built matching binary exists anywhere locally to diff
against byte-for-byte (see below) — fell back to structural/control-flow comparison against
ST's public `stm32f4xx_hal_pcd.c` (fetched to `tmp/stm32_hal_ref/`, gitignored, not committed
— DJI/ST copyrighted source, kept local only per this repo's no-binaries-committed rule).

- **V, reference-binary search was exhaustive and came back empty.** Swept every `.elf` under `/mnt/2tb/git` (~150 repos) for `HAL_PCD`/`USB_OTG`/`PCD_IRQHandler` symbols.
  - All hits are Zephyr/ESP-IDF builds (`awto-zephyr-wt-*`, `awto-l8-wt-*`): unrelated architecture, not STM32F4, not ST's HAL.
  - No STM32F4 reference binary with debug symbols exists in any local repo. No shortcut; matching has to be done by reading the code.
- **V, disassembled `0x8029f26` directly** (`firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin`, base `0x08020000`).
  - Shape: `push {r4-r8,sb,sl,lr}`; read a status word via a call (`0x803c298`/`0x803c2b8`); then a long run of independent bit tests, each `lsls r0, r5, #<shift>` / `bpl` (i.e. "if bit N of the status word is set").
  - Each test guards a call to a distinct sub-handler (`0x802a256`, `0x8029e60`, `0x802a168`, `0x802a0ec`, `0x802a06c`, `0x803c474`, `0x803c44e`) whose results get OR-accumulated into `r4`; ends `pop {...,pc}` returning `r4`.
  - This is the canonical shape of a GINTSTS-style "test every pending-interrupt bit, dispatch per bit, return which ones were handled" USB-OTG device-mode ISR. `HAL_PCD_IRQHandler` has the same shape in every ST HAL version checked (confirmed against the fetched `stm32f4xx_hal_pcd.c`: `if (__HAL_PCD_GET_FLAG(...))` per flag, each guarding a handler, same independent-bit-test structure).
  - Upgrades the earlier "looks like PCD_IRQHandler" from a bare guess to a structurally-grounded claim with cited addresses. It is **not** a byte-exact or version-exact match (see next point).
- **I, not literally ST's current `HAL_PCD_IRQHandler`.**
  - One dispatch arm (the last couple of bits tested) calls indirectly through a pointer loaded from RAM. Literal pool at `0x802a2a4` holds `0x2001cd98` (an SRAM1 address), loaded into r8, then `ldr r0,[r8]` / `ldr r1,[r0,#0xc]` (and `+0x18`, `+0x1c`, `+0x20`) / `blx r1`. That is a table of function pointers at small, early offsets inside some global struct reached via `0x2001cd98`.
  - ST's `PCD_HandleTypeDef` (`tmp/stm32_hal_ref/stm32f4xx_hal_pcd.h`) does have a block of callback function pointers (`SOFCallback`, `SetupStageCallback`, `ResetCallback`, ... `MspDeInitCallback`). They sit well past these small offsets (after `Instance`/`Init`/the USB register-state fields) in every HAL version checked, so `+0xc/+0x18/+0x1c/+0x20` land too early to be that block.
  - More consistent with either (a) a much older/leaner `HAL_PCD_IRQHandler` (pre-`USE_HAL_PCD_REGISTER_CALLBACKS`, which only exists from HAL F4 ~v1.7+), or (b) a DJI-internal thin wrapper struct with its own small callback vtable, not ST's HAL verbatim. (b) is suggested by the firmware's own distinct in-house `hal_` naming convention for unrelated peripherals (`hal_compass_add`, seen in the same image).
- **U, not resolved this pass:** exact HAL version/vendor, and whether `0x2001cd98` names a real persistent handle (vs. a relocatable bootloader-copy artifact). Would need either:
  - (a) a compiled HAL_PCD_IRQHandler at a specific version to diff bit-shift-order against (started, not finished: `tmp/stm32_hal_ref/` has HAL source only, no build yet), or
  - (b) finding the constructor that populates `0x2001cd98` and checking its struct literal against a specific HAL header's field layout.
- **Compiler/toolchain fingerprint, I:** `Reset_Handler` (`0x08021964`) is two instructions: an indirect call via literal pool (SystemInit-equivalent), then an indirect tail-jump. No inline `.data`/`.bss` copy loop is visible at the reset entry.
  - Better fit for ARM Compiler/Keil's `__main` scatter-loader trampoline than for a typical GCC+newlib `Reset_Handler` (which usually inlines the copy/zero loops).
  - Not confirmed against an actual ARMCC build; no Keil-built STM32F4 reference binary found locally either.

Reproduce: disasm via ad hoc capstone (same pattern as `scripts/re/fc_usb_xrefs.py`, not
checked in as its own script); HAL reference source fetched from
`raw.githubusercontent.com/STMicroelectronics/stm32f4xx_hal_driver/master/{Src,Inc}/...`
(the HAL driver is a separate submodule repo from the `STM32CubeF4` umbrella — the umbrella
repo's own raw tree 404s on these paths).

### Follow-up, same day: the two opening calls confirm real ST LL_USB code (not DJI-custom)

Checked the "is it the LL API" angle (DJI may call ST's lower-level `stm32f4xx_ll_usb.c`
directly rather than going through the full `HAL_PCD` object). Result: it's both, and it's
genuinely ST's code, not a lookalike.

- **V.** The disassembly's first two `bl` targets, in order, are exactly `USB_GetMode()` then
  `USB_ReadInterrupts()` — the same two calls, same order, as `HAL_PCD_IRQHandler`'s opening
  lines (`if (USB_GetMode(...) == USB_OTG_MODE_DEVICE) { if
  (__HAL_PCD_IS_INVALID_INTERRUPT(hpcd)) return; ...`). Confirmed against ST's own header
  (`tmp/stm32_hal_ref/stm32f4xx_hal_pcd.h:201`):
  `__HAL_PCD_IS_INVALID_INTERRUPT(__HANDLE__)` expands to a **real call** to
  `USB_ReadInterrupts((__HANDLE__)->Instance)`, not an inline register read — so the macro
  call-site and the disassembled `bl` match at the function-call level, not just
  coincidentally similar shape. `r5` (the value every subsequent bit test runs against) is
  this call's return value, exactly matching `USB_ReadInterrupts`'s role (`GINTSTS & GINTMSK`)
  in the real source.
  - This retires the earlier "not literally ST's HAL_PCD_IRQHandler" doubt raised by the
    vtable-offset mismatch — the core dispatcher **is** ST's LL_USB/HAL_PCD code (or
    byte-identical to it for a HAL version not yet pinned down). The vtable-offset point
    stands on its own as a separate, narrower open question (struct layout/version, not
    "is this ST's code at all").
- **U, still open:** which HAL/LL release (the field-offset mismatch says *not* the current
  `master` layout — an older pre-`RegisterCallback` version is the leading candidate, not yet
  confirmed by diffing against a specific tagged release's header).
