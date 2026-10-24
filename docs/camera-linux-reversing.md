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

## 7. `rpc_trans` full disassembly - settles the `GetUSB`/`SwitchUSB` candidate (issue #37 follow-up)

Resolves the section 2 open item. Repro: `python3 scripts/re/cam_server_ghidra_disasm.py
rpc_trans` (dump `tmp/rpc_trans_ghidra/rpc_trans_dump.txt`; project archived
`re/ghidra-projects/rpc_trans_m0100.tar.gz`). 51 instructions, 3 real functions (rest
PLT thunks) - small enough to read in full, not sampled.

- **V**: `FUN_00008cd0` is the service bring-up routine - calls the `/dev/mem` mmap
  helper (`FUN_00008d8c`, two regions: `0x20000000` and `0x10000000` bytes, matching the
  "Dump Buffer"/"mmap phy addr" strings - unrelated to USB, a shared-memory frame/data
  region), then `bl 0x000088b0` with the literal string `"linux_rpcsvr_ctrl"` (vaddr
  `0x927c`) as the service name and a callback-table entry pointing at `FUN_00008acc` -
  i.e. `ambaipc_svc_register("linux_rpcsvr_ctrl", 1, {FUN_00008acc}, 1)` (symbol name
  `ambaipc_svc_register` confirmed from the dynsym table). After registering, it loops
  `sleep(10)` forever (`0x8d70`-`0x8d78`) - a keepalive loop, not polling.
