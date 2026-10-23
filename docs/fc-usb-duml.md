# Front micro-USB (m0306 flight controller): why it never answers DUML

Firmware: `P3X_FW_V01.11.0020_m0306.bin` (STM32F427IIH6, app base `0x08020000`, SP
`0x2002ff00`, reset `0x08021965`, RTOS strings identify **Micrium uC/OS-III**). Reproduce
disasm: `python3 scripts/re/mcu_trace.py --img firmware/unpacked/P3X_FW_V01.11.0020_m0306.bin
--base 0x08020000 --load 0x08020000 dis <addr> <n>`.
Scope (`CLAUDE.md`): read/trace-only, no control-command sending, no geofence work.
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

**V (Renode, dynamic confirmation).** Forced NVIC enable+pend on OTG_HS (IRQn 77, since
Renode has no STM32 OTG device-controller peripheral model — same "forced register state
instead of full peripheral emulation" method used for m0900's AD9363 SPI writers,
`docs/fpga-bringup.md`): `sysbus WriteDoubleWord 0xE000E108 0x2000` (ISER2 bit13) then
`0xE000E208 0x2000` (ISPR2 bit13), `emulation RunFor "00:00:00.001"`. Result: `cpu PC` =
`0x080219a0` and stays there after another 1ms step — the CPU parks in `Default_Handler`
permanently the instant any OTG_HS interrupt is actually taken, exactly as the static
disasm predicts. Reproduce: `python3 scripts/re/m0306_probe.py` (log
`tmp/logs/m0306_probe.log`); platform `renode/platforms/m0306.repl` (extends stock
`platforms/cpus/stm32f429.repl` — closest public SVD match to the real F427; unlike m0900's
F103 it did not need an RCC_CFGR tag workaround, since the stock F4 repl already models
`STM32F4_RCC`).

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

**I.** `"VCOM"` vs `"MSCM"` read as two USB personalities (CDC-ACM vs mass-storage), and
`"Assistant protect"` / `"assistant connect changed:last(%u) != current(%u)"` / the config
key `"assistant_timeout_0"` (all string-verified, V for existence) look like a boot-time
"Assistant window": known DJI A3-family behavior is a short post-power-on window during
which DJI Assistant PC software can attach; after a timeout with no handshake the firmware
moves on. Combined with the Renode findings above, the likeliest explanation for "accepts
bytes, never replies" is: the probe connects to a FC that is **already past** that window (or
one that, in this firmware image, never enables OTG-interrupt service at all) — the hardware
OTG peripheral still ACKs USB transport-layer traffic (control transfers for enumeration,
bulk-OUT framing) regardless of software, but nothing ever reads the result into a DUML
parser. **Not verified**: the actual content of the one-shot boot init (I did not find/trace
the consumer of `assistant_timeout_0`, nor a receive-processing function reachable from
either call chain above), and whether the operator's physically connected FC runs this exact
firmware build (image `.ini` version `02.04.5170`; other P3X FC images checked in
`docs/air-id-and-stream-survey.md` cross-check table have **no** UID literal and may differ
in this area too).

## Open / not resolved

- **U**: no CDC-receive-equivalent function was located by tracing forward from either boot
  chain; time budget did not allow a full reverse-trace from the DUML SOF (`0x55`) framer
  back to confirm it never has a USB-fed case.
- **U**: what gates/reads `assistant_timeout_0` and the "Assistant protect" / "Device lock
  protect" state strings; not disassembled this session.
- **U**: the SDIO stall's effect, if any, on code that runs after it in real boot order.
- **U**: whether the exact firmware on the operator's aircraft matches this image byte-for-
  byte.

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
