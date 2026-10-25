# m0900 (`air_router_stm32f103`) deep dive: full command surface, bring-up gate, reboot/upgrade mechanism

Source: static trace of `P3X_FW_V01.11.0020_m0900.bin`, SHA-256
`72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d` — **verified** against
`docs/data-manifest.md` (exact match) before use. App base `0x08008000`. Tool:
`python3 scripts/re/m0900_trace.py dis|who|ptr <addr>` plus short one-off `word()`-reader
scripts using the same base/load convention (shown inline below so they're reproducible by
pasting). Capstone-only; no Ghidra project was built for m0900 (none existed; given the
answers came cleanly from table walks + `who`/`ptr` xrefs, a GUI project wasn't needed — see
"Method note" at the end). Cross-checked by name against
`docs/symbols/upstream/P3X_FW_V01.07.0060_m0900_air-radio.map` and
`docs/data/apk-dynamic-cmdset-ids.tsv` where noted.

Tags: **V** verified (address/command cited, reproducible), **I** inferred, **U** unknown.
This doc only adds to/corrects `dataflow.md`, `m0900-can-channels.md`, `fpga-bringup.md`,
`fpga-upgrade-path.md`, `phy-params.md` — read those first; not restated here except where
corrected.

## 0. Headline results

1. **The "16-bit-id table, how reached: U" item in `dataflow.md` §3/§5.10 is closed.** It is
   not a separately-reached table — it is a *second, nested* dispatch table immediately
   below the main one, entered through exactly one main-table record: DUML `set 0x09 cmd
   0x2c`, receiver type 9. (§1, §2 — V)
2. **The RAM flag `0x200000c8` "consumer not decoded" (`fpga-upgrade-path.md`) is closed.**
   It gates the watchdog-feed task that `fpga-bringup.md` lists at 100-tick cadence but
   doesn't decode. Setting it stops IWDG refresh, so the chip free-resets. (§3 — V)
3. **The flash page `0x7b00` "256-byte config page... use not decoded" is closed**: it is
   read/written by DUML sub-ids `0x0901`/`0x0902` (get/set), reached via the table in (1).
   It backs the live `radio_state_S` RAM struct (`0x20001ab4`) byte-for-byte. (§2.1 — V)
4. **The flash page `0x7800` "second page... use not decoded" (`fpga-upgrade-path.md`) is
   closed**: written by DUML `set 0x00 cmd 0x0D` (Set Device Version), two 16-byte fields. (§1 — V)
5. **`dataflow.md` §5a's cmdset-9 naming mismatch is resolved, mostly.** The apk names
   `SetFPGA`(4)/`GetFPGA`(5)/`Set9363`(6)/`Get9363`(7) as four separate commands; the firmware
   *does* have four separate handlers at cmd 04/05/06/07, not the single combined-write this
   doc previously thought. Cmd 0x06 additionally keeps a legacy FPGA-write fallback
   (`hi==0xFE`) alongside its AD9363 write path, which is why it looked "combined" before this
   trace separated 04 from 06. (§1.1 — V)
6. **Issue #2 (AD9363 bring-up trigger) was already closed by `fpga-bringup.md`/`phy-params.md`
   before this task** (board-code GPIO straps, not a DUML command) — confirmed again here by
   re-reading the gate, no new result. (§4)
7. **The Update-Transmit mystery is narrowed, not solved.** New: the exact mechanism by which
   the app hands off to the (absent) bootloader is now fully traced — a watchdog-forced reset,
   not a jump or vector rewrite. Still open: what the bootloader does with the image bytes,
   because the bootloader (`0x08000000-0x08007FFF`) is not in this container. (§5)
8. **CAN camera/gimbal payload semantics (types 1/4/8/15): negative result, verified.** The
   complete dispatch-table walk (§1) has zero records for receiver types 1, 4, 8 or 15. m0900
   never interprets their payloads — CAN 0x412/0x413 is confirmed pure pass-through end to
   end, not just "beyond what's been traced." (§6)

## 1. The full command surface (dispatch table, completely walked)