- **V**: `FUN_00008acc` *is* `RPC_Ctrl_Svr_ProcRecv` (vaddr `0x9290`, used as the
  function's own self-identifying string in its entry debug `printf`, xref `0x8b14`) -
  the ambaipc message callback. Dispatches on `msg->+0x8` (a "Control Message Type"
  field, not a DUML cmdset/cmdid byte):
  - `== 1` (`0x8b38`-`0x8b88`): **TimeSync** - stores a value into a global via a
    1-instruction identity helper (`FUN_00008ff8`), then logs `"Recv TimeSync Message,
    Set TimeSync addr to 0x%x, Curr Time %u\n"` (vaddr `0x91d8`). Unrelated to USB.
  - `== 2` (`0x8b8c`-`0x8c48`): **the USB-query handler.** `system("lsusb >
    /tmp/usbtmp")` (`0x8b98`) -> `fopen("/tmp/usbtmp","r")` (`0x8ba4`) -> a
    `fgetc`/`feof` loop counting `'\n'` bytes (`0x8bb0`-`0x8be8`, i.e. **counts lines
    of `lsusb` output = number of enumerated USB devices**) -> `fclose` (`0x8c00`) ->
    `memcpy(response->+0x4, &count, 4)` (`0x8c1c`) -> `response->+0x0 = 4` (reply
    length) -> `response->+0xc = 0` (status/success) -> logs `"Recv usb query, return
    %u\n"` (vaddr `0x923c`, matches the strings-pass finding exactly).
  - default: logs `"Unknow Control Message Type(0x%x)\n"` (`0x8c4c`-`0x8c60`) with
    `msg->+0x8`.
  - No FPGA, CAN, or other issue #18/#19/#36-relevant content in this function or
    binary - the mmap'd regions are a generic shared-memory buffer, not a config/FPGA
    path.
- **V, settles `SwitchUSB`: NOT the backend.** The entire handler has exactly two valid
  message types (TimeSync, USB-query-count) and a reject-all default. There is no
  write/mode-change branch anywhere in `rpc_trans` - no call to anything resembling
  `usbsw.sh`/`usbmod.sh`. Those live exclusively in `cam_server`'s `FUN_0000b1c8`
  dispatcher (section 1a), a different process entirely. `rpc_trans` cannot implement
  `SwitchUSB` (cmdset `0x02`/cmdid `0x04`) - ruled out.
- **I, `GetUSB` plausible but still unconfirmed end-to-end.** The USB-query case's
  *behaviour* (report a USB device count on request) matches what a `GetUSB`
  (`0x02`/`0x06`) backend would need to do, and it is the only Linux-side code found
  that answers an on-demand USB query (vs. `cam_server`'s own 5 s poll, section 1b,
  which is unrelated - different consumer, feeds `add_usb_net.sh`). **But**: the
  dispatch key here is `rpc_trans`'s own internal `linux_rpcsvr_ctrl` "Control Message
  Type" enum (1/2), not a literal DUML cmdset/cmdid byte, and no RTOS-side caller that
  sends type-`2` into this `ambaipc` service was traced in this pass - confirming the
  wire from RTOS `GetUSB` through to here still needs an RTOS-side (or `rpmsg_trans.ko`/
  IPC-port) cross-reference, same class of gap as section 1a's untraced IPC producer.
  Reported to the issue as: evidence is suggestive, not proof.

## 8. `viz_tracking` - full disassembly (issue #37 follow-up, ask 1)

Resolves the section 2 open item. Repro: `python3 scripts/re/cam_server_ghidra_disasm.py
viz_tracking` (dump `tmp/viz_tracking_ghidra/viz_tracking_dump.txt`; project archived
`re/ghidra-projects/viz_tracking_m0100.tar.gz`). 164 functions, 12,149 instructions over the
67,556-byte stripped ARM EABI5 ELF - small enough for a full read, not sampled.

- **V, it is a real tracker, not a passthrough/consumer.** The binary implements an FFT
  correlation-filter tracker: `get_weight_window`/`get_confident_map`/`get_hamm_series`/
  `get_hann_series` (Hamming/Hanning window generation), `fft2`/`fft2_real`/`ifft2` via the
  FFTS library (`[fft2_with_ffts]Error: FFTS plan empty`) with a mixed-radix FFT fallback
  (`mixfft.c`, `"Prime factor of FFT length too large"` - matches the public Ooura/Jensen
  mixed-radix FFT used by several open-source MOSSE-style trackers), plus a generic
  `image_float`/`image_int`/`image_char`/`image_complex` tensor layer (`new_image_*`/
  `free_image_*`). This is the signature shape of a **MOSSE-family correlation tracker**
  (confidence map + windowed FFT correlation), not a dumb frame forwarder. Version string:
  `"[viz_tracking] ver %s\n"` / `"0.8.26nohog"` (`FUN_0000b350`, vaddr `0xb35c`).
- **V, trigger chain inside the binary (how it gets frames).** `FUN_00008e10` (the real
  `main`, called from `entry`/`__libc_start_main`):
  1. `FUN_00009a6c` - opens a device/fd and `mmap`s a physical address to a virtual one
     (`"mmap phy addr(0x%08x) -> virt addr(0x%08x)\n"`), same `/dev/mem`-style physical-frame
     mapping pattern as `cam_server`'s `rscvmem.ko` consumer (section 1d) - on failure logs
     `"MemMap error"` and exits; on success logs `"MemMap ok"`.
  2. `FUN_00009778` - creates **two `AF_NETLINK` sockets** (`socket(16, SOCK_RAW, 24)`),
     binds each, and `pthread_create`s a receive-loop thread (`FUN_0000947c`) per socket -
     logs `"init ipc ok"`.
  3. `FUN_0000b350` - version-string log + a `sizeof(cplx_t)==sizeof(float)*2` sanity check,
     then logs `"init server ok"`.
  4. `FUN_00009740("0x6607", FUN_0000b1a0, <mmap handle>)` - **registers `FUN_0000b1a0` as
     the callback for netlink message type `0x6607`**, with the mmap'd buffer handle as
     context.
  5. `sleep(9999872)` (main thread then effectively parks;~115 days - a "sleep forever"
     idiom, not a real polling interval) while the two receiver threads do the work.
- **V, dispatch in the receive thread (`FUN_0000947c`):** loops `recvmsg` on its netlink
  socket; a message of type `0x7788` is the **"recv lv yuv addr 0x%08x len %u\n"** live-view
  frame-ready notification (same family of message `cam_server`'s own live-view IPC uses,
  section 1d) and is handed to `FUN_00009bdc`; any message whose header's `+0x18` field
  equals the registered id (`0x6607`) invokes the registered callback - i.e. **`FUN_0000b1a0`
  (the tracker) runs once per incoming liveview-frame-ready IPC message**, not on a timer and
  not by polling the mmap'd buffer itself.
- **V, `FUN_0000b1a0` (the tracker entry point) and `FUN_0000a604` (2964-byte tracker
  core):** `FUN_0000b1a0` normalizes an incoming seed box (read from the IPC message: x/y/
  width/height/flags at offsets `0x0`-`0xa`) into a float center, calls `FUN_0000a604` with
  that seed plus fixed tuning constants (`5`, `0.25f`, `2.25f` - search-window/scale
  parameters) which runs the actual correlation-filter update and returns a refined center,
  stores the new center back into static state, and **every 150th frame** (`frameIdx % 150
  == 0`) logs it via `printf("[viz_tracking] frameIdx:%d, timing:%d ms, center(y,x)=(%d,%d),
  frame size:%d,%d[pitch:%d], needflip(%d)\n", ...)` (vaddr `0x6554`) - confirming the
  earlier strings-pass finding is a genuine, computed tracking result, not a dead string.
- **V, well-supported negative: no output path found.** Searched every `sendmsg`/`socket`/
  `bind`/`pthread_create`/IPC-send (`FUN_000092f8`, the module's own send-side counterpart
  to `FUN_0000947c`'s receive loop) call site in the whole binary (full disassembly, not
  sampled): the tracker core (`FUN_0000a604`) and its caller (`FUN_0000b1a0`) make **no**
  call to any of them. The one `FUN_000092f8` (IPC send) call site in the whole binary is
  inside `FUN_0000947c`'s own generic-message dispatch path (an ack/reply for the *receive*
  side), unreachable from the tracking computation. The updated center is stored to static
  memory and periodically `printf`-logged - **no evidence this binary ever reports its
  tracking result to any other process, gimbal, or control loop.** Read as: either an
  instrumented/debug-only build of a vision feature, or a shelved feature never wired to a
  consumer on this firmware (`P3X_V01.11.0020`) - the Phantom 3 Professional app does not
  expose an ActiveTrack-style feature, consistent with this reading. Not falsifiable further
  without a second firmware version or dynamic tracing on hardware.
