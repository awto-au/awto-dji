# m0306 flight-controller bootloader & upgrade scheme

What the P3 FC (STM32F427, module m0306) uses for boot and firmware update, and whether it is a
dual-slot design. Tags: **V** verified in firmware/package, **I** inferred, **U** unknown.
Companion to `app-upgrade-sequence.md` (that doc is the *app/phone* side; this is the *FC* side).

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

## Slots: the APP is single-image, but the LOADER/UPDATER supports two (CORRECTED)

The STM32F427 die is **always 2 MB dual-bank** silicon — even "1 MB"-marked SKUs are the same part
with the top bank unlabelled/fused (and usually still reachable). So A/B is possible on the hardware.

**At the application level, it is single-image** — **V**: the m0306 app has no reference to the
bank-2 base `0x08100000` (only `0x08000000` ×1 and the app base `0x08020000` ×2), no
`slot`/`bank`/`partition`/`active`/`backup`/`rollback` strings, and is linked at the one fixed base
`0x08020000`.

**But the loader/updater (`m0305`, decompiled — see below) does implement a two-image scheme.** An
earlier draft here concluded "single-slot, no A/B" from the app alone; that was premature and is
**corrected**: `m0305` carries a runtime region table over {loader `0x08000000`, app `0x08020000`,
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
speaks DUML to receive firmware, erases/programs flash (app, and — by its table — potentially the
loader `0x08000000` and bank2), can rewrite option bytes, and can validate+boot either of two image
slots. The *resident* loader at `0x08000000` (what launches `m0305`) is still the one piece not in
hand; a SWD dump would close it out. **I** (strong) that `m0305` is loaded/used by that resident
loader during update.

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