The two tables `dataflow.md` described as separate are one contiguous array of 8-byte
records `[handler_ptr(4), key(4)]`, laid out `0x0801a0d8..0x0801a200` (37 records, two
all-zero sentinels). There is no other dispatch table in the image (checked: `ptr` on both
table base literals finds exactly one load site each — see §2).

Reproduce the raw dump:
```python
BASE=0x08008000
img=open('firmware/P3X_FW_V01.11.0020_m0900.bin','rb').read()
word=lambda a:int.from_bytes(img[a-BASE:a-BASE+4],'little')
# inner table: a in range(0x0801a0d8, 0x0801a120, 8)
# outer table: a in range(0x0801a120, 0x0801a200, 8)
```

### 1a. Inner table `0x0801a0d8..0x0801a118` (8 records + zero sentinel) — matched on a raw
16-bit value, not type/index (§2 explains the matcher)

| id16 | handler | Name/behaviour | Tag |
|---|---|---|---|
| `0x0901` | `0x0801102c` | **Get Config**: memcpy 0xFC (252) B from RAM struct `0x200019b8` into reply `0x0951` | V |
| `0x0902` | `0x08011062` | **Set Config**: if payload len==0xFC, write 252 B to the same struct, `bl 0x8012766` (flash-writes 256 B incl. CRC to page `0x7b00`, verifies), `bl 0x0800e9e8` (reloads page `0x7b00` back into RAM struct `0x20001ab4`, the live `radio_state_S`) — reply `0x0952` [success 0/1] | V |
| `0x0903` | `0x080110bc` | **generic watchdog reboot**: unconditionally `bl 0x0800bd50(0x64)` (arm IWDG, ~100-tick reload) then `bl 0x0800bd82` (set flag `0x200000c8`=1) — reply `0x0953` [1]. Identical mechanism to "Reboot Chip" (§1b `cmd 0x0B`) and to Enter Loader's post-success step (§3/§5) | V |
| `0x0904` | `0x080110f2` | **Get UID**: STM32 96-bit UID `0x1FFFF7E8`, reply `0x0954`, 16 B (already known, `fpga-upgrade-path.md`) | V |
| `0x0911` | `0x08011122` | reply `0x0961`; not decoded further (pre-existing) | — |
| `0x0912` | `0x0801114a` | reply `0x0962`, value from `0x0800105d2`; not decoded further (pre-existing) | — |
| `0x0913` | `0x08011180` | **radio config SET**: packs cfg-word bits 7-11/18-20/27-29, bit21, TX-atten idx (`S+0x11b`) (pre-existing, `m0900_V01.11.0020.tsv`) | V |
| `0x0914` | `0x080111fc` | **radio status GET**, reply `0x0964` (pre-existing, partial) | — |
| `0x0000` | `0x00000000` | sentinel — matcher stops here (§2) | V |

`0x0901`/`0x0902`/`0x0903` are new in this pass. They give the flash page `0x7b00` concrete
semantics: it is a persisted snapshot of `radio_state_S`, round-tripped by a DUML get/set/
commit triplet, and `0903`'s reboot is the generic commit-and-reset primitive the other paths
(§3, §5) reuse.

### 1b. Outer table `0x0801a120..0x0801a1f8` (28 records), matched on `(cmd,set,type,index)`
exactly as `dataflow.md` describes. Full walk (no gaps skipped):

