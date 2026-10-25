# Camera Linux (m0100, Ambarella A9SE): console and shell access

Evidence from `firmware/unpacked/P3X_FW_V01.11.0020_m0100.bin`, both the extracted `sys`
RTOS partition (`tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_sys.a9s`) and the
`rfs` Linux rootfs (UBIFS, partially extracted to `tmp/air/rfs_P3X0020/` via
`scripts/re/fpga_write_path.py` -> `scripts/re/air_survey.py`'s UBIFS walker). Tags:
V = verified in extracted bytes, I = inferred, U = unknown/untested.
Interop analysis only: no keys read, nothing sent to hardware for this doc.

**2026-10-24 bench update:** the camera SD card was identified through its USB
mass-storage interface and an empty diagnostic marker was written at the operator's
request. This later action is separate from the read-only firmware analysis below.
See the diagnostic logging section for the exact file, device identity and limits.

## SD-card diagnostic logging marker (2026-10-24)

- **V, now independently traced in firmware:** an existence check for **`0x40003000.dji`** in the camera card root enables the SD logging worker.
  - The traced output path is **`C:\MISC\LOG\CameraLogCur.log`**, with rotation to **`C:\MISC\LOG\CameraLogOld.log`**.
  - This corrects the earlier operator-supplied path `MISC/CameraLogCur.log`: the firmware includes an additional `LOG` directory.
  - Static behavior is verified. The later SD-card review found actual diagnostic output at this path; see the validation update below.
- **V, device identification:** USB `070a:4026`, manufacturer `AmbarellaInc`, product `A9 Platform`, exposes USB mass storage.
  - Its block device reports `Ambarell A9 DSC EVK Platf`, approximately 32 GB, with a FAT partition containing `DCIM/100MEDIA/DJI_*.DNG`, `DJI_*.MP4` and `MISC/LOG/P3X_FW_LOG_AB.txt`.
  - This confirms the camera media card rather than merely assuming it from the VID.
- **Stable partition identity used for the write:** `/dev/disk/by-id/usb-Ambarell_A9_DSC_EVK_Platf_0001-0:0-part1`.
  - It resolved to `/dev/sdc1`, mounted at `/run/media/dan/8765-4321`, at the time of the operation.
  - Re-resolve by-id and the mount before future writes; `/dev/sdc1` and the mount path are observations, not permanent identifiers.
- **V, action completed:** created `0x40003000.dji` in that partition's root with
  exclusive creation (no existing file overwritten), verified size **0 bytes**, and
  flushed it with `sync -f`. No firmware image or executable script was added.
- **V, later validation:** `MISC/LOG/CameraLogCur.log` now exists (reported size 42,466 bytes), with Ambarella boot output and camera version 01.32.5432.
  - The first 32,768 bytes were copied before an EIO read error.
  - This verifies the output path is active with the marker present; timing and exclusive causation by the marker remain unproven.
  - See [firmware-upgrade-log-review.md](firmware-upgrade-log-review.md) for provenance, the preserved prefix and the separate historical upgrade-log analysis.
- **Boundary:** logging is output capture. This marker does **not establish USB
  command input, a USB serial console, or access to the Linux shell**. The Ambarella
  USB interface observed during this session was mass storage, not CDC serial.

## Firmware trace of the logging gate and related filenames

All addresses in this section refer to `P3X_FW_V01.11.0020_m0100_part_sys.a9s`,
loaded at **`0x0e600000`**, ARM A32. This is the camera's **RTOS `sys` partition**,
not its Linux kernel or root filesystem. The image's ThreadX source-path strings
are consistent with that separation. String references are reproducible from the image with
`scripts/re/elfdis.py` / `strings` at the addresses cited below.

### Exact gate

1. **V:** `DjiLog2SdDetectProc` at `0x0e80d184` builds a drive-root pathname using
   `%c:\%s` and the marker string at `0x0e672d24` (file offset `0x72d24`). It obtains
   the drive letter through helper `0x0e899aa4`.
2. **V:** instruction `0x0e80d1ec` calls `0x0e71f17c`, independently identified by
   its own `AmbaFS_Stat` diagnostic string. A return of 0 takes the enable path.
   This path checks existence/stat success, **not file contents**; no nonempty
   payload or numeric address parsed from the filename is required by this check.
3. **V:** `0x0e80d1f8` passes 1 to `0x0e80d468`, which stores the SD logging
   enable byte at `0x109d0b80`; `0x0e80d200` calls worker creation at `0x0e80d368`.
   That routine registers task entry `0x0e80cf0c` under the name `DjiLog2Sd` and
   sets an already-created flag at `0x109d0ce0`. The detector exits early when
   that flag is already 1.
4. **V:** the worker constructs `C:\MISC\LOG\CameraLogCur.log` at
   `0x0e80cf40`–`0x0e80cf64`. `MISC` and the filename are pool-referenced strings;
   `LOG` is inline at `0x0e80d178`. The same path construction is used for the
   old-log name near `0x0e80d014`; subsequent code handles rotation and file writes.
5. **V:** shell output wrapper `0x0e7cb238` calls buffering function `0x0e80d3d4`
   at `0x0e7cb250`. The startup sequence at `0x0e8130a0`–`0x0e8130ac` registers
   that wrapper with the shell setup routine. This connects the SD worker to the
   shell's output path; it does not establish an input channel over USB.

**Invocation:** callback `0x0e81e060` calls the detector at `0x0e81e064`.
Initialization installs that callback in a work record at `0x0e81e148`–`0x0e81e14c`,
alongside a `0x7d0` (2000) field and enabled-looking fields. **I:** a periodic
scheduled check; the scheduler and timing units were not fully traced, so a precise
poll interval or hot-insertion guarantee is not established. The writer separately
waits on storage-related status and synchronization. An enabled marker alone does
not guarantee a file appears while USB mass-storage mode owns the card.

**Another enable path:** when the marker stat fails, the detector reads camera-aging
state via `0x0e804e1c`. State >=2 takes the same enable/create calls, with a diagnostic
string saying camera aging enables SD log recording; state 1 clears the enable flag.
Thus the marker is one gate into this logger, not its only possible activation path.

### Other filenames: triggers versus data/output files

These findings describe code present in this build. None of the additional files
below was created or executed on the camera during this search.

| Name / path | Verified references and behavior | Limits |
|---|---|---|
| `C:\autoexec.ash`, `D:\autoexec.ash` | Startup `0x0e8130bc` loads a two-entry path table at `0x0ed8c074`; `0x0e8130c4` calls `0x0e8c7aac`. That routine stats the files and enters script execution, printing `execute script: %s ...`. | RTOS shell scripts, not empty logging markers or Linux shell scripts. A runtime guard also exists; not tested on hardware. |
| `P3X_FW_DEBUG` | Root-path stat at `0x0e8a6c20`; success sets flag `0x10bcd688`. | In firmware-update code. Full effects of the flag remain U; not established as logging-only. |
| `P3X_FW_DEBUG_2` | Root-path stat at `0x0e8a6c64`; success sets both `0x10bcd688` and `0x10bcd68c`. | Separate update/debug variant; full effects U. |
| `P3X_FW_LOOP` | Root-path stat at `0x0e8a6cb4`; success sets flag `0x10bcd684`. | Update-loop-related control (I); full downstream behavior U. |
| `C:\DjiAgingFun_300X` | Parser `0x0e80660c` opens and reads configuration records; filename loaded at `0x0e806624`. | Factory aging configuration with contents, not an empty-file toggle. |
| `C:\Dji97986986_300X`, `C:\Dji97986986R_300X` | `0x0e8077bc` opens a candidate, reads 16 bytes and compares with reference data before choosing aging configuration. | Structured factory-test enable/check files. Mere existence is insufficient; no reference bytes reproduced here. |
| `C:\DjiBoard` | `DjiAgingCheckBoardFile` path reads 10 bytes and compares with locally constructed board data at `0x0e8069c8` onward. | Board-validation data, not a demonstrated empty-file trigger. |
| `C:\DjiCheckVideo`, `C:\DjiAgingResult*.txt` | The routine at `0x0e807378` constructs/open result filenames from these strings. | Factory-test outputs; a matching filename string alone does not establish a trigger. |
| `C:\amba_mtp.txt` | MTP database paths near `0x0ea4717c` open and seek within this file; neighboring diagnostics name `AppMtpd_DbInsertHandle`. | MTP database/storage data, **not evidence of an MTP-mode enable marker**. |

### Linux side: expanded search

**Not reproducible as stated.** This section previously claimed the UBIFS walker
reconstructed 335 regular files and 415 symlinks and found no occurrence of the marker
names in them. `tmp/air/rfs_P3X0020/` on disk holds **22 regular files and 0
symlinks** (matches section 2's "only 22 files pulled" below) - no saved walker output
for a 335/415-file run exists, so that negative result can't be re-run or checked.
Treat the 335/415 claim as unverified until someone reruns the walker and saves its
output; until then, assume only the 22 known files have been searched.

There are other file-driven Linux behaviors:

- **V:** `/usr/local/share/script/tcp_script.sh` checks for
  `/tmp/fuse_d/MISC/tcp_tuner.sh` and invokes it with `/bin/sh` when present.
  **U:** what launches `tcp_script.sh`; no other reference to its basename was
  found in the reconstructed files, so this does not prove automatic boot execution.
- **V:** `wifi_start.sh` and `bt_start.sh` test SD-side configuration paths such
  as `/tmp/fuse_d/MISC/wifi.conf` and `MISC/bt.conf`. These are configuration files
  with contents, not empty diagnostic markers; exact product/runtime applicability U.
- **V:** `S50service` mounts RTOS `c:` at `/tmp/fuse_d`, providing the path bridge
  between card-root `MISC/...` and Linux `/tmp/fuse_d/MISC/...`.
  Its `/tmp/fuse_a/.exist` file is created by the startup script itself to check the
  internal `a:` mount; it is not an SD-card diagnostic trigger supplied by the user.

The logging marker is therefore independently confirmed in the **RTOS file gate**;
the Linux scripts expose additional hooks with different invocation requirements.

### Reproduce

```sh
python3 -I scripts/re/camera_marker_audit.py
python3 -I scripts/re/fpga_write_path.py dis 0x0e80d184 92
python3 -I scripts/re/fpga_write_path.py dis 0x0e80cf0c 26
python3 -I scripts/re/fpga_write_path.py dis 0x0e80d368 26
python3 -I scripts/re/fpga_write_path.py dis 0x0e8130a0 10
python3 -I scripts/re/fpga_write_path.py dis 0x0e8c7aac 65
python3 -I scripts/re/fpga_write_path.py dis 0x0e8a6bf8 54
```

**Update (2026-10-24, later same day):** `MISC/LOG/CameraLogCur.log` now exists on the
card, 42,466 bytes - see `docs/firmware-upgrade-log-review.md:92-101` and
`captures/sessions/2026-10-24/sdcard-review/CameraLogCur-readable-prefix.log` (32,768
bytes readable, then `EIO`). The marker's logging effect is no longer just claimed,
there's a file to point to - but causation (that the empty `0x40003000.dji` marker is
what produced it, versus some other trigger) is still not independently proven; see
`docs/firmware-upgrade-log-review.md:90-96`.

## 1. A root shell is already live by default - no unlock needed

- **V** `tmp/air/rfs_P3X0020/etc/inittab`: `ttyS2::respawn:-/bin/sh` - BusyBox init
  respawns an unauthenticated root shell on `ttyS2` forever, by default.
- **V** Kernel command line (sys partition string): `console=ttyS2` - matches; `ttyS2`
  is the Linux console, not a secondary/debug-only UART.
- **V** Commented-out (disabled) in the same inittab: a getty on `ttyUSB0` and a shell
  on `ttyGS0` (USB gadget serial). Not active in this image as shipped.
- **I** This looks like a stock/dev-style BusyBox rootfs shipped as-is, not something
  DJI stripped for retail - consistent with the single-CPU/companion-board DJI
  architecture description in `o-gs/dji-firmware-tools` issue #3 (quoted in
  `alternative-approaches.md`/session history): nobody there had confirmed this.

