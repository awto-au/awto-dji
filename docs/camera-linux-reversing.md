# Camera Linux (m0100, Ambarella A9) userland: binary reversing

Goes past `camera-linux-console-access.md` (access paths: telnet/ssh/UART, already closed
by #20/#35) and `air-id-and-stream-survey.md` (strings-level fragments) into the actual
code of the Linux userland binaries. Scope: issue #37. Tags: **V** verified in bytes/
disassembly (address cited), **I** inferred, **U** unknown. Static analysis only, no
hardware touched. Addresses below are runtime vaddr (ELF `LOAD` segment: file offset +
`0x8000`), matching `readelf -l`.

Source: full UBIFS rootfs extraction (issue #35, `scripts/re/rfs_full_extract.py`),
`tmp/air/rfs_P3X0020_full/` (335 files/415 symlinks, gitignored `tmp/`). Ghidra project
archived per `scripts/re/ghidra_archive.py`: `re/ghidra-projects/cam_server_m0100.tar.gz`.
Reproduce: `python3 -I scripts/re/cam_server_ghidra_disasm.py cam_server`
(log `tmp/logs/cam_server_ghidra_disasm.log`, ~6 s on this build; Ghidra post-script
`scripts/re/ghidra/DumpELF.java`).

No secrets reproduced: a hardcoded FTP credential exists in `cam_server` (see below) -
its nature is described, the literal value is not pasted here.

## 1. `cam_server` - full disassembly (issue #37 ask 1)

- **V**: ARM EABI5, dynamically linked, **not PIE** (`EXEC`, entry `0x9b20`, `LOAD`
  segments at fixed vaddr `0x8000`/`0x18000`), stripped, 35 KB. Ghidra ELF loader,
  no explicit base needed (unlike the raw Cortex-M firmware images elsewhere in this
  repo). 261 functions total (194 library/PLT thunks, 67 local), 5381 instructions.
- **V, sibling binary**: `cam_server_old` (27 KB, same dir) is **not stripped** - real
  symbol names (`IPC_*`, `UDT_Server_*`, `MCCTRL_*`, `IpcMcctrlRecvProc`,
  `CommMonitorProc`/`CommandRecvProc`/`CommListenProc`). It is an **older, smaller**
  build (no USB-net bring-up, no FX2LP/wifi-fw-upload strings, no authorized-MAC
  check) - useful as a naming reference for the IPC/UDT plumbing shared with current
  `cam_server`, not a byte-identical twin. `camserver_restart.sh` can still launch it
  standalone (`/usr/bin/cam_server_old &`) - a live fallback/debug build shipped
  alongside the production one.

### 1a. The command/control dispatcher: `FUN_0000b1c8`

- **V**: single large function (`0xb1c8`-`0xb998`, ~2000 bytes) dispatches on a `u16`
  field at offset `0x10` of its second argument via a 9-entry branch table
  (`0xb1f8: ldrh r3,[r3,#0]; sub r3,r3,#1; cmp r3,#8; ldrls pc,[pc,r3,lsl#2]` at
  `0xb200`-`0xb204`). Each case logs a string with `puts()` then runs a shell command
  with `system()` (`bl 0x97cc`, confirmed PLT thunk `system`). This is the actual
  command/control surface the brief asked for - not loose fragments:
  - case -> `system("/usr/local/share/script/usbsw.sh host")` (`0xb238`)
  - case -> `system("/usr/local/share/script/usbsw.sh device")` (`0xb24c`)
  - case -> `system("/usr/local/share/script/usbmod.sh ins")` (`0xb260`)
  - case -> `system("/usr/local/share/script/usbmod.sh rmv")` (`0xb274`)
  - case -> reads `/sys/bus/usb/devices/1-1/manufacturer` (`enc V%u.%u.%u.%u`, the
    already-known FX2LP version read, `0xb288`) - now pinned to this dispatcher,
    not a loose string.
  - case -> `system("fxload -t fx2 -d 0547:1002 -i /home/Vend_Ax.iic")` (`0xb47c`,
    stock loader) **or** `system("fxload -t fx2 -d 0547:1002 -i %s")` (`0xb4d0`,
    caller-supplied path) gated on `"68013 fw should be in SD card"` (`0xb4ac`) -
    **new**: `cam_server` can push an **SD-card-supplied FX2LP firmware image**
    through `fxload` at runtime, not just the stock `Vend_Ax.iic`. Logged as
    "Update 68013 start/end" (`0xb474`/`0xb518`).
  - case -> Wi-Fi firmware upload: `"wifi fw should be in SD card"` (`0xb728`) gates
    `system("ftpput -u root -p <redacted> 192.168.1.2 %s %s")` (`0xb6ec`) - pushes
    an SD-card file to the Wi-Fi companion module over FTP. **Credential nature**:
    hardcoded `root`-equivalent FTP username/password pair, visible in the binary's
    `.rodata` as a `sprintf`-style format string; not reproduced here per repo
    convention. Logged "Upload wifi fw start/fail/end" (`0xb6d4`/`0xb734`/`0xb740`).
  - case -> `"Update authorized MAC: %02x:...\n"` (`0xb870`) - Linux-side mirror of
    the RTOS `DjiMsgAuthorizedMac` mechanism (`air-id-and-stream-survey.md`): this
    dispatcher is how a new authorized MAC reaches `cam_server`'s own accept-filter
    (section 1c), not just the RTOS side.
- **I**: the struct passed in is consistent with an IPC message (`ambaipc_clnt_*` is
  linked, `libambaipc.so`) or an internal thread-queue record; the exact caller/queue
  producer was not traced (would need `libambaipc.so` or the RTOS-side encoder for the
  `+0x10` type field).

### 1b. The USB hotplug monitor: polls `lsusb`, does not use netlink

Resolves the open "what gates `cam_server`'s call to `add_usb_net.sh`" question from
`air-id-and-stream-survey.md` / `camera-linux-console-access.md`.

- **V**: `FUN_0000e178` is a worker thread (`pthread_create` call site at `0xe25c`,
  one of 5 in the binary: `0xaa50`, `0xbd78`, `0xbdcc`, `0xbe20`, `0xe25c`). Loop:
  call `FUN_0000e044`, `sleep(5)` (`0xe190`-`0xe194`), repeat.
- **V**: `FUN_0000e044` is `popen("lsusb", "r")` (literal strings at vaddr
  `0xfaf0`/`0xfaf8`, read via file-offset `vaddr-0x8000`), then `fgets`/`sscanf` each
  line against the format string `"Bus %03u Device %03u: ID %04x:%04x"` (vaddr
  `0xfafc`, matches the same literal already seen in the strings-only pass) - i.e.
  **`cam_server` enumerates USB devices by shelling out to `lsusb` and text-parsing
  its output every 5 s**, not via a netlink `uevent` socket or `/sys` inotify.
- **V**: new/removed bus:device:vid:pid tuples are logged `"add (%x %x %x)\n"` /
  `"del %s(%x %x %x)\n"` (vaddr `0xfb20` region) and, on add, `FUN_0000e044`'s
  caller `FUN_0000e178` calls `FUN_0000def8(buf, len)` at `0xe1e8`, which contains
  the `"/usr/local/share/script/add_usb_net.sh %s"` string (`0xe014`) - **this is the
  exact call site** that brings up `usb0` once the FX2LP enumerates.
- **I, corroborated by a disabled predecessor**: `usersetting_s2.sh` has a
  **commented-out** block calling a *different*, standalone binary, `monhotplug`
  (present in the rootfs, `usr/bin/monhotplug`, 8144 B), which itself contains the
  same `add_usb_net.sh %s` string plus `DEVTYPE=usb_%s`/`"Get usb info fail"` -
  environment-variable names that match a kernel `mdev`/`udev` **uevent** payload,
  not `lsusb` text. **V**: the DJI engineers' older design used a netlink/mdev-style
  hotplug listener (`monhotplug`); the shipped `cam_server` build **inlines its own
  polling replacement** instead and `monhotplug` is dead code left on the rootfs,
  disabled at the script level (comment block, not just unreferenced).

### 1c. Authorized-MAC check via ARP, not a passive compare

- **V**: `FUN_0000d4a8(ip_str, ...)` builds a `sockaddr_in` (`bzero` 0x44 bytes,
  `sin_family=AF_INET` at `0xd4f4`), calls `inet_aton(ip_str, &sin_addr)` (`0xd508`),
  then issues the `SIOCGARP` ioctl (string `"Get arp map info SIOCGARP fail!\n"` at
  the function's error path) to resolve the connecting peer's **MAC address from its
  IP** via the kernel ARP table - i.e. the "Invalid connection, MAC: ..., reject!"
  check (`air-id-and-stream-survey.md`) authenticates a TCP/UDT client by looking up
  the ARP entry for the IP it connected from, not by anything in the payload.
- **I**: this is consistent with the `usb0` link (static IPs `.3`/`.2`, ARP already
  seen in `add_usb_net.sh`) being the channel this filter guards - a peer at a
  different IP that still ARPs correctly (e.g. a MITM on the same USB-net segment)
  would pass this specific check; not tested on hardware.

### 1d. Live-view bitrate control and image-data monitor

- **V**: `FUN_0000d288` logs `"Set bitrate to %u Kbps. Status: %d"` (string at
  `0xf914`) - a runtime bitrate-change entry point.
- **V**: `FUN_0000d3d0`/`FUN_0000e35c` create/init an IPC object named in-binary
  `DjiLvBitrateChangeIpcCreate` (strings `"create LvBitrateChangeIpc client fail"`,
  `"init DjiLvBitrateChangeIpcCreate() error/ok"`) - a dedicated IPC channel to the
  RTOS side purely for live-view bitrate negotiation, separate from the main
  `IPC_*`/`ambaipc_*` command channel in section 1a.
- **V**: `FUN_0000e288` opens `/proc/dji/test/rscv_addr` (`fopen`, vaddr string
  `0xfb38`) - a **third** custom `/proc/dji/*` entry (alongside the already-known
  `/proc/dji/trans/stat` from `rpmsg_trans.ko`) exposed by the `rscvmem.ko` module
  (loaded by `usersetting_s2.sh`, "rscv" = reserved/shared-memory region address,
  consistent with the H.264/liveview buffer addresses `cam_server` receives from the
  RTOS: `"recv h264 codec addr 0x%08x len %u"`). Full consumer logic not traced past
  the `fopen`/parse call.

## 2. Other Linux-side binaries (strings-level pass, not full Ghidra - budget)

- **V, `rpc_trans`** (6948 B, started unconditionally by `usersetting_s2.sh`, separate
  process from `cam_server`): contains `"lsusb > /tmp/usbtmp"` and
  `"Recv usb query, return %u\n"` - **a second, independent USB-query path**, driven by
  a received request (not a poll loop like `cam_server`'s). **I, not yet confirmed by
  disassembly**: this is a strong candidate for the actual Linux-side backend of the
  camera-receiver DUML `GetUSB`/`SwitchUSB` commands (cmdset `0x02`, cmdid `0x04`/`0x06`)
  that `air-id-and-stream-survey.md` left as **U** ("no literal-pool reference found on
  the RTOS side") - if the RTOS forwards that DUML command to Linux over IPC/rpmsg
  rather than handling it in RTOS code directly, this is where it would land. Needs a
  disassembly pass on `rpc_trans` to confirm the IPC port/message type it listens on.
- **V, `monhotplug`** (8144 B): see 1b above - disabled predecessor of `cam_server`'s
  inlined USB monitor, same `add_usb_net.sh` call, env-var-style parsing
  (`DEVTYPE=usb_%s`).
- **V, `viz_tracking`** (67556 B, started by nothing found in `etc/init.d` or the
  `usr/local/share/script/*` tree - **U** trigger): references `/dev/mem` and
  `/tmp/fuse_d/video_udt` (the same UDT video-socket path family as `cam_server`'s
  `/tmp/fuse_d/%s`) - a vision/tracking consumer of the same live-view buffer, not
  disassembled this pass.
- **V, `ipcbind`/`ipcinfo`**: reference `/proc/ambarella/rpc_profiler`, generic
  Ambarella RPC-binding daemons (`ipcbind -b` run from `S50service`), not DJI-specific.
- **V, `hdr_merge`**: references `/dev/mem` only; started unconditionally after
  `cam_server` in `usersetting_s2.sh`; no DJI-specific strings found, not pursued.
- **`boot_done`**: referenced by name in four init scripts (`S50service`, `S52wifi`,
  `ap_start.sh`, `wifi_start.sh`/`p2p_start.sh`/`sta_start.sh`) but **not present as a
  binary, script, or busybox applet anywhere in the 335-file extraction** - **U**:
  either a busybox applet this image's `busybox` doesn't actually provide (the init
  scripts would then silently no-op on `command not found` under `/bin/sh`), or it
  lives in a part of the rootfs this UBIFS extraction didn't reach. Worth a targeted
  recheck of the extraction completeness before assuming it's genuinely missing.

## 3. Developer/diagnostic tooling (issue #37 ask 2)

- **V, factory challenge-response cipher tool**: `/usr/local/share/script/
  cmdctr.cipher.sh` wraps `openssl bf-cbc` (Blowfish-CBC) encrypt/decrypt with a
  passphrase argument, with an explicit comment: *"DEBUG only: camera should never
  encrypt and generate response"*. This is a **developer-only test harness for a
  challenge/response scheme** the camera's production code only ever answers
  (decrypts), never originates - directly relevant to the ATSHA204/authorized-MAC
  authentication story in `air-id-and-stream-survey.md` ("DjiEncryptCheckA9Mac" etc.)
  as the Linux-side tool an engineer would use to hand-craft a matching
  challenge/response pair for bench testing. No key/passphrase value is shipped in
  the script itself (passed as a CLI arg); not something this pass can exercise
  further without a live key.
- **V, raw GPIO poke script**: `/usr/local/share/script/t_gpio.sh <pin> <0|1>` writes
  through `/proc/ambarella/gpio` (binary command protocol: `c\x<hex pin>\x01` to
  configure as output, `w\x<hex pin>\x<0|1>` to drive it) or falls back to
  `/sys/class/gpio/gpioN/{direction,value}`. Used by `bt_start.sh`/`wifi_start.sh`
  for enable-pin control; this is the generic engineering tool for toggling any named
  GPIO from a shell, independent of the FPGA-mux GPIO pair (`0x30`/`0x2f`) already
  traced on the RTOS side (`air-id-and-stream-survey.md`).
- **V, SD-card TCP tuning hook** (already known, re-confirmed at the call-site level):
  `tcp_script.sh` runs an arbitrary `/tmp/fuse_d/MISC/tcp_tuner.sh` off the SD card
  with `/bin/sh` if present; the shipped `tcp_tuner.sh` template raises
  `rmem_max`/`wmem_max` to 16 MiB and disables `tcp_sack`/`tcp_timestamps` - a
  dev-only network-stack tuning knob left reachable from the SD card.
- **V, `ssh`/`scp`/`gdbserver`/`strace` all present** (`usr/bin/gdb`, `gdbserver`,
  `strace`, `strace-log-merge`) - a **full remote-debugging toolchain** shipped on a
  production rootfs (not just busybox): `gdbserver` + host `gdb` would let a telnet/ssh
  session attach to any running process (`cam_server` included) live.
- **V, HTTP directory listing of the SD card, no auth**: `home/http/cgi-bin/index.cgi`
  (ELF, stripped) is a `readdir`/`qsort`-based Apache-style "Index of" generator; the
  `cherokee.conf` vhost (`vserver!1!rule!4!match!directory = /cgi-bin`, handler `cgi`)
  wires `/cgi-bin/*` into the `cherokee-worker` webserver that `S50service`-era scripts
  start on port 80 (`restart_webserver.sh`). **I**: given the `index.cgi` string
  `/tmp/fuse_d` and `REQUEST_URI`, this serves a browsable listing of the mounted SD
  card over plain HTTP with no credential check anywhere in `cherokee.conf` - same
  no-auth posture as the telnet `default` account already documented, on a different
  service. Not exercised against hardware.
- **V, `cam_server_old` left in place**: see section 1 - a non-stripped, differently-
  featured fallback build, switchable via `camserver_restart.sh old`.

## 4. FPGA-related Linux userland (issue #37 ask 3)

- **V, re-confirmed, not found**: no `fpga`/`altera`/`cyclone`/`jtag`/`idcode`/
  `spidev`/`uio` string anywhere in `cam_server`, `rpc_trans`, `util_svc`,
  `viz_tracking`, or the kernel partition (already established in
  `air-id-and-stream-survey.md`; re-checked against the full 335-file extraction,
  same result).
- **V**: the only FPGA-adjacent Linux-side code is the **68013/FX2LP firmware-load
  path** inside `cam_server` (section 1a) - `fxload` loading `Vend_Ax.iic` (or an
  SD-supplied alternative) into the FX2LP, which is the FPGA's slave-FIFO USB peer
  per `fpga-write-path.md`. Linux itself still never touches FPGA configuration
  memory directly; this doc adds the **SD-card-supplied-firmware variant** of that
  path (not previously documented) but does not change the "chip that writes the
  configuration memory" conclusion in `fpga-write-path.md` (still **U**, FPGA-resident
  logic is the only remaining candidate).

## 5. Firmware-update specifics, Linux side (issue #37 ask 4)

- **V**: `cam_server`'s dispatcher (1a) is the **only** Linux-side code found that
  performs a firmware push, and it pushes two things, both **not** the FPGA image:
  1. FX2LP (`68013`) firmware, via `fxload`, optionally from an SD-card file instead
     of the stock `/home/Vend_Ax.iic` loader - **new finding**, not in
     `fpga-write-path.md` (which only covers the FPGA module's own UEG-orchestrated
     path through `rpmsg_trans.ko`/`68013.ko`/`usb_bulk_msg`, unrelated to this
     `fxload` mechanism - the two are different firmware items carried by different
     mechanisms, both living in `cam_server`).
  2. Wi-Fi companion-module firmware, via `ftpput` to `192.168.1.2` (credential
     redacted, section 1a).
- **V**: the FPGA image itself (`PFPGAFw3.bin`) never passes through `cam_server`,
  `rpc_trans`, or any other userland binary checked here - confirms
  `fpga-write-path.md`'s path (RTOS UEG -> IPC port `0x5501` -> `rpmsg_trans.ko` ->
  `68013.ko` -> `usb_bulk_msg`) is a **kernel-module-only** relay on the Linux side,
  with no userland process in the loop for that specific transfer. `rpmsg_trans.ko`/
  `68013.ko` disassembly already exists (`fpga-write-path.md` section 4); not
  repeated here.

## 6. Switch/mux mechanisms, Linux side (issue #37 ask 5)

Beyond the RTOS-side GPIO mux (`DjiCmmDownloadModeCtrl`, GPIO pair `0x30`/`0x2f`,
issue #25) and the A9<->DM368 port switch, the Linux side has its **own**,
independent switch:

- **V**: `/proc/ambarella/uport` - a single-word `echo host`/`echo device` sysfs-style
  control for the A9's own USB **controller role** (host vs. device/gadget), read
  back via a formatted dump (`cat /proc/ambarella/uport | sed -n '3p'`, fields
  `CURR_CTRL`/`CURR_PORT`). Three scripts drive it: `usbsw.sh` (bare echo),
  `setusbmode.sh` (reads current state first, only switches + (un)loads
  `ehci-hcd`/`ohci-hcd` on an actual transition), and `usb_mass_storage.sh`/
  `usb_msg_dev.sh`/`insert_usb.sh` (boot-time one-shot host-mode bring-up for mass
  storage / gadget serial).
- **V**: `cam_server`'s dispatcher (1a) calls `usbsw.sh host`/`device` and
  `usbmod.sh ins`/`rmv` directly via `system()` - i.e. **the Linux-side host/device
  role switch is itself remote-controlled by whatever feeds `cam_server`'s IPC
  dispatcher**, not just a boot-time static choice. This is a distinct mechanism
  from the RTOS GPIO mux: that one switches which *SoC* (A9 vs DM368) owns the
  shared USB port; this one switches whether the **A9 itself** acts as USB host or
  device once it owns the port. The two are orthogonal and both get exercised during
  an FPGA/68013 firmware update (`fpga-write-path.md`'s "Switch To USB Host" step is
  the RTOS-side GPIO mux; this Linux `/proc/ambarella/uport` switch is what makes the
  A9's own controller usable as a host afterward, matching the `usbmod.sh ins` case
  that inserts `ehci-hcd`/`ohci-hcd` only on request).
- **V**: `usbmod.sh`/`usbsw.sh` are also reachable manually at a shell (`t_gpio.sh`-
  style direct scripts, no auth beyond the shell itself).

## Not done / open

- `rpc_trans`'s "Recv usb query" handler: not disassembled - would settle whether it's
  the Linux-side `GetUSB`/`SwitchUSB` DUML backend (section 2).
- `FUN_0000b1c8`'s caller / the IPC message producer for its `+0x10` type field: not
  traced (needs `libambaipc.so` or an RTOS-side cross-reference).
- `viz_tracking`'s trigger (what starts it - no static reference found in any init
  script or `usr/local/share/script/*.sh`) and its own command surface: not
  disassembled this pass (67 KB, stripped - a full Ghidra pass is feasible, just not
  done under this pass's time budget).
- `boot_done`: genuinely missing from the 335-file extraction despite 6 references by
  name - re-verify extraction completeness before concluding it's an image defect.
- `cherokee`/`index.cgi` auth posture: not exercised against hardware (static only).
- `hdr_merge`, `util_svc`, `ipcbind`/`ipcinfo`: strings-only, no DJI-specific surface
  found; lower priority for a future pass.

## Reproduce

```sh
python3 -I scripts/re/rfs_full_extract.py            # if tmp/air/rfs_P3X0020_full/ is gone
python3 -I scripts/re/cam_server_ghidra_disasm.py cam_server
# full dump: tmp/cam_server_ghidra/cam_server_dump.txt
# archived Ghidra project: re/ghidra-projects/cam_server_m0100.tar.gz
nm -C tmp/air/rfs_P3X0020_full/usr/bin/cam_server_old   # unstripped sibling, symbol reference
strings -a -n6 tmp/air/rfs_P3X0020_full/usr/bin/cam_server | sort -u
```