| cmd | set | type | handler | Name (apk `cmdset-ids.tsv` where it exists) | What it does | Tag |
|---|---|---|---|---|---|---|
| 0x01 | 0x00 | 0 | `0x0801250e` | COMMON `GetVersion` | rewrites receiver byte to type 9 (self); replies only for a specific sub-index (bits 5-6 of byte 8 ==1 or 2), else silently drops | V |
| 0x42 | 0x03 | 9 | `0x08012012` | (pre-existing) | byte5→type4 (gimbal), resend | V (pre-existing) |
| 0x43 | 0x03 | 9 | `0x08011ed4` | (pre-existing) | byte5→type2 then type1, resend (OSD General fan-out) | V (pre-existing) |
| 0x44 | 0x03 | 9 | `0x08011f98` | (pre-existing) | same family as 0x43/0x42 | V (pre-existing) |
| 0xda | 0x03 | 14 | `0x0801203c` | FLYC `Detection` (cmdset3=FLYC, cmd218) | if payload[0]==0x10, `bl 0x08011324` (rate-limited sample into RAM ring `0x20001f08`, counter at `0x2000019c+4` resets at 0x47=71), **then always forwards** via `packet_send` | V (name from apk table; sampling behaviour new) |
| 0x0e | 0x09 | 9 | `0x0801205a` | **unnamed** (apk list has no cmd 15/0x0e in cmdset 9 between 14 and 16) | arg 1/2 → `bl 0x0800bffa(arg)`: sets/clears **GPIOB ODR bit4** (`0x40010c0c`), caches state at RAM `0x200000d4` | V; purpose I (looks like an FPGA-bypass/passthrough select line — same `0x0800bffa` helper Enter Loader calls for receiver-0x13 index∈{1,8}, §3) |
| 0x0f | 0x09 | 9 | `0x08012086` | **unnamed** (gap between cmd14 and cmd16) | branches on **receiver index** (not type) ∈{1,8,10}, calls `0x0800bff4` (reads RAM `0x200000d4`, the state `0x0e` just set) and returns status 0xF1/0xF2 on mismatch | V; purpose I — reads back the `0x0e` GPIO-state cache |
| 0x04 | 0x09 | 9 | `0x080120e2` | **SetFPGA** (apk) | direct `spi_fpga_raw_write(reg=payload[1], val=payload[2])`, no AD9363 branch — reply [0] | V. **Resolves `dataflow.md` §5a**: this is the dedicated FPGA-only write the apk names separately from cmd 0x06 |
| 0x05 | 0x09 | 9 | `0x08012102` | **GetFPGA** (apk) | FPGA reg read (pre-existing) | V |
| 0x06 | 0x09 | 9 | `0x08012122` | **Set9363** (apk) | AD9363 write; `hi==0xFE` legacy fallback still does an FPGA write too (pre-existing) | V |
| 0x07 | 0x09 | 9 | `0x0801216a` | **Get9363** (apk) | AD9363/FPGA read counterpart of 06 (pre-existing) | V |
| 0x12 | 0x09 | 9 | `0x080121b4` | radio SET (pre-existing) | `radio_start_stop(0)`, cfg-word fields | V |
| 0x13 | 0x09 | 9 | `0x08012210` | radio GET (pre-existing) | readback of 0x12's fields | V |
| 0x01 | 0x00 | 9 | `0x0801226e` | (pre-existing, "default") | board-dependent 0x22-byte reply | V (partial) |
| 0x01 | 0x00 | 0x13 | `0x0801226e` | same handler, FPGA receiver | same | V (partial) |
| 0xff | 0x00 | 9 | `0x0801253a` | (pre-existing, "catchall") | not decoded | — |
| 0xff | 0x00 | 0x13 | `0x0801253a` | same | not decoded | — |
| 0x07 | 0x00 | 9 | `0x08012320` | COMMON `RequestUpgrade` = **Enter Loader**, MCU self | write marker `OOXX` to flash `0x7400`; on success arms watchdog + sets flag `0x200000c8` (§3, §5 — newly closed) | V |
| 0x07 | 0x00 | 0x13 | `0x08012320` | same, FPGA receiver | boards 4/5 only: radio quiesce, FPGA upgrade-mode handshake | V (pre-existing) |
| 0x08 | 0x00 | 0x13 | `0x080123b8` | COMMON `RequestReceiveData` = **Update Confirm** | reply [status, block size 512] (pre-existing) | V |
| 0x0a | 0x00 | 0x13 | `0x080123e6` | COMMON `TranslateComplete` = **Update Finish** | FPGA reg compare + handshake (pre-existing) | V |
| 0x0b | 0x00 | 9 | `0x08012428` | COMMON `RestartDevice` = **Reboot Chip** | reads a host-supplied delay word from the payload, `bl 0x0800bd50(delay)` + `bl 0x0800bd82` — **same watchdog-reboot primitive as `0x0903`**, now fully decoded (was "not decoded") | V |
| 0x0c | 0x00 | 9 | `0x08012458` | COMMON `GetDeviceStatus` | board/receiver-type-dependent reply (pre-existing, partial) | V (partial) |
| 0x0c | 0x00 | 0x13 | `0x08012458` | same | same | V (partial) |
| 0x0d | 0x00 | 9 | `0x080124bc` | **Set Device Version** | `bl 0x080126b8`/`bl 0x080126d4`, two 16-byte fields → flash page `0x7800` — reply [0x12] | V. **Closes `fpga-upgrade-path.md`'s "0x7800... use not decoded"** |
| 0x1b | 0x06 | 3 | `0x080124f0` | RC `GetPushGpsInfo` (cmdset6), receiver **type 3 = FC** | memcpy 0x1E (30) B of payload into RAM `0x20002601`, **then always forwards** via `packet_send` | V. New: same intercept-and-cache-while-forwarding pattern as the OSD-General fan-out (0x43), now shown for a GPS push addressed to the FC |
| 0x2c | 0x09 | 9 | `0x080125dc` | **unnamed** (gap between 43 and 45 in apk cmdset9 list) | single instruction `b.w 0x080112da` — **tail-jumps straight into the inner-table matcher**, see §2 | V |
| 0xfe | 0x00 | 9 | `0x08012592` | **unnamed** | mode 1: writes host payload bytes directly into live `radio_state_s` (`0x20001ab4`), then `fpga_cfg_load()` + `radio_first_init()` — forces a full radio/FPGA re-bring-up with host-injected state; mode 2: silent 1-byte write to `radio_state_s+0x11c`, no reply. No auth gate found on either mode. See `air-router-io-and-naming.md` §2.4/§6 for the full trace | V, fully resolved (2026-10-25 follow-up) |
| *(end)* | | | `0x00000000` | sentinel | table ends at `0x0801a200`, confirmed by direct read (zero handler) | V |