## 2. Two more default-on access paths, same rootfs

- **V** `etc/init.d/S50service` runs bare `telnetd` unconditionally at boot (no `-l`
  flag seen). Whether it falls back to `/bin/login` (needs `/etc/passwd`, not yet
  extracted) or spawns a shell directly: **U**.
- **V** `etc/init.d/S50sshd` starts `sshd` every boot, generating RSA1/RSA/DSA/ECDSA
  host keys on first run if missing. Auth config (`sshd_config`, not yet extracted): **U**.
- **V** `etc/init.d/S40network` runs `ifup -a` - some network interface is configured.
  Which one (likely the FX2LP/rpmsg USB-net path the phone uses for video, per
  `air-id-and-stream-survey.md`'s "phone-over-Wi-Fi/USB-net path") and whether it's
  reachable without the phone already linked: **U**.
- **Practical gap**: physical UART pads for `ttyS2` have not been located on this
  board (no schematic, no device tree extracted - see "Open" below). telnet/ssh need
  network reachability, which likely depends on the same AOA/rpmsg link already in use.

## 3. A factory/repair UART<->USB-CDC-ACM bridge exists in firmware

This looks closest to what you were thinking of - a DJI-added engineering command, not
a bare UART header:

- **V** Driver present: `AppCdcAcmd_Start`/`_Stop`/`_Task`/`_RcvTask`
  (sys offset `0x489b0`-`0x48db4`), log strings `"%s(): switch to CDC_ACM mode."` /
  `"%s(): switch back to UART mode."` (`0x48bcc`, `0x48c18`). A second "Multid" variant
  exists for multiple simultaneous CDC-ACM log channels.
- **I** This bridges one of the SoC's own UARTs to a USB CDC-ACM (virtual COM port) endpoint at runtime, i.e. the UART console over USB instead of bare pads.
  - Nearby strings `"Ambarella UART0"` / `"Ambarella UART1"` (`0x48f6e9`, `0x48f6fc`) sit close to this cluster.
  - Which UART (0, 1, or `ttyS2` itself) gets bridged is **U**.
- **V** A DJI engineering shell command exists to drive a related toggle: `t dji console [addr/0]`, help string `"Console [on/off] control. t dji console [0x40003000/0]. eg: t dji console 0x40003000"` (sys offset `0x76d50`).
  - `0x40003000` looks like an STM32-range peripheral address, not a typical Ambarella SoC MMIO address. This may toggle a *different* chip's UART (the "uart M4" string at `0x554e8` suggests a Cortex-M4 companion is also in the picture).
  - Whether `t dji console` is the same mechanism as `AppCdcAcm`, or a separate one: **U**.
- **V** The same `t dji` help table (sys offsets `0x76924`-`0x76fd4`, one continuous block, reproduce with `strings -n4 -tx <sys partition> | grep 't dji'`) also has:
  - `t dji updater [0/1]` (firmware update test, camera/368), `t dji reboot [0/1]`.
  - `t dji wdg [0/1/2]` (disable/stop/start the watchdog; useful to hold a debug session without auto-reset), `t dji reason` (print reset reason).
  - `t dji pano [0..4]`, whose options 3/4 are `connect usb to A9` / `connect usb to DM368`: the switch between the camera's single external USB port talking to the A9 (control) or the DM368 (video), already noted in `air-id-and-stream-survey.md`.

## How you'd reach the `t dji` shell at all

These are typed commands at an existing prompt - they don't themselves grant initial
access. Candidate paths, none tested yet:

1. Already-live `ttyS2` root shell (section 1) - if its physical pads can be found.
2. telnetd (section 2) - if/once the network path is reachable.
3. Whether any of this is reachable through a DUML passthrough from the app side (the
   project has found hidden debug/test command paths before - `cmdset_fuzz.py`,
   `docs/apk-vs-dissector-gap-report-2026-10-23.md`'s debug-mode findings for
   Assistant 2) - **not checked for the camera module specifically**.

## Public corroboration (2026-10-24)

- **W** (same wiki page's component list): two **TI TS3USB221A-Q1** USB multiplexers on
  the camera board - the part behind the A9<->DM368 port switch `scripts/re/usb_switch_trace.py`
  (issue #25) traces by function name (`MCCTRL_SetUsbMode` etc.) but hadn't named yet;
  exact URL not re-confirmed this pass, follow up before citing further.
- **W** (`o-gs/dji-firmware-tools` wiki, "CV310 Gimbal top board" page, <https://github.com/o-gs/dji-firmware-tools/wiki/CV310-Gimbal-top-board>): confirms this board carries m0100/m0101 ("Takes care of driving CMOS sensor and does high resolution video encoding... Looks very similar to FC200 video pipeline").
  - Its "Service interfaces" section (test pad locations) is unfilled (`TODO`) on the project wiki itself; not documented there as of this check.
- **W** (PhantomPilots forum, "Camera lost communication" thread, <https://phantompilots.com/threads/camera-lost-communication.141294/page-2>): a community member found the UART pads on this exact board (P3S/P3 gimbal top board).
  - Setup: bare USB-to-TTL adapter (no level shifting beyond 3.3V, avoid "smart"/auto adapters). Got real Ambarella A9 boot logs at **115200 8N1** once the baud rate was set correctly (the thread shows the wrong-baud garbage first, then the fix).
  - No unlock command needed: just RX/TX/GND wired correctly and powered on after the terminal is already listening.
  - The log confirms the same architecture this repo found independently: `AmbaSD_InitCard`, SD-card firmware package detection/CRC check, NAND programming per-partition, `Cortex Boot-Up Success` banner, `UART freq: 1846153`.
  - The thread explicitly says **"you need to connect to a different UART - not m0800, but m0100"**. So more than one UART is broken out on connectors/pads on this board, and only one of them is the Linux console.
- The public-source search below did not establish a USB command-input unlock -
  every confirmed command-input case it found uses a physical
  UART tap. Consistent with this doc's own firmware trace: the always-on `ttyS2` shell
  needs physical pads in those examples, and `AppCdcAcm`/`t dji console` are things
  you'd type *after* you already have a prompt, not a way to get one from nothing.

## Open / next steps

- No DJI schematic or device tree for the camera (Ambarella) board exists on this
  machine - `ttyS2`'s physical pin location is unknown. The 2016 community thread
  (`o-gs/dji-firmware-tools` issue #3) speculated about enabling USB-side UART but
  never confirmed it; this firmware trace is more specific but still not pin-level.
- `/etc/passwd`, `/etc/network/interfaces`, `sshd_config` not yet extracted from the
  rootfs (only 22 files pulled so far, by a script scoped to a different task) - a full
  UBIFS extraction would answer telnet/ssh auth and the network interface question.
- `AppCdcAcm` trigger condition (strap pin? a `t dji` command? automatic on a specific
  USB enumeration?) is not established from strings alone - would need to disassemble
  its call sites, or test on real hardware via the camera's own micro-USB port.
  `scripts/re/usb_switch_trace.py` (issue #25) traces the related A9<->DM368 port
  switch (`MCCTRL_SetUsbMode`, `DjiMsgStUsbSwitchStatusSet`,
  `DjiUegDm368StreamControl`) but not `AppCdcAcm` itself - no GPIO/mux identified yet,
  all three show zero direct `bl` callers in the scanned range (dispatched via a
  table, not disassembled), so this is a start, not a resolution.
