# Replacement FC firmware + bootloader-dump: plan

Goal, near-term: a **clean-room replacement FC app** for the STM32F427 (m0306) that the **stock DJI
loader will accept and flash**, whose first job is to **add a DUML "read memory" command and dump
the resident bootloader** (`0x08000000–0x0801FFFF`) — the one piece we cannot otherwise read without
SWD. Longer-term: the same app is the base for owned-aircraft autonomy work.

This is bench reverse-engineering on an aircraft the operator owns. **Flight is out of scope here**
and stays behind the project's A–E props-off work order (`autonomy-onboard-plan.md`). The dump app
below is a **diagnostic that never touches motors** (see Safety).

## Two approaches — patch the stock image (B) before a clean-room replacement (A)

**Approach B (preferred for the bootloader dump): surgically patch the stock m0306.** Keep the
entire working DJI firmware; **append** a small payload in the free flash at the end of the app
region and **redirect one hook** to it. Far less work and far lower risk than a rewrite — every DJI
driver, control loop and failsafe stays intact; the payload is dormant until explicitly triggered.
Verified specifics:

- **Free space:** the image is 0x0DD200 B and occupies `0x08020000–0x080FD200`; the app region
  (sectors 5–11) runs to `0x08100000`, leaving **`0x080FD200–0x08100000` = 11.5 KB free** — ample
  for a dump payload (a few hundred bytes of Thumb).
