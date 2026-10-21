# Phantom 3 firmware — how it's structured

This is the aircraft/RC software, a separate world from the phone app. Described from
the P3-focused open-source tooling (`o-gs/dji-firmware-tools`) and its P3X firmware
symbols — i.e. how the firmware is *organised and works*, not how to modify it.
Modifying firmware is signed/encrypted, out of scope, and not needed for the app.

## One package, many modules

A P3 firmware `.bin` is a container holding a separate firmware image for each
processor on the aircraft and the remote. They all talk to each other over the
internal **DUML bus** — the same protocol the phone speaks to the aircraft. Module map
for the Phantom 3 (from `dji_xv4_fwcon.py`):

| Module | Chip / role |
|---|---|
| `m0100` (FC300X / CAMLDR) | Camera SoC — **Ambarella A9SE**, runs Linux (ROMFS + UBIFS). Main camera/imaging processor. |
| `m0306` | **Flight Controller** — the flight MCU. Receives and executes flight commands, holds flight parameters and flight state. The one that matters for control. |
| `m0400` (GIMBAL0) | Gimbal controller. |
| `m0800` (DM368) | Video **encoder** on the aircraft — DaVinci DM368 Linux. |
| `m0900` (MCA1765) | **Lightbridge** MCU in the air — STM32F103. |
| `m1300` (DM365) | Video **decoder** on the ground (in the RC). |
| `m1400` (MCG1765A) | Lightbridge MCU on the ground (RC) — LPC1765. |
| `m1900` / `m2000` (FPGAA / FPGAG) | Lightbridge FPGAs, air and ground. |

So "updating the drone" actually flashes ~8 different processors, each over DUML.

## Package format and signing

- **Phantom 3 uses the `xV4` container** (`dji_xv4_fwcon.py -x` extracts the modules).
  Example from the reference: `./dji_xv4_fwcon.py -x -p P3X_FW_V01.08.0080.bin`.
- **Newer DJI products use the `IMaH` signed/encrypted format** (`dji_imah_fwsig.py`).
  Images are signed with `PRAK` keys and encrypted with `PUEK` keys; the private parts
  are rarely available, so modules generally cannot be re-signed. (P3 predates the
  strictest of this.)
- The camera module (`m0100`) is a full Linux system (kernel + device tree + UBIFS
  rootfs). The flight controller (`m0306`) is bare-metal ARM loaded at `0x8020000`;
  the tooling turns it into an ELF for analysis (`arm_bin2elf.py`).

## How the flight controller works (m0306)

The FC is the DUML endpoint that executes the flight-controller command set
(`cmd_set = 0x03`). Its firmware symbols show the state machine and command handlers,
e.g. `kctrl_init_auto_landing` / `act_ctrl_auto_landing`, matching the flight states in
the protocol dissector (`Manual`, `GPS_Atti`, `AutoTakeoff`, `AutoLanding`, `GoHome`,
`Joystick`, …). It also exposes **hundreds of parameters** over DUML, which the service
tools get/set (`comm_og_service_tool.py`, `dji_flyc_param_ed.py`) — this is how tuning
and configuration work.

The implication for the app: the "flight control over DUML" we flagged as *unproven*
is ultimately received and acted on by `m0306`. Confirming the exact command payloads
is best done by **capturing live DUML** between a working RC/app and the aircraft, not
by modifying firmware.

## GPL source availability (verified)

