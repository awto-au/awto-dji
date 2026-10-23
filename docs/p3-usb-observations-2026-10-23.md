# Phantom 3 Professional USB observations, 2026-10-23

What the controller and aircraft do on USB, from two USBPcap captures (`captures/2026-10-23_*`)
and live read-only probing with `scripts/duml_probe.py`. Companion to
`usb-tools-test-2026-10-23.md` (tool test). Hardware: P3 Pro (owner-confirmed), Windows 11 VM.
Everything here is observation of owner-owned hardware; nothing was written to either device.

## The two USB ports

| | Controller | Aircraft side |
|---|---|---|
| VID:PID | `2CA3:0008` | `FFF0:0008` (matches `fc-usb-port.md`) |
| Descriptor | "DJI CONTROLLER", USB 1.1 (`bcdUSB 0x0110`) | USB 2.0 (`0x0200`) |
| Windows driver | inbox `usbser` (not DJI's VCOM INF) | same |
| DUML | **answers** | **never answers**, only talks |

Device addresses swap between replugs (1.1 / 1.2): read per time, not per address.

## Serial line settings (Assistant 2, `captures/…both-connected.cdc-ctrl.txt`)

- Enumerates at **9600 8N1** (Windows default), Assistant sets **115200 8N1** on every open.
- Open: `SET_CONTROL_LINE_STATE` **RTS=1, DTR=0** (`wValue 0x0002`). Close/reset: 0/0.
  **DTR is never asserted. No SEND_BREAK.**
- Controller echoes line coding back correctly (GET after SET = 115200 8N1).
- **Aircraft port returns 7 zero bytes to `GET_LINE_CODING`, even directly after a SET to
  115200** (seen at 100.8 s, 5 reads). It is a CDC-looking port that ignores line coding, so baud
  is irrelevant there and it behaves like a raw pipe.

## Controller (2CA3) DUML, all CRCs valid

Requests (host 0a to 0e unless noted), 100% reproducible live from our script:

| set/id | reply |
|---|---|
| 00/0c ping | ack, payload `000000000000` (one run `e30000000000`: first reply after a fresh open) |
| 00/01 version | `00 10` + `GL300C` padded to 16 + `07010103001c18054302000000` (version words, undecoded) |
| 00/ff build | `WM320 A7_LPC1 20170828/00` |

The controller also answers the Assistant's heartbeat variant (receiver `00`, payload `00`) with a
normal ack. Sender/receiver are wire bytes: `0a` = PC, `0e` = type 14 index 0; `snd=03` = aircraft.
Meaning of the type numbers is not decoded here (dji-firmware-tools has the table).

## Aircraft port (FFF0): one-way log stream

- Emits valid DUML frames, **sender `03`, receiver `0a`, seq `ffff`, set 00 id `0e`**, payload is
  an ASCII log line, about 50 bytes/s in total. Content seen: `tgimbal  pitch 0.00, roll 0.00, yaw
  158.x` (about 1 Hz, yaw drifts by 0.1), `>>sending limit areas:[0]` (about every 5 s), and in
  one capture window `Eeprom write offset:1d0`, `gps init: nack:0 ack:18`, `[LED] changed: no atti`,
  `[FDI AHRS[1]]:(wxyz)wait for static…`, `(mxyz)compass stuck!!!`, `check_comm_s…`.
  (A boot-ish log: GPS not locked, compass stuck, no attitude.)
- Assistant pings it (`0a` to receiver `00`, set 00 id `0c`, 1 payload byte) every ~0.5 s,
  **167 frames total, zero replies**. Our probe confirms: ping/version/build to this port get nothing.
- This matches the repo's finding that the flight controller's USB port is silent to DUML. What is
  new: the port is not dead, it **transmits** (log lines) and DJI's tool still tries it.

## Sensitivity to DTR/RTS after open (one experiment, not a proven rule)

- Probe v1 re-assigned `dtr/rts` right after `open()`: **0 bytes** from COM4 over four runs.
- Probe v2 sets them once before `open()` (RTS=1, DTR=0): stream returns at ~50 B/s.
- A direct test with DTR=0/RTS=1, DTR=1/RTS=1 and DTR=1/RTS=0 all streamed (208 to 320 B in 4 to 5 s)
  when set before opening. So it is the extra change after open (a 0/0 pulse or reconfigure), not
  the final value, that stopped the stream. Why: unknown (hypothesis: the device re-syncs its log
  stream on a control-line edge and waits). Treat as "set lines before open, don't toggle".

## Other

- Neither device spoke DUML until the host did: controller silent on bus until queried; aircraft
  stream starts on its own.
- Unplugging one device does not stop a root-hub capture; re-enumeration is recorded (23.6 s,
  190.9 s, 216 s, 223 s).
- The earlier Assistant run was only start-up traffic: it never got past DJI's login box.

## Open

- Version words after `GL300C` and the `0x00/0x0c` payload (`e3` vs `00`) are not decoded.
- Why the Assistant treats WM320 as unsupported is still inference.
- Aircraft-side commands beyond ping/version/build (and other receiver addresses) not tried. The
  existing `scripts/probe_fc_usb.py` / `docs/fc-usb-port.md` cover some of that; not cross-checked.
- Linux not tested. `pcap_decode.py` handles USBPcap (Windows) captures only; usbmon would need a
  second header parser.
