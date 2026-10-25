# m0306 flight-controller bootloader & upgrade scheme

What the P3 FC (STM32F427, module m0306) uses for boot and firmware update, and whether it is a
dual-slot design. Tags: **V** verified in firmware/package, **I** inferred, **U** unknown.
Companion to `app-upgrade-sequence.md` (that doc is the *app/phone* side; this is the *FC* side).
Change history: see docs/HISTORY.md.

## There is a separate bootloader ("Loader"), factory-fixed

- **V** The app reports **two** versions: `Loader   = [V%02d.%02d.%02d.%02d]` and
  `Firmware = [V%02d.%02d.%02d.%02d]` (strings in the decrypted m0306). "Loader" = the bootloader,
  distinct from the app firmware.
- **V** The app image loads at **`0x08020000`**, not the flash base `0x08000000` — the low
  **128 KB (`0x08000000`–`0x0801FFFF`) is reserved for the loader**. Our m0306 is the app only; the
  loader is not in it.
- **V** The OTA package (`P3X_FW_V01.11.0020.bin`) contains **no FC-loader module** — its modules
  are m0306 (FC app), m0305, m0400 (gimbal), m11xx/m12xx (ESCs), m1500 (FX2), m17xx, m1900 (FPGA),
  m0100/m0101 (camera), m0800 (DM368), m0900 (air radio). So the **bootloader is flashed at
  manufacture and never field-updated** — it is the immutable recovery anchor. That is why the app
  can report a Loader version the package never ships.

## The upgrade protocol = streamed in-place reflash (DUML COMMON cmdset 0)

Bootloader/upgrade commands (cmdset 0, from `app-upgrade-sequence.md` / `scripts/re/duml_catalog.py`;
the FC is the receiver). **V**:

| cmd | name | role |
|---|---|---|
| 0x01 | GetVersion | returns Loader + Firmware versions |
| 0x07 | RequestUpgrade | begin: size, target, firmware id |
| 0x08 | RequestReceiveData | FC ready to receive |
| 0x09 | TranslateData | firmware payload, streamed in chunks |
| 0x0A | TranslateComplete | end of stream → verify |
| 0x0B | RestartDevice | reboot (into the loader to apply) |
| 0x0C | GetDeviceStatus | state poll |
| 0x0F | UpgradeSelfRequest | device-initiated upgrade |
| 0x2A | TransferFile | P4-era multi-file transfer |
| 0x41 / 0x42 | ControlUpgrade / GetPushUpgradeStatus | drive + progress |

The result codes name the flash steps the loader performs and so prove an **in-place erase/program/
verify** flow (not a slot swap): `FM_NONSEQUENCE`(240), `FM_LENGTH_WRONG`(241), `FM_CRC_WRONG`(242),
`FLASH_C_WRONG`(243 = erase/check failed), `FLASH_W_WRONG`(244 = write failed), `UPDATE_WRONG`(245),
`FIRM_MATCH_WRONG`(246 = firmware/hardware match check), `UPDATE_WAIT_FINISH`(247),
`UPDATE_MOTOR_WORKING`(249 — refuses to flash with motors spinning; cf. the app string
`system upgrade,stop motor!`), `FLASH_FLUSHING`(253). The DUML `cmd_reboot_mc_request_rcv`
(`0x08042124` in the V01.07.0060 map) is the reboot-into-loader entry (`sender%d request mc reboot`).

## Slots: the APP is single-image, but the LOADER/UPDATER supports two

The STM32F427 die is **always 2 MB dual-bank** silicon — even "1 MB"-marked SKUs are the same part
with the top bank unlabelled/fused (and usually still reachable). So A/B is possible on the hardware.

**At the application level, it is single-image** — **V**: the m0306 app has no reference to the
bank-2 base `0x08100000` (only `0x08000000` ×1 and the app base `0x08020000` ×2), no
`slot`/`bank`/`partition`/`active`/`backup`/`rollback` strings, and is linked at the one fixed base
`0x08020000`.

**But the loader/updater (`m0305`, decompiled — see below) does implement a two-image scheme.**
`m0305` carries a runtime region table over {loader `0x08000000`, app `0x08020000`,
bank2 `0x08100000`} and has **two independent validate+boot paths** — a blank/erased check
(all-`0xFFFFFFFF`) and a "set MSP = vector[0], jump to vector[1]" boot routine for **each of two
slots** (table+0x14 and table+0x30). So the boot architecture can hold and select a second image
(A/B, or main + golden/recovery). Which bank each slot maps to, and the switch/rollback policy, are
**U** (the table is populated at runtime; needs a dump with live values or more trace). What is
solid: the capability and the mechanism exist in the loader, even though the running app ignores it.