The camera module runs Linux, so DJI must *offer* that source under GPL v2. They list
it on [dji.com/opensource](https://www.dji.com/opensource) under the Ambarella platform
(which names the Phantom 3). Checked with `scripts/check_gpl_sources.sh` on 2026-10-21:

| Package | Version | License | Link status |
|---|---|---|---|
| busybox | 1.23.2 | GPL v2 | **OK** — 2,252,786 bytes, extracts cleanly (sha256 `05a6f9e2…`) |
| Linux kernel | 3.10 (Ambarella BSP) | GPL v2 | **EMPTY** — `linux-ambarella.tar.gz` returns HTTP 200 but **0 bytes** |

So the kernel source is listed but not actually downloadable from DJI right now — a
GPL-compliance gap, re-confirmed across retries.

**But GPL source is freely redistributable, so DJI's broken link doesn't make it
unavailable.** A community mirror carries it:
[`sin5678/DJI_Ambarella_Linux`](https://github.com/sin5678/DJI_Ambarella_Linux).
Verified it is the genuine Ambarella BSP, not a vanilla tree:

- Kernel **3.10.71** (Makefile `VERSION=3 PATCHLEVEL=10 SUBLEVEL=71`) — the same 3.10
  line DJI lists and a P3 boot log shows (3.10.62); minor point-release difference.
- `arch/arm/mach-ambarella/` is present — the Ambarella SoC machine support that
  mainline 3.10 does **not** have, which is what makes it the real BSP.
- Uploaded as a single bulk commit (how GPL source drops usually appear).

Caveats: it's a community mirror (one commit, no signature), and DJI's own copy is empty
so there's nothing to diff it against — so treat it as "the right kernel line and the
real Ambarella BSP", not as byte-verified against DJI's exact build. The Wayback Machine
is another avenue if a DJI-hosted snapshot with content is wanted.

Either way it is a generic Ambarella 3.10 BSP (camera SoC Linux), without DJI's
proprietary drivers/apps, so it is of limited use for this project — the flight-control
and DUML code is not Linux and is not covered by GPL.

## How firmware is updated

The whole aircraft+RC is updated from the single package `.bin` (~66 MB for the P3).

**Delivery — three ways, same package:**
1. **DJI GO app** downloads the package and pushes it to the aircraft; progress is
   reported back via `DataCommonGetPushUpgradeStatusInfo`.
2. **microSD card** — copy the `.bin` to the camera's card and power-cycle; the camera
   picks it up on boot.
3. **DJI Assistant 2** over USB to the camera.

**Internal mechanism — the camera orchestrates, DUML distributes:**
The Ambarella camera module (`m0100`, the Linux host) is the upgrade manager. It reads
and verifies the package, then flashes each of the other processors over the internal
**DUML bus** using the General command set (`cmd_set = 0x00`), observed in the reference
dissector:

| cmd_id | Step |
|---|---|
| `0x0f` Upgrade Self Request | compatibility / consistency check per module |
| `0x07` Enter Loader | put the target module into its bootloader |
| `0x08` Update Confirm | prepare / start the upgrade procedure |
| `0x09` Update Transmit | stream the firmware data blocks |
| `0x0a` Update Finish | verify (CRC / signature) |
| `0x0b` Reboot Chip | restart into the new image |
| `0x0c` Get Device State | check whether a module is in loader or app mode |

Modules are flashed **sequentially** (camera, FC, gimbal, Lightbridge MCUs/FPGAs, …),
each announced by the aircraft's audio tones; a failure mid-sequence can leave a module
on its bootloader (the "won't boot / needs reflash" state owners sometimes hit).

**Verification & downgrade:** each module image carries a CRC (P3 `xV4`); newer DJI
products add the `IMaH` signature layer. The P3 permits **downgrade** to earlier
versions (DJI's own notes allowed going back to v1.4.10+), which is how the research
community moved between builds.

## Verified by unpacking the real firmware

Downloaded the actual last P3 Pro firmware (`P3X_FW_V01.11.0020`, 66 MB, built
2017-07-05) and extracted it with `dji_xv4_fwcon.py`. It is a plain `xV4` container
(no keys needed) and unpacked to 17 modules, matching the module map above:
`m0306`/`m0305` (A3 flight controller app/loader), `m0400` (gimbal), `m1100`/`m1101`,
`m1200`–`m1203` (the four ESCs), `m1500`, `m1700`/`m1701`, `m1900` (air FPGA),
`m0100`/`m0101` (camera app/loader — the 56 MB Linux module), `m0800` (DM368 video
encoder), `m0900` (Lightbridge air MCU). Manifest: `model=P3X`, `pkg_format=201507`.
The camera module's strings are the source of the video-format details in
`video-and-link.md`.

## Is the firmware signed? (P3: no)

Checked in `dji_xv4_fwcon.py`: the P3 `xV4` package is validated only by **CRC-16 +
per-module MD5 checksums** — there is **no cryptographic signature** (no RSA/ECDSA).
Checksums detect corruption but are recomputable, so they do not prevent modification;
this is why P3 firmware can be downgraded/modified/reflashed by the community.

- Cryptographic signing arrived with the newer **`IMaH`** format (Phantom 4 / Mavic on)
  — RSA PKCS#1/PSS with DJI `PRAK`/`PUEK` keys (`dji_imah_fwsig.py`). P3 predates it.
- Some P3 modules carry DJI module-level AES (`encrypt_type=1`, e.g. the A3 FC `m0306`),
  **but the keys are known/extracted** — the tool decrypts them automatically (that's how
  we disassembled `m0306`). So that layer is effectively open too.
- The FPGA module `m1900` is `encrypt_type=0` (no DJI wrapper); its high entropy is the
  Altera tool's own bitstream compression/encryption, separate from DJI's container.

### FPGA bitstream: compressed, not encrypted (tested)

High entropy alone does not prove encryption — a *compressed* bitstream also looks
random, while a *plain* one is low entropy (zero-heavy). Tests on the `m1900` used
region (2.06 MB) settle it:

- gzip → **98.6%** (incompressible): compressed or encrypted — inconclusive alone.
- chi-square vs uniform = **113,468** (encryption would give <~310): byte distribution
  is strongly **non-uniform** → **not AES-encrypted**; non-uniformity is the mark of
  compression.
- header is **structured, not random**: first 2 KB entropy **1.22** (mid 7.91), a
  repeating `xxxx ffff …` pattern. Encrypted data is random from byte 0, so a structured
  cleartext header rules out whole-file encryption.
- only **1.85%** zero bytes → not a plain/uncompressed bitstream either.

Conclusion: it is an **Altera-compressed** bitstream, **not encrypted**. The protection
is obscurity + device-specificity, not a device-bound key. So it is **not**
cryptographically locked to one chip — the same Cyclone-V part could in principle be
configured with it (it still needs the board: AD9363, clocks, PAs, the configuring MCU).
Reversing the *logic* remains hard (undocumented compressed config format). The
modem/scrambler exists only as gates in this bitstream; the `m0900` MCU merely brings the
FPGA up (config/reset lines, AD9363 over SPI), so reading the MCU does not reveal the
radio logic.

### Bitstream reverse-engineering tooling

The FPGA-bitstream-documentation projects are the right tools here:

- **Xilinx 7-series:** Project X-Ray (F4PGA/SymbiFlow).
- **Lattice:** Project IceStorm (iCE40), Project Trellis (ECP5).
- **Intel/Altera Cyclone V — the P3's part:** **Project Mistral**
  (`Ravenslofty/mistral`), a library/CLI that **compiles and decompiles Cyclone-V
  bitstreams** (loads `.rbf` → configuration RAM, and back). Correction to an earlier
  note: Altera's on-chip config compression is a **nibble-RLE scheme** (see Mistral's
  `rbf_load`), **not LZMA** — Mistral's `liblzma` dependency is only for its own device
  database `.xz` files, not the bitstream.

**Is `m1900` a usable bitstream? Yes — a compressed (not encrypted) config image.**
Re-tested on the payload bulk (header excluded): chi-square 27,810 for 2 MB (uniform
would be ~255; encryption gives ~uniform) → **not encrypted**; gzip 99.3% + non-uniform
→ **compressed**, with a structured framing header. So the "random look" is compression,
confirmed.

**But Mistral can't load it directly, for two reasons:** (1) the **air FPGA part is
unknown** — the firmware labels it only "model 0"; Mistral ships data for `5CEBA4`/
`5CSEBA6`, the P3 *ground* FPGA is `5CEFA4`, the air one is unidentified; and (2)
`rbf_load` expects a **plain (uncompressed / nibble-RLE) `.rbf`**, whereas `m1900` is a
further-packed image (structured header + high-entropy bulk) that must be de-packed to a
plain `.rbf` first.

Realistic feasibility: decompressing/cloning onto the *identical* part is plausible once
de-packed; recovering readable RTL for the OFDM modem is not — bitstream-RE tools yield a
LUT/FF-level **structural** netlist on a documented fabric, not behavioral Verilog.

## Boundaries

The reference also ships tools to edit firmware (including a no-fly-zone editor and
FC "hardcoder" patchers) and historically a firmware *downgrade* enabled root access.
Those modify the aircraft's behaviour and its safety limits — out of scope here, and
unnecessary: the app project only needs to *speak* DUML to a stock aircraft and enforce
airspace limits itself (the `geofence` gate), not to alter firmware.
