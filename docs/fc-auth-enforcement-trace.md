# FC/A9 auth-check enforcement trace — what the callers do on failure

Answers the open item in issue #45: when `DjiMsgAuthorizedMac` / `DjiEncryptCheckA9Mac` /
`DjiEncryptCheckSN` (A9, `m0100`) and the activation check (FC, `m0306`) **fail**, what do
their **callers** actually do — reject only a client/app connection, or gate something on the
hardware side (boot/video/flight)? Tags: **V** verified (decompiled), **I** inferred, **U**
unknown/needs more RE. Companion: `security-and-activation.md` (summary table this trace
updates), `atsha204-repair-note.md`.

## Method / tooling note

All addresses below were re-derived directly in this session from the two pre-built Ghidra
projects (`m0100sys` = A9 ThreadX sys partition @ base `0x0E600000`; `m0306` = STM32F427 FC app,
loaded at base `0x08020000`), using Jython scripts under `scripts/re/ghidra/` (run via
`analyzeHeadless ... -noprocess -scriptPath scripts/re/ghidra -postScript <script>.py`) plus two
plain Python helpers (`disasm_window.py`, `find_movwt_motorstop.py`, Capstone-based) for the one
case where Ghidra's own analysis didn't reach the code. Decompiler output is Ghidra's
pseudo-C (`FUN_xxxxxxxx` = unnamed function at address `xxxxxxxx`; `DAT_xxxxxxxx` = a
global/pointer variable at that address).

**Important correction to `security-and-activation.md`'s cached addresses:** the addresses
`is_prod_activated` (`0x08047c2c`), `check_activation_authority` (`0x08047d5e`), and
`dji_sdk_set_key` (`0x0805a964`) in that doc were taken from a **different firmware build**'s
symbol map (`docs/symbols/upstream/P3X_FW_V01.07.0060_m0306.map`), not from
`P3X_FW_V01.11.0020_m0306.bin` (the binary actually loaded in the `m0306` Ghidra project handed
to this session). In the `V01.11.0020` build those three addresses land inside an unrelated MD5
compression routine (`FUN_08047c08`) or a few instructions off a different function's body —
confirmed by: `getFunctionAt()`/`getFunctionContaining()` returning that MD5 function for both,
and `0x08047c2c` not even being disassembled as code (`getCodeUnitAt` → `None`). The real
addresses for this build are given below (§2), re-found via the string/log-table trail rather
than trusting the stale map.

---

## 1. A9 (`m0100`) — `DjiMsgAuthorizedMac`, `DjiEncryptCheckA9Mac`, `DjiEncryptCheckSN`

### 1.1 `DjiMsgAuthorizedMac` (0x0e85f370) — no in-image caller found (**U**)

**V** — decompiled, confirms the 6-byte Ethernet-MAC compare and `0`/`0xe6` return (see
`security-and-activation.md` §2a).

**U** — `getReferencesTo()` on this function's entry point returns **zero** results in the
`m0100sys` project, and a raw byte-level scan of the whole partition for the literal 4-byte
pointer `0x0e85f370` also finds **zero** hits (script: `fc_mac_refs.py`, `fc_mac_scanptr.py`).
So within the ThreadX sys-partition image we have, this function has **no caller at all** — it
is reached from somewhere this Ghidra project doesn't cover, almost certainly the A9's Linux
userspace `cam_server` binary (not available to this session) via whatever cross-core/IPC path
connects the Linux side to this ThreadX partition. **This specific function's enforcement point
remains unconfirmed** — the claim in `security-and-activation.md` that "`cam_server` rejects
clients whose MAC is not authorized" is **not re-verified in-code here**; it rests on the
earlier string-based reading (`Update authorized MAC: ...`, `t dji mac ...`). Needs the
`cam_server` ELF to close out.

### 1.2 `DjiEncryptCheckA9Mac` (0x0e871ae0) / `DjiEncryptCheckSN` (0x0e8731cc) — traced 3 hops up

Caller chain (script: `fc_auth_callers.py`, `fc_auth_callers2.py`, `fc_auth_callers3.py`):

```
FUN_0e8734fc  (calls CheckA9Mac @0x0e871ae0, then CheckSN @0x0e8731cc)
  -> called by FUN_0e872bb8  @0x0e872bb8
       -> called by FUN_0e872e38 @0x0e872e38
```
`DjiEncryptCheckSN` also has a second, independent caller:
```
FUN_0e83c59c  (calls CheckSN @0x0e8731cc directly, inside a per-record loop)
  -> called by FUN_0e8475b8 @0x0e8475b8   (a 4-case DUML-style command dispatcher)
```