### The resident bootloader is NOT identified (and what `m0305` is)

The resident flash bootloader — the "Loader" at `0x08000000` whose version the app reports — is
**not identified**: it is not in our m0306 app image (which begins at `0x08020000`) and there is no
`0x08000000`-based flash module in the OTA package. Confirming what it does (secure-boot?
signature? bank-2 use?) needs a **SWD dump of `0x08000000–0x0801FFFF`** from the board. **U.**

The package *does* carry a separate **`m0305`** module (~43 KB, AES-encrypted like the rest,
MD5-OK) sitting beside the FC app. Vector table **SP `0x1000e4e8` (CCM RAM @ 0x10000000), reset
`0x200002c9` (main SRAM @ 0x20000000)** → a **RAM-resident image linked to run from SRAM** (confirms
STM32F4: CCM @ 0x10000000), with essentially no strings (pure code). **Decompiled** (base
`0x20000000`, `scripts/re/ghidra/m0305_flash.py` + `m0305_regions.py`), it is the FC's
**RAM-resident bootloader/updater** — more than a dumb programmer. **V:**

- **Full STM32 flash driver:** `FLASH_Unlock` (writes `FLASH_KEYR` = `0x45670123`/`0xCDEF89AB`,
  `FUN_20001660`-area), **option-byte unlock** (`FLASH_OPTKEYR` = `0x08192A3B`/`0x4C5D6E7F`), sector
  erase (`FUN_2000156c`: sets `FLASH_CR` SNB/SER/PSIZE/STRT, polls BSY), status decode
  (`FUN_200015d8` → busy/error/EOP codes that map to the DUML `FLASH_*_WRONG` results), `FLASH_Lock`.
- **Its own clock init** (`FUN_20003398`: HSE→PLL, `FLASH_ACR`=`0x705` = 5 WS + I/D-cache + prefetch).
- **DUML over CAN** (CAN1/CAN2 bases + the `0x55` SOF and CRC16 `0x3692` table present) — it receives
  the image on the FC's CAN link.
- **Two-image boot/select** over a region table {loader/app/bank2} — the A/B-capable logic described
  above.

So `m0305` is the RAM-side half of the boot/upgrade system: delivered in, it reconfigures clocks,
speaks DUML to receive firmware, erases/programs flash, can rewrite option bytes, and can
validate+boot either of two image slots. The *resident* loader at `0x08000000` (what launches
`m0305`) is still the one piece not in hand; a SWD dump would close it out. **I** (strong) that
`m0305` is loaded/used by that resident loader during update.

### `m0305` command set vs a classic bootloader — and the A/B slot layout

The handlers match a standard field-update bootloader, and the erase targets pin the slot map via
the F427 2 MB dual-bank sector layout (bank1 = sectors 0–11, bank2 = 12–23; sectors 0–3 =16 KB,
4 =64 KB, 5–11 =128 KB):

| bootloader op | m0305 | note |
|---|---|---|
| Unlock | `FUN_20001660`-area writes `FLASH_KEYR` 0x45670123/0xCDEF89AB | flash write-enable |
| OB Unlock / Write | `FUN_20007d0c` → OPTKEYR unlock + writes an option byte (0x55 marker) unless already 'U' | touches option bytes |
| Erase | `FUN_20007c28`(start,end sectors); `FUN_20008c88`: **type 6 → sectors 5–11 = `0x08020000` bank-1 app slot**, **type 7 → sectors 12–23 = `0x08100000` bank-2 slot**; **sectors 0–4 (`0x08000000` loader) never erased** | per-slot erase, loader preserved |
| Program | word-program via `FLASH_CR` PG (program path) | writes the received image |
| Verify | per-slot **validate** `FUN_20007a30`/`200081f0` = blank-check + marker-word match (image word == expected constant) + vector-table sanity | marker+sanity, **not** a full-image CRC at boot |
| Go / Boot | `FUN_20007ec0`/`20007edc`: set MSP=vector[0], jump vector[1] | boot slot A, else slot B |
| **Read Memory** | **absent** | no flash read-out/dump command found |