- **V, trigger mechanism: genuinely not found, re-checked.** `grep -r viz_tracking` and
  `grep -r viz_track` across the full 335-file extraction (every script, binary, and the
  `_SYMLINKS.txt` manifest) returns **zero** hits anywhere outside the binary's own path -
  no init script, no other binary's string table, no symlink alias. This is a second,
  independent re-check past the first pass's script-only search (this pass also grepped
  binary contents and the symlink manifest). Not resolved: either it is started by a
  mechanism this static search cannot see (a hardcoded `fork`+`execve` byte pattern in
  another binary that builds the path at runtime rather than storing a literal string -
  not ruled out), or it is genuinely dead/unused on this firmware build and only ever run
  manually at a shell during development.

## 9. `boot_done` - confirmed genuinely missing, not a busybox applet (issue #37 follow-up, ask 2)

Resolves the section 2 open item.

- **V, extraction re-verified complete.** `tmp/logs/rfs_full_extract.log`: the UBI image
  (`P3X_FW_V01.11.0020_m0100_part_rfs.a9s`, 27,000,832 bytes) has exactly 2 UBI volumes
  (vol 0: 190 LEBs, vol 1: 14 LEBs, `leb_size=126976`); vol 1's UBIFS tree is empty (0 files,
  0 symlinks - a reserved/unused volume, not a second rootfs); vol 0 (the real rootfs)
  walked to **335 files + 415 symlinks with zero exceptions logged**, and all 335 were
  written to disk (`find tmp/air/rfs_P3X0020_full -type f | wc -l` = 335, excluding the
  `_SYMLINKS.txt` manifest itself) with the symlink manifest listing exactly 415 entries -
  an exact match between what the UBIFS walker found and what landed on disk, no silent
  drop. No second, larger volume exists that could be hiding a missed binary.