**V — `FUN_0e872bb8` (0x0e872bb8), the retry+status wrapper.** Decompiled:
```c
*param_1 = 1;
while ((iVar1 = FUN_0e8734fc(), iVar1 != 0) && (++uVar4 < 3)) {
    /* log retry */
    FUN_0e6f44e4(1000);          // sleep 1s
}
if (uVar4 == 3) { *param_2 = 0; FUN_0e860560(0); }   // 3 failed retries -> status 0
else            { *param_2 = 1; FUN_0e860560(1); }   // success        -> status 1
```
So a failed `CheckA9Mac`/`CheckSN` is retried up to 3 times (1 s apart), and the **final
pass/fail result is persisted into a global status flag** via `FUN_0e860560(0|1|2)` — not just
returned to whoever asked.

**V — `FUN_0e860560` (0x0e860560), the status setter**, writes straight into RAM:
```c
undefined4 FUN_0e860560(int param_1) {
    if (param_1==0 || param_1==1 || param_1==2) { *DAT_0e861450 = param_1; return 0; }
    /* else: log "bad value", return -1 */
}
```
`DAT_0e861450` resolves (traced in the function body's own references) to RAM address
**`0x109d00b8`** — i.e. the A9Mac/SN pass-fail outcome lives in a RAM variable, not just a return
code. **V** — the matching getter is `FUN_0e8605fc`: `return *DAT_0e861450;` (reads the same RAM
slot).

**V — who reads that status flag (`FUN_0e8605fc`), 4 distinct call sites** (script:
`fc_statusgetter.py`):

1. **`FUN_0e83c1a8`** (0x0e83c1a8): `if (status==0) return 0;` — otherwise it builds an
   identity/SN record (`FUN_0e83c024`) and either sends a DUML-style report
   (`FUN_0e864ca0(0,0x32,...)`, opcode `0x32`) **or** calls `FUN_0e81aeac(0x200,0)`, which clears
   bit `0x200` in a flags register (`*DAT_0e81bcf4`) — i.e. **an enable/feature bit is
   cleared** when this path is taken. When status==0 (not authorized) this whole branch is
   skipped — the function just returns 0 immediately, performing **none** of that work.
2. **`FUN_0e8a2080`** (0x0e8a2080): `iVar2 = FUN_0e8605fc(); if (iVar2==0) { log; return -0x1c; }`
   — on status==0 (unauthorized) it **aborts with an error and does not perform** the rest of the
   function: a buffer setup (`FUN_0e81b998`, `FUN_0e839690`→`FUN_0e71ff1c`), a per-channel table
   lookup (`FUN_0e89a998`), and enable calls `FUN_0e899dcc(0)` / `FUN_0e899dcc(1)`. On status!=0
   it runs all of that. **I** — the exact subsystem these enable calls bring up is not pinned
   down further in this pass (candidate: radio/link channel bring-up, given the neighboring code
   deals with Wi-Fi channel tables — see next item — but this is inference, not proof).
3. **`FUN_0e8ac25c`** (0x0e8ac25c): as one term of a multi-condition gate
   (`status!=0 && FUN_0e866470()!=0 && ...`) before iterating Wi-Fi-channel-shaped indices `0..0x1f`
   (`FUN_0e89add0`/`FUN_0e89c654` per index) and calling `FUN_0e8a5a78(1)` ("set mode 1"). **I** —
   reads as a channel/RF-mode enable gated (in part) on the auth status, consistent with the A9's
   Wi-Fi stack (`link-security.md`), but the full semantics of `FUN_0e8a5a78`/`FUN_0e866470`
   weren't decompiled further in this pass.
4. **`FUN_0e860690`** (0x0e860690): uses the status value as one field in a table-lookup match
   (mode dispatch), lower-confidence read.

**Verdict for §1.2 (V for the control-flow; I for the exact subsystem named):** the
ATSHA204 A9Mac/SN check's result is **not confined to a connection-accept/reject answer**. It is
latched into a persistent on-device status flag that **multiple other A9 functions branch on**,
skipping real work (a DUML report send, an enable-bit clear, a buffer/channel setup sequence,
part of a Wi-Fi-channel-enable gate) when the status is "unauthorized." This is a materially
different, and more hardware-adjacent, picture than "`cam_server` rejects the client and nothing
else" — but it still is **not** shown to touch the FC (`m0306`) or motor/flight path; it's an
A9-side (camera/video/link) gate. Whether any of items 2–4 is literally "start the video stream"
or "bring up Wi-Fi" remains **I/U** pending further decompilation of `FUN_0e866470`,
`FUN_0e8a5a78`, and the `FUN_0e89xxx` channel helpers.

**V — the other `CheckSN` caller, `FUN_0e8475b8`** (a 4-case command dispatcher: SN read / SN
write / `FUN_0e83c59c` (provisioning loop) / factory-record case): this path returns an error
code (`0xe3`/etc.) straight to its own caller — it reads as a **protocol-level response path**
(answering a DUML-style request), i.e. client/app-facing, not a subsystem gate. Its own caller
wasn't found in-image (0 refs) — likely invoked via the same kind of command-dispatch table
pattern as above, outside what's resolvable without the dispatcher's own call table.

---

## 2. FC (`m0306`) — the activation → motor-start gate

### 2.1 Real addresses in `P3X_FW_V01.11.0020_m0306.bin` (base `0x08020000`)

Found via the firmware's own PC→string log-record table (a `{check_fn_ptr (thumb-tagged),
msg_ptr, id}` triplet array near the end of flash) rather than trusting the stale map: the
string `"Product not activation,stop motor!"` lives at `0x080fba67` (a **second**, referenced
copy — a first, unreferenced copy of the same string sits at `0x080254a4` and is dead data in
this build). Its paired log-table entry names call-site `0x0809dd73`
(scripts: `fc_motorstop_string.py` → `fc_motorstop4.py` → `fc_motorstop5.py`;
`py/disasm_window.py` for the raw Capstone disassembly that located the real table/functions
Ghidra's own auto-analysis hadn't reached).

* **`FUN_08046d54`** (`0x08046d54`) — **the real activation-state read**:
  `return *(byte*)(DAT_08047028 + 0x28);` — a single byte read from a global "comms/activation"
  struct. This is the direct equivalent of the old doc's `is_prod_activated`.
* That byte is **written** by `FUN_08046cfe` (`0x08046cfe`) when an incoming 8-byte record
  arrives (looks like a received DUML message payload being staged into the struct and queued).
* **`fc_sdk_set_key`** (`0x08046e86`, Ghidra auto-recovered this name from debug/symbol
  remnants) — the SDK/API-key handshake: validates a magic (`0x2766`/`DJI_DEMO_AES256_KEY...`),
  retries up to 10 times (logs `"req %d real %d %d"`, `"[SDK USER] sdk_set_key: %s"`), and is the
  direct equivalent of the old doc's `dji_sdk_set_key`/`check_activation_authority` — i.e. the
  **key is supplied externally** (DJI app/server), matching the existing doc's claim, now
  re-confirmed in the `V01.11.0020` build at this (different) address.

### 2.2 The actual motor-start gate: `FUN_08024b46`

**V** — decompiled in full. This is a long sequential preflight-check function (battery level,
compass, GPS, IMU calibration, ESC error, novice mode, geofence/whitelist, simulator state,
gyro/accel/press "stuck" sensors, gear-pack mode, etc. — dozens of checks) that computes an
overall "motor OK" boolean (`cVar10`) and feeds the "`%s M %5s %s`" / "`%s M Start %s FAIL! %s`"
log lines and a start counter. The activation check is one line in that chain:
```c
iVar8 = FUN_08046d54();
if ((iVar8 == 0) && ((char)puVar4[0x7f] == '\0')) {
    *(undefined1 *)((int)puVar6 + 5) = 0x16;                    // fail-reason id 0x16
    pcVar11 = s_Product_not_activation_stop_moto_080254a4;      // the exact string
    goto LAB_08025376;                                          // -> cVar10 = '\0' (FAIL)
}
```
When `FUN_08046d54()==0` (device reports "not activated"), this clears the overall go/no-go flag
(`cVar10 = '\0'`) exactly the same way every other hard stop-motor condition in this function
does (low battery, ESC error, ...) — i.e. activation sits in the **same gate list as the safety
interlocks**, not in a separate client-authorization path.

### 2.3 Second, table-driven implementation of the same gate (`fc_Motor_fail` / `fc_Motor_Start`)

Ghidra auto-recovered real names for this cluster, confirming it's the live motor-arm logic
(script: `fc_motorstop5.py`):

* **`fc_Motor_fail`** (`0x0809dda4`) iterates a **29-entry** table of boolean check functions
  (same conceptual check list as §2.2, implemented as function pointers + id + message instead of
  an if-chain). One of the 29 entries is **`FUN_0809dd72`**, newly named here, which is exactly
  the activation check: `return (FUN_08046d54() == 0) ? 0 : 1;` — i.e., wraps the same
  `FUN_08046d54` read into the table's "1 = this check passed" convention. On any entry's failure
  it calls a logging callback (`FUN_080677a2()->+0xc`) with the id/message and returns a nonzero
  "has failed check(s)" status to its caller.
* **`fc_Motor_Start`** (`0x0809de80`) calls `fc_Motor_fail(...)` and uses its result together with
  armed-state bytes (`*(iVar1+0x350)`/`+0x351`/`+0x352`) to decide whether the motor actually
  transitions to the armed/started state, logging `"%s Motor %5s reason: %s"` and
  `"%s Motor Start failed, start reason:..."`.
* **`FUN_0809de70`** (`0x0809de70`) is a convenience "can the motor run?" accessor
  (`return fc_Motor_fail()!=0 ? 0 : 1;`), consumed by:
  * **`fc_MOTOR_HAVE_STARTED`** (`0x080a1482`) — reports `MOTOR_HAVE_STARTED` vs. runs the
    fail-reason path,
  * **`FUN_080a7e84`** (`0x080a7e84`) — a flight-mode-applicability gate (`INAPPLICABLE_FLY_MODE`,
    `MOTOR_ON`/`MOTOR_OFF` reasons),
  * **`FUN_080a8010`** (`0x080a8010`) — the auto-takeoff mission state machine (`TO_DO` state 0
    calls it before letting takeoff proceed).

**Verdict for §2 (V):** unlike the A9 ATSHA204 check, the FC activation check is **directly and
verifiably wired into the actual motor-arm/motor-start code path**, in two parallel
implementations that both read the same `FUN_08046d54` activation byte, and that result also
gates the auto-takeoff state machine. This is **hardware behaviour** (the firmware will not let
the motor-start sequence proceed), not a client/app connection-level rejection — confirming (and
now re-grounding, with correct in-build addresses) the existing `security-and-activation.md`
claim.

---

## 3. Net answer to issue #45

| Check | Caller behaviour on failure | Scope |
|---|---|---|
| `DjiMsgAuthorizedMac` (A9 Ethernet-MAC pairing) | **U** — no in-image caller found; likely enforced in the (unavailable) `cam_server` Linux binary | presumed client/app-facing (not re-verified here) |
| `DjiEncryptCheckA9Mac` / `DjiEncryptCheckSN` (A9 ATSHA204 crypto MAC) | **V** — retried 3x, then latched into a persistent RAM status flag; **multiple A9 functions skip real work** (a DUML report, a feature-enable bit, a buffer/channel-setup sequence, part of a Wi-Fi-channel gate) when that flag says "unauthorized" | **A9-side feature/subsystem gating**, more than just connection accept/reject — but still **not** shown to reach the FC or motor/flight path. Exactly which subsystem(s) is **I/U**. |
| FC activation check (`FUN_08046d54`, fed by `fc_sdk_set_key`) | **V** — directly gates `FUN_08024b46`'s and `fc_Motor_fail`'s overall motor-arm go/no-go, in the same list as battery/ESC/IMU safety interlocks; also read by the auto-takeoff state machine | **Hardware behaviour** — firmware won't arm/start the motor. Confirms existing doc, with corrected in-build addresses. |

So the picture is more nuanced than a strict "client-reject vs. motor-stop" binary: the FC
activation gate is unambiguously a hardware motor-start block (§2); the A9 ATSHA204 MAC/SN check
is **not merely a connection filter either** — its result gates at least one, and plausibly more,
on-device A9 feature paths (§1.2) — but no evidence found in this pass connects it to the FC or
to flight/boot. The weakest link remains `DjiMsgAuthorizedMac` itself, whose caller lives outside
the Ghidra projects available to this session.

## Scripts

All reproducible via `analyzeHeadless <ghproj> <program> -noanalysis -scriptPath
scripts/re/ghidra -postScript <name>.py`, saved in `scripts/re/ghidra/`:
`fc_auth_callers.py`, `fc_auth_callers2.py`, `fc_auth_callers3.py` (A9 caller-chain walk),
`fc_statusflag.py`, `fc_statusflag2.py`, `fc_statusgetter.py`, `fc_statuscallees.py` (A9 status
flag trace), `fc_mac_refs.py`, `fc_mac_scanptr.py` (the `DjiMsgAuthorizedMac` no-caller check),
`fc_memmap.py`, `fc_act_probe.py`, `fc_probe2.py` (m0306 address/base verification),
`fc_activation_gate.py` (the initial, stale-address attempt — kept to document the version
mismatch), `fc_motorstop_string.py` → `fc_motorstop2.py` → `fc_motorstop3.py` →
`fc_motorstop4.py` → `fc_motorstop5.py` (the string/log-table trail to the real m0306
addresses), `fc_actflag_writers.py` (activation-byte producer side). Plain-Python Capstone
helpers: `disasm_window.py`, `find_movwt_motorstop.py`.