So the slots are **bank-1 app (`0x08020000`) and bank-2 (`0x08100000`) = true dual-bank A/B**, with
the loader (sectors 0–4) kept out of the erase path.

**Target "types" and external selection.** The erase descriptor's type field selects the target:
**type 6 → bank-1 app slot, type 7 → bank-2 slot** (verified). Values **0–5 are undetermined** —
the erase dispatcher (`FUN_20008c88`) branches only on 6/7; 0–5 are other entries in DJI's generic
updater descriptor enum but their meaning isn't established here (**U**; would need the descriptor
enum / `RequestUpgrade` target parser). *Programming* is therefore externally selectable — the host
picks the bank via the type in the DUML command. *Booting* is **not** a "boot slot N" command: the
loader auto-selects (validate slot A → boot; else slot B; else update mode). There is one external
boot control: `FUN_20006f04` reads an **update-pending flag** (`FUN_20008280`→`FUN_20007ab4(…,0xc0)`);
nonzero forces update mode instead of booting — the standard "app sets flag, reboots, loader stays
in the updater" handoff. No evidence of an external override to force-boot a *specific* slot. **V**
for 6/7 + the force-update gate; **U** for types 0–5 and any per-slot boot override. **Verify** exists but is a marker-word + blank
+ vector sanity check at boot (the transfer itself is CRC'd during `TranslateData`, the
`FM_CRC_WRONG` path) — there is **no full-image-CRC or host-"verify-digest" command**. **Read** —
unlike the ST system bootloader's Read Memory (0x11) — has **no equivalent here**: `m0305` reads
flash only internally (blank/marker/boot), with no command to stream flash back out. So even in
update mode you cannot dump the image over DUML/CAN; reading it still needs SWD. **V** (the handlers
decompiled; absence of a read-out command).

## Reproduce
```
strings -n4 m0306_dec.bin | grep -E 'Loader   = |Firmware = |system upgrade|request mc reboot'
# bank-2 / region constants (expect no 0x08100000):
python3 - m0306_dec.bin <<'PY'
import struct,sys;d=open(sys.argv[1],'rb').read()
for t in (0x08000000,0x08020000,0x08100000):
    print(hex(t), sum(struct.unpack_from('<I',d,i)[0]==t for i in range(0,len(d)-3,4)))
PY
```

## Integrity check: CRC + MD5 + AES, NOT a cryptographic signature

What protects the P3 FC image is checksums + the module encryption, not a public-key signature:

- **No signature primitives.** The decrypted m0306 has **no** `signature`/`RSA`/`ECDSA`/`SHA`/`cert`
  strings. What it does have: `verify_crc16_checksum` (CRC16), a config/param **hash**
  (`cfg err hash`, `hash table is not match cfg_table`), a flash-write **key** gate
  (`invalid flash key`, `[whitelist]invalid flash key`), an AES decrypt routine
  (`decrypting:Ibuf…`, `DJI-DEMO AES256 KEY-…` — used for SDK activation, not the image), and
  activation/license (`ActiveStatus` 0x32, `LockLicense` 0x34, `CmdNeedEncrypt` 0xcc). **V.**
- **The integrity chain is therefore:** (1) xV4 module **AES-128** encryption (`encrypt_type=1`,
  public key — `scripts/re/xv4_decrypt.py`); (2) container **MD5** (`decrypted_md5` per module);
  (3) upgrade-stream **CRC** (the `FM_CRC_WRONG`=242 / `FLASH_C_WRONG`=243 result codes); (4)
  `FIRM_MATCH_WRONG`=246 version/hardware match. No step is a signature, so **anyone holding the
  (public) module AES key can craft an image the loader accepts** — the long-known basis for custom
  P3 firmware. This is the xV4 era; DJI's **signed** format (`IM*H`, `dji_imah_fwsig.py`) arrives on
  the newer, SAM E70-class products (e.g. the P4-generation / Spark lineage), so the P4 FC likely
  *is* signed — a contrast worth testing if its image is ever obtained. **I** for the P4 side.

## Is there a DUML command that reads/writes memory directly?

Checked the full 723-entry DUML catalog (`scripts/re/duml_catalog.py`). **There is no
general peek/poke (read/write arbitrary address) command on the FC.** The only memory-touching
paths are structured and gated:

- **Flash write** only via the upgrade state machine — `RequestUpgrade`(0x00,0x07) →
  `RequestReceiveData`(0x08) → `TranslateData`(0x09, the bytes) → `TranslateComplete`(0x0A) →
  `RestartDevice`(0x0B), behind the flash-key + CRC + `FIRM_MATCH` + motor-stopped gates. It writes
  the image, not an arbitrary address you choose.
- **Config read/write by index** — `GetParamInfoByIndex`(0x03,0xf0), `GetParamsByIndex`(0xf1),
  `SetParamsByIndex`(0xf2): reach any `g_config` field, but *by table index with min/max
  validation* (see `fc-io-inventory.md`), not raw memory.
- **File transfer** — `RequestFile`/`GetPushFile`/`TransferFile`(0x00,0x26/0x27/0x2a): SD-card/log
  files, not MCU memory. The only `Debug`-named commands are OSD `GetPushDebugInfo`(0x09,0x16) /
  `SetDebugVideo`(0x09,0xf0) and EYE `DebugCtrlParam`(0x0a,0x09) — telemetry/video, not memory.

**Consequence for "verify the on-chip image":** there is **no DUML flash-read-back**, so you cannot
dump or verify the installed firmware over DUML — only `GetVersion`(0x01) reports the Loader/Firmware
version numbers. Reading the actual bytes (to verify, or to pull the immutable loader at
`0x08000000`) needs **SWD/JTAG** on the board, not the DUML link. **V** (absence of a read-mem cmd).

## Does this apply to the other chips? (the universal constraint, two solutions)

The reason the FC updater runs from RAM is a hardware rule: **the flash-programming code can never
execute from the flash region being erased/programmed** — the flash bus stalls during an
erase/write, so instruction fetch from it would hang. Every self-flashing MCU here obeys it; they
differ in *where* the programmer runs:

| Chip | How it flashes itself | Evidence |
|---|---|---|
| **STM32F427 FC** (m0306/m0305) | **downloads a RAM-resident programmer** (`m0305`) that runs from SRAM; full driver (KEYR unlock, erase, program, OPTKEYR), dual-bank A/B, DUML-over-CAN | decompiled, this doc |
| **STM32 gimbal** (m0400) | **loader + app**, generic DUML update cmds: `packet_exec_gener_enter_loader` / `_update_transmit` / `_update_finish` / `_update_confirm` / `_reboot_chip`, `store_boot_loader` | upstream m0400 map |
| **STM32F103 air radio** (m0900) | same STM32 family pattern presumed; its loader isn't in the (sparse) map | `update_board_version` only — **U** on the loader |
| **NXP LPC1765 ground radio** (m1400) | **on-chip ROM IAP** — programmer lives in the LPC boot ROM (`iap_entry` @ `0x1FFF1FF1`), so it runs from ROM, not user flash; **no RAM download needed**. Data still staged in RAM (`Chip_IAP_CopyRamToFlash`). | upstream m1400 map: `Chip_IAP_EraseSector/CopyRamToFlash/BlankCheckSector/Compare/PreSectorForReadWrite`, `iap_entry` |

So: the **RAM-resident downloaded programmer is an STM32-family solution** (ST has no flash-program
ROM, so DJI ships the programmer as code and runs it from SRAM). The **LPC uses NXP's ROM IAP**
instead — same constraint, met by the silicon vendor's boot ROM. On the **verify/read** question
across chips: the LPC's ROM IAP exposes **`Chip_IAP_Compare` (verify)** and `BlankCheckSector`
directly, and LPC memory is ordinarily readable; the STM32 FC updater has only its marker+blank
validate and no read-out (above).

**Documentation status:** the LPC `Chip_IAP_*` names are NXP's standard **LPCOpen** library (so that
layer is "documented" by the vendor and carried verbatim in the symbol map). The DJI-specific pieces
— the `m0305` RAM-resident FC updater, the FC dual-bank A/B slot map, the type-6/7 targets — are
**not** covered by o-gs/dji-firmware-tools (which handles the container + parameters, not loader
internals), so the analysis in this doc is original RE. The gimbal's `packet_exec_gener_*` update
command names do appear in the upstream map.

**Remaining open (U):** `m0305` target types 0–5 (6/7 confirmed), the air-radio (m0900) loader, and
the resident FC loader at `0x08000000` (needs an SWD dump). Everything else in the FC boot/upgrade
path is now analysed.