Three records (`0x0e`, `0x0f`, `0xfe`, and partially `0xff`/`GetDeviceStatus`) have no name in
`docs/data/apk-dynamic-cmdset-ids.tsv` at all — real, reachable handlers the dynamically-dumped
APK enum doesn't list under those numbers (gaps: cmd 15 between 14/16, cmd 44 between 43/45,
and 0xfe/0xff outside the normal id range). Consistent with `dataflow.md` §5a's observation
that this firmware's command numbering doesn't track the apk enum 1:1 — now shown to recur,
not a one-off.

## 2. How the inner table (`0x0801a0d8`) is reached — closes the `dataflow.md` U item

`python3 scripts/re/m0900_trace.py ptr 0x0801a0d8` finds exactly one load of that literal, at
`0x0801131c`, inside a function starting `0x080112da`:

```
0x080112da: push {r4,r5,r6,r7}; r2=0
0x080112e0: cmp r1,#0x13; blo <return 0>      ; needs payload len >= 0x13 (19)
0x080112e4: r3 = 0x0801a0d8                    ; TABLE BASE — the inner table
0x080112e8: r6 = r3 + r2*8
0x080112ec: r5 = u16 @ [r4+0xd]                ; <-- match key: payload offset 0xD (2 B
                                                ;     into the payload, after the 11-byte
                                                ;     DUML header), NOT cmd/set/type
0x080112f0: r6 = u16 @ [r6+4]                   ; record's id16 field
0x080112f2: cmp r5,r6; bne next
0x080112f6: r2 = [r3 + r2*8]; bx r2             ; call handler
  next: r2++; loop; r5=[r3+r2*8]; if r5==0 stop (sentinel, §1a)
```

So the inner table is matched on a **16-bit value inside the payload**, not the standard
`(type,index,set,id)` 4-tuple the outer table (§1b) uses. The *only* way into this function
(checked with the properly-resynced instruction sweep, i.e. the same decode the tool's full
trace uses — a naive linear disasm from an arbitrary address mis-syncs across this packed
handler region and gives a wrong answer; see Method note) is one direct `b.w` at `0x080125dc`:

```
0x080125dc: b.w 0x080112da      ; the ENTIRE body of this "handler"
```

