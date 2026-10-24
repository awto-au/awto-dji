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

- **V, now independently traced in firmware:** an existence check for
  **`0x40003000.dji`** in the camera card root enables the SD logging worker.
  The traced output path is **`C:\MISC\LOG\CameraLogCur.log`**, with rotation to
  **`C:\MISC\LOG\CameraLogOld.log`**. This corrects the earlier operator-supplied
  path `MISC/CameraLogCur.log`: the firmware includes an additional `LOG` directory.
  Static behavior is verified. The later SD-card review found actual diagnostic
  output at this path; see the validation update below.
- **V, device identification:** USB `070a:4026`, manufacturer `AmbarellaInc`, product
  `A9 Platform`, exposes USB mass storage. Its block device reports
  `Ambarell A9 DSC EVK Platf`, approximately 32 GB, with a FAT partition containing
  `DCIM/100MEDIA/DJI_*.DNG`, `DJI_*.MP4` and `MISC/LOG/P3X_FW_LOG_AB.txt`.
  This confirms the camera media card rather than merely assuming it from the VID.
- **Stable partition identity used for the write:**
  `/dev/disk/by-id/usb-Ambarell_A9_DSC_EVK_Platf_0001-0:0-part1`.
  It resolved to `/dev/sdc1`, mounted at `/run/media/dan/8765-4321`, at the time of
  the operation. Re-resolve by-id and the mount before future writes; `/dev/sdc1`
  and the mount path are observations, not permanent identifiers.
- **V, action completed:** created `0x40003000.dji` in that partition's root with
  exclusive creation (no existing file overwritten), verified size **0 bytes**, and
  flushed it with `sync -f`. No firmware image or executable script was added.
- **V, later validation:** `MISC/LOG/CameraLogCur.log` now exists (reported size
  42,466 bytes), with Ambarella boot output and camera version 01.32.5432.
  The first 32,768 bytes were copied before an EIO read error. This verifies the
  output path is active with the marker present; timing and exclusive causation
  by the marker remain unproven. See
  [firmware-upgrade-log-review.md](firmware-upgrade-log-review.md) for provenance,
  the preserved prefix and the separate historical upgrade-log analysis.
- **Boundary:** logging is output capture. This marker does **not establish USB
  command input, a USB serial console, or access to the Linux shell**. The Ambarella
  USB interface observed during this session was mass storage, not CDC serial.

## Firmware trace of the logging gate and related filenames

All addresses in this section refer to `P3X_FW_V01.11.0020_m0100_part_sys.a9s`,
loaded at **`0x0e600000`**, ARM A32. This is the camera's **RTOS `sys` partition**,
not its Linux kernel or root filesystem. The image's ThreadX source-path strings
are consistent with that separation. Reproduction metadata and string references
are retained in [data/camera-marker-audit-2026-10-24.json](data/camera-marker-audit-2026-10-24.json).

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

