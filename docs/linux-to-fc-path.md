# Can the aircraft's Linux systems reach the flight controller?

Two Linux systems fly: the **camera A9** (m0100, Linux beside the ThreadX RTOS) and the **DM368
encoder** (m0800). The FC (m0306) is reached only through m0900 USART1
(`m0900-can-channels.md`). Tags: **V** = shown in firmware, **I** = inferred, **U** = unknown.

## Short answer

**Yes, a path exists from both, but it always goes through the camera RTOS's DUML router.** In
stock firmware neither Linux originates FC traffic: the camera's Linux has no DUML code at all,
and the DM368 only sends its own status and command replies.

```
A9 Linux user process --netlink--> rpmsg_trans.ko --rpmsg dji_app/dji_sock/dji_usbdrv-->
    A9 RTOS (DjiIpc*, DjiMsg router: ch3 = IPC channel) --route by receiver type-->
    type 3 (FC): ch0 = A9 UART index 1 --(I: gimbal/CAN or m0900 side)--> m0900 --USART1--> FC

DM368 Linux encode_usb --/dev/ttyS1 DUML--> (I: A9 UART ch2) --> same A9 RTOS router --> ...
```

## Evidence

| Hop | Fact | Tag |
|---|---|---|
| Linux ↔ RTOS | `rpmsg_trans.ko` registers rpmsg channels `dji_app`, `dji_sock`, `dji_usbdrv`, `dji_test` and bridges them to netlink (`rpmsg_netlink_init`, `netlink_kernel_create`, `rpmsg_netlink_rx/tx`). The RTOS side has `IPC_Rpmsg_*`, `DjiIpcSend`, `DjiIpcSendSyn` | V (m0100 strings and symbols) |
| RTOS DUML router | `DjiMsgChannelInit`: ch0, ch1 and ch2 are UARTs (config word 0x1C200); **ch3 is the IPC channel** (`0x0e861628`). Route by receiver type: **type 3 → ch0** (with types 9 and 19), types 8 and 15 → ch2, type 30 → ch1 | V (`fpga-write-path.md` §1) |
| What Linux uses IPC for | `trans_server` (`trans_server.cpp`, `mcctrl_server.c`, `ipc.c`): RTOS control requests (switch USB host/device, FX2 firmware load, Linux log, tick sync); H.264 buffer addresses for a UDT/TCP video server (`/tmp/fuse_d/video_udt`, I: Wi-Fi models). UEG FPGA image blocks: IPC type 3 → `dji_usbdrv` → `68013.ko` → FX2 EP2 | V |
| No DUML in camera Linux | Scanned every ELF in the Linux region: none contains the DUML CRC8 or CRC16 table. The RTOS does (`0x5dc88`) | V (absence; a table-free bitwise CRC would be missed) |
| DM368 | `encode_usb` speaks DUML on `/dev/ttyS1` (0x55, CRC8 seed 0x77, CRC16 seed 0x3692). Its status frames (sender 8 → receiver 2) reach the phone in a real capture, so its DUML is forwarded across the whole network | V (`m0800-dm368-provenance.md` §7, `ground-fx3-m1601.md` §4) |
| DM368 peer | the camera router sends types 8 and 15 to its ch2 UART, so ttyS1 is most likely wired to A9 UART ch2 | I (strong) |
| Camera ch0 → FC | m0900 reaches types 1/4/8/15 over CAN 0x412 and the FC over USART1. So ch0 is not a direct A9-to-FC wire. I: a CAN-side bridge (gimbal MCU m0400) or the m0900 side carries it on | I/U |

## Practical meaning

- **From A9 Linux:** a root process could put a DUML frame on the IPC channel that DjiMsg uses
  (ch3) and let the RTOS route it to receiver type 3. Which rpmsg channel and port ch3 binds to,
  and the IPC header (magic `0x7788`, ports `0x55xx`/`0x66xx`, `fpga-write-path.md`), are V
  for the upgrade path only. The DUML-over-IPC framing is U.
- **From DM368 Linux:** a frame written to `/dev/ttyS1` with receiver type 3 would be routed like
  any other. Routers key on the receiver (V for m0900 and the camera route table). Whether
  anything filters by sender is U.
- **Nothing here needs the phone or the radio:** both Linux hosts sit on the aircraft's own DUML
  network.

## To confirm on hardware

- Log A9 UART ch0 (A9 console docs: `camera-linux-console-access.md`) while the FC is pushing
  OSD data. Seeing type 3 traffic there makes the camera→FC hop V.
- Read `/proc/dji/trans/stat` on the camera Linux for per-channel IPC counters.