and `0x080125dc` is exactly the handler pointer for outer-table record `cmd=0x2c, set=0x09,
type=9` (§1b, last-but-one row). So: **a host sends `set 0x09 cmd 0x2c` to receiver type 9;
the outer dispatch (`0x0801198a`) matches it and jumps to a one-instruction stub that
tail-jumps into the inner dispatcher (`0x080112da`), which re-matches a 16-bit sub-id carried
two bytes into that command's own payload against the `0x0901..0x0914` table.** This is a
second dispatch *level*, not a second *entry point* into the same dispatch — `dataflow.md`'s
"how it is reached is not traced (U)" is now V, fully, with the exact gate condition (DUML
`cmd 0x2c / set 0x09 / type 9`, payload ≥ 19 B, inner id at payload+2).

Cmd `0x2c` (44 decimal) has no name in `apk-dynamic-cmdset-ids.tsv`'s cmdset-9 list (which
jumps 43→45) — consistent with §1's other unnamed gaps, i.e. this sub-dispatch command itself
is one of the apk-enum gaps.

## 3. RAM flag `0x200000c8` and the 100-tick watchdog task — closes `fpga-upgrade-path.md`'s
"consumer not decoded"

`fpga-bringup.md` lists `0x0800bd74` as a 100-tick main-loop task with meaning "not decoded".
Full disasm:

```
0x0800bd74: r0 = byte @ 0x200000c8
            cmp r0,#0; bne skip
            b.w 0x080096a6          ; IWDG_KR = 0xAAAA  (feed/reload the watchdog)
    skip:   bx lr                   ; flag set -> do NOT feed it
```

`0x080096a6`/`0x080096b0` write IWDG_KR (`0x40003000`, the real IWDG base on STM32F1 — the
tool's `NAMED_CONSTS` label "IWDG/SPI2region" for this address is confirmed to mean IWDG here,
not SPI2) with the reload key `0xAAAA` / start key `0xCCCC` respectively — standard StdPeriph
`IWDG_ReloadCounter`/`IWDG_Enable`.

So: **`0x200000c8` is the "stop feeding the watchdog" flag.** Three places set it, all via the
same two-call idiom `0x0800bd50(timeout)` (arm IWDG with that reload value) + `0x0800bd82`
(set the flag):

- Enter Loader (`0x08012320`), receiver type 9, only on a successful marker write (§1b, §5).
- Reboot Chip (`0x08012428`, `set 0x0B`), with a host-supplied timeout (§1b).
- the inner-table `0x0903` sub-command (§1a).

All three are the same primitive: **arm a short watchdog timeout, then stop refreshing it**,
which forces a hardware reset a few ticks later. This closes both "consumer not decoded"
(`fpga-upgrade-path.md`) and the 100-tick task's unlisted meaning (`fpga-bringup.md`).

## 4. Issue #2 (AD9363 bring-up gate) — not reopened, re-confirmed only

This was already resolved by `fpga-bringup.md`/`phy-params.md` (2026-10-24, before this task):
`main` (`0x0800db00`) skips all FPGA/AD9363 bring-up unless the board-strap code (PA0/PC15/
PC14) is in `{2,4,5,6,7}`; it is not gated by any DUML command. Re-read here to confirm no
newer doc superseded it — it hasn't. No new work was needed or done on this item; still open
underneath it (unchanged): which strap value the operator's physical board (`P01007.06`)
actually reads, and the meaning of FPGA reg `0x8A` the boot handshake polls.

## 5. The Update-Transmit mystery — narrowed

Unchanged facts (`fpga-upgrade-path.md`): there is no dispatch record for `set 0x00 cmd 0x09`
(`TranslateData`/"Update Transmit") at all, for either receiver 9 or 0x13, and `packet_send`'s
per-type routing table explicitly drops both receiver types (dead end `0x08011988`, §1b
confirms no record exists for cmd 0x09 in the full walk).

New this pass — the hand-off mechanism from app to (absent) bootloader is now fully traced,
not just asserted:

1. Host sends `set 0x00 cmd 0x07` (Enter Loader) to receiver 9. `0x08012320` writes `OOXX` to
   flash page `0x7400` via `0x08012690`.
2. On success, it calls the watchdog-reboot primitive (§3): IWDG armed with a ~100-tick
   reload, flag `0x200000c8` set.