- **V, re-confirmed:** `grep -r boot_done` across the full 335-file tree (scripts, binaries,
  and `_SYMLINKS.txt`) finds only the same 6 **call sites** already documented (section 2) -
  still no binary, script, or symlink named `boot_done` anywhere.
- **V, busybox does NOT provide it as an applet.** `bin/busybox` on this rootfs is a
  dynamically-linked ARM ELF (not a static multi-call binary stripped of its string table)
  and its applet names are present as **plain ASCII strings** in the binary (confirmed:
  `ash`, `cat`, `echo`, `hush`, `ifconfig`, `init`, `insmod`, `kill`, `ls`, `mdev`, `mount`,
  `ps`, `rmmod`, `sh`, `udhcpc`, `umount` all found via `strings`). `boot_done` is **not**
  among them, and a plain `strings -a -n2` dump of the entire binary (24,633 lines) contains
  no `boot_done` substring at all. Since this busybox build's applet names are readable via
  `strings` at all (ruling out "it's compiled in but the string got dead-stripped" as an
  explanation), this is a clean negative: **this busybox does not implement a `boot_done`
  applet.**
- **I, settled: every one of the 6 call sites silently no-ops.** `boot_done` is referenced
  as a bare command (not a path) in `S50service`, `S52wifi`, `ap_start.sh`,
  `wifi_start.sh`/`p2p_start.sh`/`sta_start.sh`, all run under `/bin/sh` -> `busybox ash`/
  `hush`. With no binary, script, or busybox applet named `boot_done` anywhere on the
  filesystem and no shell builtin by that name in busybox's `ash`/`hush` (not in the applet
  string table at all, builtins included), every one of these call sites hits `command not
  found` and the shell continues (exit status nonzero, not fatal under the surrounding
  script logic as read in each of the 6 sites). **This is a real finding, not a shrug**: a
  firmware-wide dead reference across 6 init-path call sites - either a leftover from a
  retired synchronization mechanism (plausible name: a flag file or semaphore a "boot done"
  gate once checked) that was dropped without removing its call sites, or a build-
  configuration variant where `boot_done` exists in a different SKU/region image but not
  `P3X_FW_V01.11.0020`. Not resolved which, and not resolvable from this image alone.

## Not done / open

- `rpc_trans`'s RTOS-side caller for `linux_rpcsvr_ctrl` message type 2 (USB query): not
  traced this pass either - a quick repo-wide grep for the literal string
  `linux_rpcsvr_ctrl` outside this doc's own analysis output found nothing, but the RTOS
  `sys`/m0100-companion firmware partition where that caller would live has not been
  extracted/disassembled in this repo yet - would need that extraction first, then a real
  Ghidra pass, before this can move past "plausible, actively searched, not found" (still
  not **V**, same status as the previous pass left it).
- `FUN_0000b1c8`'s caller / the IPC message producer for its `+0x10` type field: not
  traced (needs `libambaipc.so` or an RTOS-side cross-reference).
- `viz_tracking`'s own output path: **resolved this pass (section 8)** - full disassembly
  done, confirms real FFT-correlation tracking logic with no reachable send/IPC-output call
  site from the tracker core. Its **trigger is still genuinely unresolved** - re-checked
  against binary contents and the symlink manifest too (not just scripts), zero hits; either
  it's started by a mechanism a static string/grep search can't see, or it's dead/unused on
  this firmware build.
- `boot_done`: **resolved this pass (section 9)** - extraction re-verified complete (exact
  335 files/415 symlinks, no logged errors), confirmed absent from busybox's own applet
  string table - genuinely missing, not a hidden applet; all 6 call sites silently no-op
  under `/bin/sh`.
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