- **Hook — a parameter callback:** each FlycExportParam entry has a `callback` function pointer at
  **+0x38**; **30 params already carry a real code callback** (e.g. `config_parameter.assistant_timeout`
  → `0x0804672f`), proving it is a live on-write hook. Repoint **one** param's callback to the
  payload — pick a param that currently has a **null** callback (807 of them) so no stock behaviour
  is lost — and a DUML `SetParamsByIndex` (0x03 0xf2) on that index invokes the payload. (Equivalently,
  repurpose an unneeded DUML command handler's dispatch entry — your "command not needed".)
- **Payload:** read `0x08000000–0x0801FFFF` and stream it out in chunks via the **stock** DUML TX —
  because the image is kept whole, the payload calls existing functions at their real addresses
  (`duml_send 0x0804f862`, `duml_crc16 0x0804f024`). Recovers the resident loader.
- **Repackage:** append payload at `0x080FD200`, patch the one callback word, recompute the transfer
  CRC + container MD5 (the `0x77557755` marker and vectors are untouched), re-encrypt AES, repack
  xV4 (`dji_xv4_fwcon.py` / `scripts/re/xv4_pack.py`), flash via the normal DUML upgrade.
- **To confirm first:** that `SetParamsByIndex` actually invokes `entry->callback` on write (the 30
  live callbacks strongly imply it — verify by decompiling that handler / in the FC Sim).

**Approach A (the clean-room replacement below)** remains the path for the eventual *autonomy*
firmware, where we want our own control code — not for the dump. Do B first; it de-risks packaging
and the loader dump without reimplementing anything.

## Why a replacement (or patch) is accepted (established by RE — see `fc-bootloader.md`, `fc-io-inventory.md`)

- **No signature.** The FC image is protected only by xV4 AES-128 (public key) + container MD5 +
  transfer CRC + `FIRM_MATCH` (version/hardware) + the `0x77557755` valid-image marker. A correctly
  packaged custom image therefore passes.
- **The loader is preserved.** The update erase path never touches sectors 0–4 (`0x08000000`), so a
  bad replacement app is always recoverable by reflashing stock m0306 via DJI Assistant 2. **Low
  brick risk** — the recovery anchor is exactly the loader we're trying to read.
- **The running app has full memory access**, so our app can read `0x08000000` and stream it out via
  a command we add — stock DUML has no read-memory, but ours will.

## Acceptance checklist for a flashable m0306 image

1. Vectors at `0x08020000` (SP in `0x2000xxxx`, reset in `0x0802xxxx`), valid.
2. The **`0x77557755` marker** at the loader-checked header offset (offset **TBC** — confirm the
   header struct; `FUN_20007a30` reads `*(*(desc+0x2c) - 0xf)`).
3. Image fits bank-1 app sectors 5–11 (`0x08020000–0x080FFFFF`).
4. Packaged as xV4 target `m0306`: correct `decrypted_len`, `decrypted_md5`, AES-128 (reverse of
   `scripts/re/xv4_decrypt.py`; `dji_xv4_fwcon.py` can repack), encrypt_type 1.
5. `FIRM_MATCH` header fields (version/hardware id) acceptable — **TBC** (read from the stock m0306
   container header; mirror them).
6. Delivered via the DUML upgrade sequence (`RequestUpgrade 0x07 → TranslateData 0x09 →
   TranslateComplete 0x0A → RestartDevice 0x0B`), CRC per block.

Items 2 and 5 are the two unknowns to close before the first flash attempt; both are readable from
the stock image/loader, not guessed.

## Components

| Layer | Choice | Source |
|---|---|---|
| MCU | STM32F427 (Cortex-M4F), flash `0x08020000`, SRAM `0x20000000`, CCM `0x10000000` | verified |
| HAL | STM32Cube **HAL** (clean-room; DJI used SPL, we don't need to match) | ST |
| RTOS | **FreeRTOS** (replaces DJI's µC/OS-III) | — |
| Framework/logging | operator's `prntc` / awto-l8 glue | **operator-supplied** (component slot; not in this repo) |
| DUML stack | port of the verified codec: `0x55` SOF, CRC8 seed `0x77`, CRC16 seed `0x3692`, device-type routing | `app/packages/duml` (Dart) + `rust/awto_dji_core` to port from |
| Transport | CAN1 on **PD0 (RX)/PD1 (TX) AF9**, FC device-type frames (IDs `0x41x`) | `fc-io-inventory.md`, `m0900-can-channels.md` |
| Commands | GetVersion; **read_memory (dump)**; later: param/control surface | this plan |

## FC Sim (host, no hardware — build this first)

A host executable linking the **same DUML stack + command handlers** against a stub vehicle model,
using the repo's existing simulated/replay transport (`app/packages/duml` has sim + tests). Lets us
develop and unit-test the protocol, the read_memory command framing, and the upgrade-client packer
with **zero hardware risk**, before anything is flashed. Deliverables: DUML round-trip tests, a
mock "read_memory" that serves a fake flash image, and the xV4 packer verified against
`xv4_decrypt.py` (pack→decrypt round-trips to the same bytes).

## Build order

1. **FC Sim** (host): DUML stack in C, command dispatch, read_memory handler against a fake image,
   xV4 packer round-trip test. No hardware.
2. **Minimal on-target app** (F427): boot, clocks, CAN1 up, FreeRTOS, DUML GetVersion only. Package
   (acceptance checklist), flash via the loader, confirm it boots and answers GetVersion over CAN.
3. **Add read_memory**: dump `0x08000000–0x0801FFFF` in chunks over DUML → recover the resident
   loader. Analyse it (closes the last boot-chain gap; check for any secure-boot the app lacks).
4. **(Gated, later)** param/control surface for autonomy — only after A–E bench bring-up, props off.

## Safety (non-negotiable for this phase)

- The **dump/diagnostic app does not initialise or drive motors/ESCs** and runs **no control loop** —
  it is comms + memory-read only. There is nothing for it to fly.
- **No propellers, no flight** in this phase; a flight-capable replacement is the separate A–E track.
- Always keep the stock m0306 image to reflash via DJI Assistant 2 (the loader, preserved in
  sectors 0–4, makes this a reliable recovery).

## Proposed layout

- `fc/` — new C firmware (STM32 HAL + FreeRTOS + operator framework), with `fc/duml/` ported from
  `app/packages/duml`, `fc/sim/` host build, `fc/app/` target app.
- `scripts/re/xv4_pack.py` — the packer (encrypt + marker + container), mirror of `xv4_decrypt.py`.