3. The main loop's 100-tick task (`0x0800bd74`) stops refreshing IWDG once it sees the flag.
   The IWDG (not reconfigurable after `IWDG_Enable`, standard STM32 behaviour) expires and
   forces a **hardware reset** — not a jump, not a vector-table rewrite, not an `NVIC`
   software reset call found anywhere near this path.
4. Control passes to the bootloader at `0x08000000`, which is not in this container.

So the open question narrows to exactly one thing: **what the bootloader does on a reset when
it finds the `OOXX` marker at `0x7400`.** Two candidates, unchanged from `fpga-upgrade-path.md`
but now with firmware-side support for the first: (a) the bootloader itself implements
`Update Transmit`/`Update Finish`-equivalent handling and talks to the FPGA directly — this is
*consistent with* the fact that the app's own `Update Confirm` (`0x08`) and `Update Finish`
(`0x0A`) handlers exist and work *before* any reboot (§1b: both are receiver-0x13-only,
runnable pre-reboot), suggesting those two bracket a reboot-mediated transfer rather than
being inside one continuous app-side session; or (b) a path that bypasses the app/bootloader
entirely. Neither is provable without the bootloader image (not obtainable in this container
per `HANDOVER.md`). Treat as **still open**, with the new mechanism (3)-(4) as the concrete
next thing to check once the bootloader binary is available (does it feed the UID/version
area, does it have its own DUML parser using the same CRC seeds as `m0900-can-channels.md`
§4, etc.)

## 6. CAN1 camera/gimbal payload semantics (types 1, 4, 8, 15) — verified negative result

The complete outer-table walk (§1b, 28 records, every one listed) contains **zero** records
with `type` in `{1, 4, 8, 15}`. Cross-checked against `m0900-can-channels.md`'s own
`packet_send` routing table (types 1/4/8/15 → CAN `0x412`/`0x413`, boards 2/4/5/6): m0900 has
no handler that ever fires for a packet whose receiver type is camera/gimbal/DM36x/15. The
*only* types the dispatch table ever matches are `0, 3, 9, 0x13, 0x14(=14)` (§1b) — i.e. a
broadcast/common slot, the FC, the MCU itself, the FPGA, and one DM36x-ish type for the
`Detection` tap (§1b). So: **confirmed, not just "not yet traced" — CAN 0x412/0x413 carries
camera/gimbal DUML that m0900 never inspects at all; it is pure transport**, same as
USART1 for FC traffic except FC traffic (type 3) *is* intercepted twice (§1b: OSD-general
re-fan-out at `0x43`, GPS push tap at `0x1b/0x06`) while camera/gimbal traffic never is. No
new work is possible here without a bus capture or the camera/gimbal firmware's own CAN TX
code (`m0900-can-channels.md` §6 already proposes both next steps; unchanged).

## 6a. A real USART3 (FPGA/radio UART) → USART1 (FC UART) relay, traced end to end (2026-10-25)

Chasing whether `air_router` forwards traffic over RF/CAN to the RC (independent of, and not
relying on, the now-retracted `fc-usb-duml.md` "Breakthrough" log). Found a genuine,
previously-uncatalogued relay path by tracing a scratchpad ring-buffer trail from the main
tick scheduler outward.

- **V, fully traced.** `FUN_080103f8` (not previously named) is called every other tick from
  the main scheduler (`FUN_080105da`, the same function that drives the FPGA bring-up state
  machine). It drains two software ring buffers via the generic ring helpers (`FUN_0800c24c`
  count / `FUN_0800c294` pop / `FUN_0800c274` push — all three already used by the known CAN
  and USART1 pumps), feeds each popped byte to `duml_parser_feed`, and on a complete frame
  (`iVar4==2`) calls **`send_usart1`** directly — **bypassing `air_router`'s own dispatch
  table (`duml_dispatch`) entirely**. This is a raw byte relay, not a routed/interpreted
  forward.