**2026-10-24, resolved:** `scripts/re/rfs_full_extract.py` reruns the same UBI/UBIFS
walker (`scripts/re/air_survey.py`'s `ubi_volumes`/`ubifs_tree`, read-only) against
`tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_rfs.a9s` (26 MB UBI image, 2
volumes: vol 0 = 190 LEBs/rootfs, vol 1 = 14 LEBs/empty) and writes every
reconstructed file, not a hand-picked subset. **V, reproduced:** 335 regular files +
415 symlinks, matching the previously-unverified claim exactly. Output under
`tmp/air/rfs_P3X0020_full/` (gitignored `tmp/`, not committed), log at
`tmp/logs/rfs_full_extract.log`. The earlier 22-file dir (`tmp/air/rfs_P3X0020/`,
written by `scripts/re/fpga_write_path.py` for the `rpmsg_trans.ko`/`68013.ko`
disassembly task) is unaffected and still has its own narrower purpose.

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

**2026-10-24, resolved** (full UBIFS extraction, `tmp/air/rfs_P3X0020_full/`,
`scripts/re/rfs_full_extract.py` - issue #35):

- **V** `etc/init.d/S50service` runs bare `telnetd` (busybox applet, `BusyBox v1.21.1`
  string in `bin/busybox`; `/usr/sbin/telnetd` is a symlink to it) with no `-l` flag.
  Busybox telnetd's compiled-in default when `-l` is omitted is `/bin/login`
  (confirmed by the literal string `/bin/login` present in the same `busybox` binary
  next to the `telnetd`/`syslogd` applet strings) - `/bin/login` is itself a busybox
  applet symlink. **So telnetd falls back to `/bin/login`, which checks `/etc/passwd`
  + `/etc/shadow`**, not a bare unauthenticated shell.
  - **V** `/etc/passwd`: `root:x:0:0:root:/root:/bin/sh` (shell is `/bin/sh`, not
    `/bin/false` - login is not blocked at the passwd level). Two other accounts of
    note: `default:x:1000:1000:...:/bin/sh` and `a8sdk:x:1001:1001:...:/bin/sh`.
  - **V** `/etc/shadow`: `root` has a real `$6$...` (SHA-512 crypt) hash - not blank,
    not a known default (not reproduced here per this repo's secret-handling
    convention). `a8sdk` is listed in `/etc/passwd` as uid/gid 1001/1001 but its
    **`/etc/shadow` entry is `a8sdk:HHTiH8SGMjHoM:0:0:99999:7:::`** - note the shadow
    line's own uid/gid-like fields are `0:0`, and the hash is an old 13-char
    DES-crypt, i.e. a second, weaker-hashed, higher-privilege-looking credential
    distinct from `root`'s. `ftp` also has a `$6$` hash. **`default`'s shadow password
    field is empty** (`default::10933:0:99999:7:::`) - an empty hash field, not `*`/`!`
    (locked). **I** (standard BusyBox/Unix login semantics, not independently
    exercised against this exact binary): an empty shadow hash means `/bin/login`
    accepts **any input, including no password at all**, for `default`. If so,
    telnet-as-`default` needs no real credential once the interface is reachable.
- **V** `etc/init.d/S50sshd` starts `sshd -f /etc/ssh/sshd_config` every boot,
  generating RSA1/RSA/DSA/ECDSA host keys on first run if missing.
  - **V** `/etc/ssh/sshd_config` (stock-looking OpenSSH 6.x-era file, header cites
    `$OpenBSD: sshd_config,v 1.89 2013/02/06`): `PermitRootLogin yes`,
    `PasswordAuthentication yes`, `PermitEmptyPasswords no`, `RSAAuthentication yes`,
    `PubkeyAuthentication yes`. So **ssh requires a real password (or key) for every
    account** - `PermitEmptyPasswords no` specifically blocks the `default` account's
    empty-hash shortcut over ssh (unlike telnet/login above). Root login over ssh is
    permitted, gated on root's real `$6$` password.
- **V** `etc/init.d/S40network` runs `/sbin/ifup -a`.
  - **V** `/etc/network/interfaces` configures **only `lo` (loopback)** -
    `auto lo` / `iface lo inet loopback` is the only active stanza; an `eth0` static
    block (`172.168.1.11/16`) is present but **entirely commented out**. So
    `ifup -a` at boot brings up **no interface but loopback** - telnetd/sshd (which
    bind all addresses by default - `sshd_config`'s `#ListenAddress 0.0.0.0`/`::` are
    commented defaults, not restrictions) are not reachable from outside the camera
    at the moment `S40network` finishes.
  - **V, no physical Ethernet PHY**: `/lib/modules/3.8.0/kernel/` has no Ethernet MAC
    driver of any kind (checked every `.ko` under `kernel/drivers/net/` - only
    `mii.ko` and `libphy.ko`, generic PHY-framework modules with nothing to attach to,
    plus six **USB-net class drivers**: `asix`, `cdc_ether`, `cdc_ncm`, `cdc_subset`,
    `net1080`, `usbnet`, `zaurus` - all Linux host-side USB-to-Ethernet/tethering
    drivers, not a wired MAC). A `strings` pass over the Linux kernel partition
    (`*_part_lnx.a9s`) finds only generic `mdio_bus`/`mdiobus_*` framework strings, no
    named Ethernet driver (no `davinci_emac`, no SoC-specific MAC string). Combined
    with no device tree/schematic (next section), there is **no evidence of a wired
    Ethernet PHY on this board at the Linux level** - stated plainly, not just implied.
  - **V, the actual USB-net path**: `/usr/bin/cam_server` contains the literal format
    string `/usr/local/share/script/add_usb_net.sh %s` plus the literal string
    `usb0` - i.e. **`cam_server` itself calls `add_usb_net.sh usb0` at runtime**, not
    `ifup`/`/etc/network/interfaces`. `add_usb_net.sh` (`tmp/air/rfs_P3X0020_full/
    usr/local/share/script/add_usb_net.sh`) runs `ifconfig $1 192.168.1.3` and, for
    `usb0` specifically, `arping -I usb0 -A -c 10 -s 192.168.1.3 192.168.1.2` - i.e.
    the camera takes `.3` and announces/expects a peer at `.2`. **I**: this is the
    FX2LP/rpmsg USB-net path `air-id-and-stream-survey.md` already flagged as the
    phone's likely video channel - the custom `rpmsg_trans.ko`/`68013.ko` drivers
    carry no `register_netdev`/`alloc_etherdev`/`usb0` strings themselves (checked),
    so the `usb0` netdev is not created by DJI's own modules; which of the
    asix/cdc_ether/cdc_ncm/usbnet host drivers (or the Ambarella UDC gadget stack)
    actually instantiates it, and the exact trigger inside `cam_server`, is **U**
    (would need `cam_server` disassembly, out of scope here).
  - **Answering "reachable without the phone already linked"**: **V** at boot, only
    `lo` is up (telnetd/sshd unreachable externally). **I** `usb0` (the only other
    interface anything brings up, and the only one with a real IP assignment) is
    brought up by `cam_server` itself, not by a static boot script - so on the
    static evidence here, reachability depends on whatever `cam_server` is waiting
    on before it calls `add_usb_net.sh`, consistent with (but not proof of) "needs
    the phone/companion link first." Not contradicted by anything found, not
    independently proven either.
- `cam_server` also contains a hard-coded `ftpput` credential pushing to `192.168.1.2`
  (the same peer IP `add_usb_net.sh` ARPs for) - noted here as evidence of what talks
  to `192.168.1.2`, credential itself not reproduced (consistent with this repo's
  existing redaction in `fpga_write_path.py`'s own scan of the same string).
- **Practical gap**: physical UART pads for `ttyS2` have not been located on this
  board (no schematic, no device tree extracted - see "Open" below).

## 3. A factory/repair UART<->USB-CDC-ACM bridge exists in firmware

This looks closest to what you were thinking of - a DJI-added engineering command, not
a bare UART header:

- **V** Driver present: `AppCdcAcmd_Start`/`_Stop`/`_Task`/`_RcvTask`
  (sys offset `0x489b0`-`0x48db4`), log strings `"%s(): switch to CDC_ACM mode."` /
  `"%s(): switch back to UART mode."` (`0x48bcc`, `0x48c18`). A second "Multid" variant
  exists for multiple simultaneous CDC-ACM log channels.
- **I** This bridges one of the SoC's own UARTs to a USB CDC-ACM (virtual COM port)
  endpoint at runtime - i.e. get the UART console over USB instead of bare pads.
  Nearby strings `"Ambarella UART0"` / `"Ambarella UART1"` (`0x48f6e9`, `0x48f6fc`) sit
  close to this cluster; which UART (0, 1, or `ttyS2` itself) gets bridged is **U**.
- **V** A DJI engineering shell command exists to drive a related toggle: `t dji
  console [addr/0]`, help string `"Console [on/off] control. t dji console
  [0x40003000/0]. eg: t dji console 0x40003000"` (sys offset `0x76d50`). `0x40003000`
  looks like an STM32-range peripheral address, not a typical Ambarella SoC MMIO
  address - this may toggle a *different* chip's UART (the "uart M4" string at
  `0x554e8` suggests a Cortex-M4 companion is also in the picture). Whether `t dji
  console` is the same mechanism as `AppCdcAcm`, or a separate one: **U**.
- **V** The same `t dji` help table (sys offsets `0x76924`-`0x76fd4`, one continuous
  block, reproduce with `strings -n4 -tx <sys partition> | grep 't dji'`) also has:
  `t dji updater [0/1]` (firmware update test, camera/368), `t dji reboot [0/1]`,
  `t dji wdg [0/1/2]` (disable/stop/start the watchdog - useful to hold a debug session
  without auto-reset), `t dji reason` (print reset reason), and `t dji pano
  [0..4]` whose options 3/4 are `connect usb to A9` / `connect usb to DM368` - the
  switch between the camera's single external USB port talking to the A9 (control) or
  the DM368 (video), already noted in `air-id-and-stream-survey.md`.

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
- **W** (`o-gs/dji-firmware-tools` wiki, "CV310 Gimbal top board" page,
  <https://github.com/o-gs/dji-firmware-tools/wiki/CV310-Gimbal-top-board>): confirms
  this board carries m0100/m0101 ("Takes care of driving CMOS sensor and does high
  resolution video encoding... Looks very similar to FC200 video pipeline"). Its
  "Service interfaces" section (test pad locations) is unfilled (`TODO`) on the project
  wiki itself - not documented there as of this check.
- **W** (PhantomPilots forum, "Camera lost communication" thread,
  <https://phantompilots.com/threads/camera-lost-communication.141294/page-2>): a
  community member walked through finding the UART pads on this exact board (P3S/P3
  gimbal top board) with a bare USB-to-TTL adapter (no level shifting beyond 3.3V,
  avoid "smart"/auto adapters), got real Ambarella A9 boot logs at **115200 8N1** once
  the baud rate was set correctly (the thread shows the wrong-baud garbage first, then
  the fix). No unlock command needed - just RX/TX/GND wired correctly and powered on
  after the terminal is already listening. Log confirms the same architecture this repo
  found independently: `AmbaSD_InitCard`, SD-card firmware package detection/CRC check,
  NAND programming per-partition, `Cortex Boot-Up Success` banner, `UART freq: 1846153`.
  The thread explicitly says **"you need to connect to a different UART - not m0800, but
  m0100"** - i.e. there's more than one UART broken out on connectors/pads on this
  board, and only one of them is the Linux console.
- The public-source search below did not establish a USB command-input unlock -
  every confirmed command-input case it found uses a physical
  UART tap. Consistent with this doc's own firmware trace: the always-on `ttyS2` shell
  needs physical pads in those examples, and `AppCdcAcm`/`t dji console` are things
  you'd type *after* you already have a prompt, not a way to get one from nothing.

## Public corroboration, round 2 (2026-10-24, issue #20 research pass)

- **Cross-product shadow match:** `droner69/MavicPro` (public GitHub, full extracted
  `_AMBA_wm220_0100` Ambarella rootfs for the Mavic Pro's camera board, a different
  product/firmware) has the **identical** `default::10933:0:99999:7:::` (empty hash)
  and `a8sdk:HHTiH8SGMjHoM:0:0:99999:7:::` lines this repo found in the P3X camera's
  `/etc/shadow` - same account names, same literal DES hash string. That build's
  `root` entry is *also* empty (`root::0:0:99999:7:::`), wider open than P3X's real
  `$6$` root hash. This independently corroborates (different product, different repo,
  publicly posted before this research) that the empty-hash `default`/weak-hash
  `a8sdk` accounts are a shared Ambarella-SDK rootfs skeleton reused across DJI
  products, not an artifact of one firmware build - strengthens, doesn't prove, this
  doc's "likely passwordless telnet as `default`" inference.
- **IP-scheme match, different link:** VoidSec (Paolo Stagno), "Hacking the DJI
  Phantom 3", Jan 2017 (<https://voidsec.com/hacking-dji-phantom-3/>) - nmap of a
  Phantom 3 (WiFi-link variant) found **both telnetd and sshd open on the camera's
  IP, `192.168.1.3`** - matching this repo's own firmware trace of `add_usb_net.sh`
  assigning the camera `192.168.1.3` on `usb0` (section 2 above). He did not attempt
  login to the camera's telnet/ssh; his actual root access (cleartext FTP creds pulled
  from the Android app's `upgrade_config.json`, then `telnetd -l /bin/ash` re-enabled
  via a firmware downgrade) was against the **WiFi/companion board** (OpenWRT,
  ar71xx) - a different Linux system from the Ambarella camera this doc covers, same
  pattern independently confirmed elsewhere: `Howchoo/drone-wars` (public GitHub,
  OpenWERX drone-hacking-competition repo) ships that same board's boot script with
  `telnetd -l /bin/ash &` unauthenticated, no `-l` omission this time.
- **Same-shape precedent, different product:** Mavic Mini (WM160) - USB-Ethernet
  adapter, static IP, `telnet 192.168.3.10` = unauthenticated root (cited on
  mavicpilots.com, sourced from `444A49/minifindings` on GitHub). Different
  architecture (Android-based FC, not an Ambarella camera), but the same *shape* as
  this doc's own `usb0` hypothesis - USB-net interface up, telnet reachable, no
  auth - confirming DJI has shipped exactly that pattern before. Not evidence for
  this camera specifically.
- **`P3X_FW_DEBUG` independently confirmed:** `o-gs/dji-firmware-tools` issue #4
  (mefistotelis, maintainer) documents `P3X_FW_DEBUG` as a stat-only, contents-
  irrelevant flag file disabling firmware version checks - matches this doc's own
  firmware trace of that filename exactly (see table above).
- **Net, negative result on the core question:** no public source found (GitHub
  code/repo search, `o-gs/dji-firmware-tools` issues/wiki, PhantomPilots,
  MavicPilots) documents reaching or exploiting passwordless telnet/shell on the
  **P3 camera's Ambarella Linux side** specifically, via `usb0` or otherwise. This
  doc's firmware-level finding (telnetd falls back to `/bin/login`; `default`'s
  shadow hash is empty) appears to still be undocumented elsewhere, as far as
  searched 2026-10-24.

## Open / next steps

- No DJI schematic or device tree for the camera (Ambarella) board exists on this
  machine - `ttyS2`'s physical pin location is unknown. The 2016 community thread
  (`o-gs/dji-firmware-tools` issue #3) speculated about enabling USB-side UART but
  never confirmed it; this firmware trace is more specific but still not pin-level.
- **Resolved 2026-10-24 (issue #35):** `/etc/passwd`, `/etc/shadow`, `/etc/network/
  interfaces`, `/etc/ssh/sshd_config` extracted via a full UBIFS pull
  (`scripts/re/rfs_full_extract.py` -> `tmp/air/rfs_P3X0020_full/`, 335 files/415
  symlinks). See section 2 above for the findings: telnetd falls back to
  `/bin/login` (not a bare shell) and `default` has an empty shadow hash (likely
  passwordless over telnet - I, standard busybox semantics, not hardware-tested);
  sshd requires a real password/key for every account (`PermitEmptyPasswords no`);
  `ifup -a` brings up only `lo` - no physical Ethernet PHY exists on this board at
  the Linux level (no MAC driver anywhere in `/lib/modules` or kernel strings); the
  only other interface, `usb0`, is brought up at runtime by `cam_server` itself
  (`add_usb_net.sh usb0`, static IP 192.168.1.3, ARPs for 192.168.1.2), not by any
  static boot script - consistent with, but not proof of, the "needs the phone link
  first" hypothesis. **Still open:** exactly what gates `cam_server`'s call to
  `add_usb_net.sh`, and which kernel driver actually instantiates the `usb0`
  netdev (not DJI's own `rpmsg_trans.ko`/`68013.ko` - no netdev-registration
  strings in either) - both need `cam_server` disassembly, not done here.
- `AppCdcAcm` trigger condition (strap pin? a `t dji` command? automatic on a specific
  USB enumeration?) is not established from strings alone - would need to disassemble
  its call sites, or test on real hardware via the camera's own micro-USB port.
  `scripts/re/usb_switch_trace.py` (issue #25) traces the related A9<->DM368 port
  switch (`MCCTRL_SetUsbMode`, `DjiMsgStUsbSwitchStatusSet`,
  `DjiUegDm368StreamControl`) but not `AppCdcAcm` itself - no GPIO/mux identified yet,
  all three show zero direct `bl` callers in the scanned range (dispatched via a
  table, not disassembled), so this is a start, not a resolution.