## Image-acceptance marker + the type-0-5 resolution

- **Valid-image marker:** the loader's slot-validate (`FUN_20007a30`) checks an image word equals
  **`0x77557755`** (`DAT_20007a74`) at a fixed header offset (`*(*(desc+0x2c) - 0xf)`), on top of
  the blank-check and vector-table sanity. `0x77557755` is a DJI magic (the DUML `0x55` SOF and
  `0x77` CRC8 seed, doubled). A flashable image must carry it. The exact byte offset in the image
  header is still to be pinned for building one (**U**, needs the header struct confirmed).
- **Types 0-5:** the erase/program *target* type is **6 = bank-1 app, 7 = bank-2** only; `m0305`
  never uses 0-5. The other "type" seen (`FUN_2000723c`, values 3/5) is the DUML **sender device
  type**, a different field. So 0-5 are other modules' targets in DJI's shared updater enum, not FC
  banks — not exercised here (**U**, by design).

## Can the resident loader be obtained elsewhere? (no — SWD only)

Checked whether the resident loader (sectors 0–4, `0x08000000`) is already available:

- **Not in any OTA package.** The o-gs/dji-firmware-tools wiki states the m0306 package "programs
  the **application part**" of the STM32F427 — the bootloader is factory-only and ships in **no**
  DJI firmware package, for any product. Confirmed locally: the P3 package has only `m0306` (app) +
  `m0305` (RAM updater) for device-type 3; `m0305` holds no `0x08000000` flash vector table.
- **No published dump found.** No community release of the P3 FC bootloader surfaced; the documented
  route to full flash is **SWD/ST-Link on the board's SWD pins** (per the same wiki). Any copy that
  exists is a private SWD dump.
- **We already have most of its logic.** `m0305` carries the full boot-decision (A/B validate+boot),
  flash driver and DUML/CAN update path, so a sectors-0–4 dump would add mainly the thin reset/copy
  stub that bootstraps `m0305`.
- **One thing may be unique to it.** A Hackaday Naza-M teardown found a DJI bootloader holding a
  "secret seed" used for authentication — i.e. the resident loader *can* hold auth material absent
  from the app/updater. On the P3 FC this is unverified (**U**), but it is the one concrete reason
  the resident loader is worth a SWD dump beyond completeness. (Scope note: the interest here is the
  boot chain and a clean replacement, not DJI activation/licensing or geofence defeat, which stay
  out of scope per `autonomy-onboard-plan.md`.)

## Is a loader-resident secret actually needed? (searched the app — no evidence)

Patching needs no secret (no signature; the module AES key is public), so the only reason to want
the loader is a possible secret/seed (cf. the Naza-M precedent). Searched the m0306 app for the
three ways such a secret would surface:

- **Reads from non-flash / never-written storage:** the app reads the **STM32 96-bit UID**
  (`0x1FFF7A10`, `uid96_read` @ 0x0808527a) — but its only consumer is `id10_build` (@ 0x080596ea),
  which builds the FC's **device identity** (base + `UID[0]`). Identity/serial, **not** a key. **No**
  reads of the STM32 **OTP** (`0x1FFF7800`), **option bytes**, or **system-memory ROM** (scanned, 0
  refs each).
- **Reads into / calls the loader flash (`0x08000000–0x0801FFFF`):** ~93 word references exist
  (the `Loader = [V…]` version read and shared data), but none resolves to a **secret** handoff; the
  activation path is app-side (`is_prod_activated`, `check_activation_authority`, `dji_sdk_set_key`)
  with the SDK key **supplied externally**, not derived from the loader.

**Conclusion:** no app-side evidence that a loader-resident secret is required — consistent with the
no-signature finding. The patch/replacement path needs nothing from the loader; the loader stays a
completeness item (any seed like the Naza-M's is unverified here, **U**, and only confirmable by a
SWD dump).

### Approach-B hijack candidates (already present in the app)

For the surgical-patch dump, besides a null param callback there are existing entry points to
repurpose: many `nullsub_*` stub handlers (e.g. `nullsub_23` @0x08046640, numerous others), and two
intriguing config entries — `api_entry_cfg.cheat_backdoor` and
`config_status.factory_output_test_request` — a factory/test path is a lower-safety-impact slot to
trigger a diagnostic payload. What each does is unverified (**U**); worth a look as the cleanest
trigger when building Approach B.