- **V, source of the second ring identified.** The two rings live inside one shared
  per-UART IRQ context array based at `DAT_0800ae6c` (value `0x20000017`); `usart1_irq`,
  `FUN_0800abe4` (unnamed — this is **USART2's** own RX IRQ, by the same pattern and by its
  ring landing at `0x20000053`, matching the pre-existing `can413_pump` board-7 tsv note
  verbatim), and `usart3_irq` each push into their own slot at `+0x14`/`+0x3c`/`+0x64`
  respectively. **`usart3_irq`'s push target (`DAT_0800ae6c+100` = `0x2000007b`) is an exact,
  address-level match for this relay's second ring.** `usart3_irq`'s own DMA source
  (`DAT_0800ae98` = `0x40004800`) is USART3's peripheral base — the UART this project already
  tags "FPGA UART" (`fpga-bringup.md`, `air-router-io-and-naming.md` §4.1).
  **Conclusion: bytes received on the FPGA/radio-facing UART (USART3) that parse as a complete
  DUML frame are relayed, verbatim, straight out the FC-facing UART (USART1) — a real,
  code-confirmed RF/radio-side-to-FC bridge, independent of `air_router`'s own command table.**
  This is architecturally sensible: the FPGA is the OFDM modem that carries the RF link to the
  ground, so inbound ground→air traffic landing on USART3 getting bounced to the FC on USART1
  is exactly what "the MCU is just the router" (this project's one-paragraph model) predicts.
- **V, first ring fully resolved (2026-10-25, same day) — this is the better answer.** Ruled
  out CAN first: traced `can_queue_init`'s 4 real call sites (`FUN_080113a8` registers CAN IDs
  `0x412`/`0x413`; `can_aux_init` registers `0x414`/`0x415`) and none registers `0x20000144` —
  every CAN RX/TX ring is accounted for and none of them is this one, so CAN is ruled out
  entirely, not just "not found by a literal scan." The actual source: **`FUN_0800e008`**
  pushes into this exact ring (`DAT_0800e27c+0x2c` = `0x20000118+0x2c` = `0x20000144`, confirmed
  by address arithmetic). `FUN_0800e008` is a payload descrambler/validator — XORs an 0x38-byte
  buffer against a repeating 8-byte key, runs a two-stage chained checksum (`FUN_08011e54`,
  seeded `0x55aa`), and on success copies a field into the radio-config area and pushes a
  28-byte (`0x1c`) chunk of the payload into this ring. Its **sole caller is `FUN_0800f978`**,
  which is unmistakably the live AD9363/OFDM link's own receive state machine: it polls
  `spi_fpga_raw_read(0xe9)` (an FPGA status register), branches on demod-lock state, calls
  `FUN_0800f6a0()` ("has a new frame arrived") and only then calls `FUN_0800e008` with the
  just-arrived frame. **Conclusion: the first ring is fed directly by demodulated over-the-air
  payloads coming off the real radio link (via the FPGA's SPI status/data interface), not a
  UART or CAN bus at all.** Combined with the USART3 finding above: `fpga_uart_to_fc_relay`
  drains **two independent RF-sourced paths** — one the FPGA's UART framing, one the FPGA's SPI
  payload/status interface — and relays both, verbatim, to the FC. This is about as complete a
  confirmation of "yes, `air_router` forwards RF-link traffic to the FC" as static analysis can
  give without a live RF capture.
- **V, key source traced (2026-10-25, same day) — it's zero, not a secret.** The 8-byte XOR
  key lives at `radio_state_s+0x64` (RAM `0x20001b18`-`0x20001b1f`, inside the struct's
  previously-opaque `pad_10` gap). Checked every write path: no DUML command handler touches
  this offset (Set Config writes the *other*, earlier struct, `radio_cfg_page_s`, not this
  one), and a direct reference search of all 8 individual bytes found zero writers anywhere in
  the firmware. Traced the reset vector into the C-runtime's RAM-init table (two region
  descriptors, each `{src, dst, len, init-fn}`) to see how this RAM starts out: the key's
  address falls inside the second descriptor (`dst=0x200001d0`, `len=0x4ae8`), whose init
  function is a plain zero-fill loop (`stmia` of zero registers, never reading `src` at all) —
  not the compressed-copy decompressor the *first* descriptor uses for `0x20000000-0x200001cf`
  (so this isn't "everything is zero," just this specific range). **Conclusion: the key is
  zero-initialized RAM nothing in this build ever writes — the XOR step is effectively a no-op
  (XOR against zero), and the real work `ofdm_payload_descramble` does is the two-stage chained
  checksum, not encryption.** Possibly wired up for a board variant not active in this build,
  or vestigial from an earlier revision.
- Reproduce: `scratchpad/ghscripts/m0900_fun80103f8.py`, `m0900_ring_writers.py`,
  `m0900_can_init_trace.py`, `m0900_can_queue_init_callers.py`, `m0900_fun0800e008_callers.py`,
  `m0900_check_usart3_ctx.py`, `m0900_all_ring_pushers.py`, `m0900_key_src1.py`-`4.py`,
  `m0900_data_table_entries.py`, `m0900_decomp_fn_dis.py` (all ad hoc, not committed).

## 7. Chip ID / identity — no new readers found

Re-checked (literal-pool scan for `0x1FFFF7E8`, `0xE0042000` DBGMCU, and the full table in §1):
no identity read beyond the already-documented `0x0904`→`0x0954` UID reply
(`fpga-upgrade-path.md`) exists in this image. Nothing new.

## 8. SPI2 / USART2 / CAN2 — no new work this pass

- SPI2 FPGA/AD9363 register catalogue: unchanged from `docs/data/fpga-regs.tsv`
  (`phy-params.md`) — not recomputed here; nothing in §1's handler walk writes SPI2 registers
  outside the already-catalogued paths (cmd 04/05/06/07, boot tables, `tcx_config_update1`).
- USART2 (board 7 only): unchanged from `m0900-can-channels.md` — its RX feeds the *same*
  CAN-0x413 pump/parser/dispatch path on board 7 (confirmed already, not re-derived).
- `can_air_fc2` (FC's second CAN bus): out of scope for m0900 — it's a flight-controller
  (m0306) peripheral, not something m0900's image touches; still `V bus, role U` as
  `naming-map.md` has it. No m0900-side evidence exists to add.

## Method note

No Ghidra project was built. `scratchpad/ghproj` held only m0100/m0305/m0306 projects, no
m0900 one; the task authorized building one, but every open item here resolved cleanly with
`m0900_trace.py`'s capstone sweep (`dis`/`who`/`ptr`) plus the same resynced-sweep primitives
the tool already uses internally (imported directly in a few steps above to get reliable
cross-references, since a *naive* linear disassembly started at an arbitrary mid-function
address through the densely packed `0x080125xx` handler region decodes out of phase and gives
wrong branch targets — this bit the first attempt at tracing §2's caller and was caught by
re-deriving from the tool's own full-image sweep instead of a fresh one-off). If a future task
needs caller chains through indirect/computed calls (none were needed here — every path
above resolved through literal-pool table reads or direct `b`/`b.w`), building the Ghidra
project at that point is the better tool.

## Reproduce

- Full table dump: the inline python snippet in §1.
- Inner-table matcher disasm: `python3 scripts/re/m0900_trace.py dis 0x080112da 30`
- Watchdog-feed gate: `python3 scripts/re/m0900_trace.py dis 0x0800bd74 14`
- Watchdog arm/flag-set primitive: `python3 scripts/re/m0900_trace.py dis 0x0800bd50 18` and
  `dis 0x0800bd82 10`
- Enter Loader full flow incl. the reboot tail: `python3 scripts/re/m0900_trace.py dis
  0x08012320 70`
- SetFPGA (cmd 0x04) vs Set9363 (cmd 0x06): `dis 0x080120e2 14` vs the existing
  `m0900_V01.11.0020.tsv` entry for `0x08012122`.
- Firmware for these commands: copy `P3X_FW_V01.11.0020_m0900.bin` to `firmware/` (gitignored,
  matches `data-manifest.md`'s hash) so `m0900_trace.py`'s default path resolves; or pass the
  path explicitly to `dis`/`who`/`ptr`... (the tool's own `load()` only treats the first
  positional arg as a path when it isn't `dis`/`who`/`ptr`, so pass it after a `dis` command's
  own args, or just use the default `firmware/` location as done here).
