# Ground USB (m1601, Cypress FX3, `gnd_fx3_cyusb2014`): where DUML and video meet the phone

Owner hardware is a **GL300C** RC (`fc-usb-port.md`). On GL300b/c the ground video decoder
(`m1300`, DM365 per `control-plane-re.md`/`ground-upgrade-path.md` — correcting an earlier
DM368 label in this file, same module slot, wrong part number) is **not populated**: Dan's
point (2026-10-31) is that one shared ground-RC PCB design covers both LCD-equipped and
phone-tethered (FX3) variants, and only the LCD variant needs a local video decoder — the FX3
variant streams raw H.264 straight to the phone instead, so `m1300`'s footprint is simply empty
on this board. This also explains why the shared firmware *package* still contains an `m1300`
DM365 image (`02.26.0000`, `Salted__`-encrypted, `ground-upgrade-path.md`): one firmware bundle
ships across variants regardless of which boards populate the chip, not evidence the chip is
present here. The phone-facing USB is a **Cypress FX3 / CYUSB2014** running module `m1601`
(ThreadX, FX3 SDK), fed directly by the ground FPGA. Sources: dji-firmware-tools wiki pages
m1300/m1600/m1601; I for anything not shown here. Tags: **V** = shown in code or in a capture,
**I** = inferred, **U** = unknown. Reproduce with `python3 scripts/re/fx3_m1601.py <m1601.bin>`,
which asserts every V code claim, and `python3 scripts/re/aoa_chunk_decode.py <relay log>`.

**Input.** The RC firmware (`C1_FW_*`) is not on DJI's download page. Before RC firmware was
split out, DJI shipped the RC modules inside the aircraft package. Source used here:
`dl.djicdn.com/downloads/phantom_3/en/Phantom_3_Professional_Firmware_v1.3.20__en.zip` →
`P3X_FW_V01.03.0020.bin` → `m1601` **02.00.0002** (hashes in `data-manifest.md`).
- Its `m2001` (ground FPGA) is byte-identical to the operator's `C1_FW_V01.06.0000` `m2001`.
- The operator's C1 package carries `m1601` **02.00.0006**. Re-run the script on that build to
  confirm nothing below changed.

## Answer in one picture

```
             DOWNLINK (RC -> phone)                                   UPLINK (phone -> RC)
ground FPGA --8-bit GPIF, PIB socket 2, 2 KB buffers--> FX3 CPU --55 CC 4A 57 <len> <H.264>--> phone
ground UART peer (I: m1400) --115200 8N1 DUML--> FX3 CPU --55 CC 49 57 <len> <DUML frames>--> phone
phone --bare DUML bytes--> FX3 CPU --(not for FX3, receiver != type 13)--> UART 115200 --> (I: m1400)
```

- **V:** video and DUML reach the FX3 on **separate physical inputs**: the FPGA parallel port
  and a UART.
- **V:** the FX3 CPU interleaves them into one USB stream for the phone, tagging every chunk
  with an 8-byte header.
- **I, by elimination:** the ground FPGA is where the radio stream is split back into video
  (to the FX3) and DUML (to the UART peer). On the air side, `m0800-dm368-provenance.md` §7
  shows the reverse.
- **Structural check against this (pluribus `m2001` lift, 2026-10-31): no UART-shaped logic
  found near the two candidate MCU-facing pads other than the confirmed SPI slave interface.**
  Pads AD5/AD13 (the only other `chip_ref=MCU` candidates besides the 4 already-confirmed SPI
  pads) each fan out to 9 FFs with no counter/divider stage gating them (no `ena` on any of the
  18 FFs; all sample at the full main-clock rate) and no FF-to-adjacent-FF shift-register
  chaining (each FF's D-LUT reads the pad directly plus its own Q — a `register_feedback`
  latch group, not a shift register). A UART RX needs both a baud-derived sampling enable and a
  shift chain; neither exists here. This doesn't prove the FPGA is absent from the DUML path (a
  structure elsewhere in the lift, or one this search didn't reach, could still exist), but it
  rules out AD5/AD13 specifically as a UART, and strengthens — without fully confirming — the
  existing "bypasses the FPGA" picture over the alternative (FPGA relays DUML both ways) that was
  raised and checked for directly.

## 1. USB identity: one chip, both phone types (V)

| Mode | Descriptor / role | Endpoints | Data path |
|---|---|---|---|
| **iPhone** (Apple MFi) | USB device. IF0 `ff/f0/00` "iAP Interface"; IF1 `ff/f0/01` "com.dji.common" (External Accessory native transport) | EP1 OUT/IN (iAP2 control), EP3 OUT/IN (DJI data) | MANUAL DMA through the CPU |
| **Android** (AOA) | **USB host**: sends the AOA identity `DJI` / `T600` / `DJI Inspire 1` / `v1.2.3.4` / `www.dji.com` / `12345678` | the phone's accessory bulk endpoints, found at runtime (`0x400|ep`, `0x300|ep`) | MANUAL DMA through the CPU |
| **Plain vendor** `0547:1002` | USB device, IF0 `ff/00/00` | EP2 OUT, EP6 IN | **AUTO** DMA: EP2 → FPGA PIB0, FPGA PIB2 → EP6, no CPU |

- The plain mode is the same VID:PID and EP2/EP6 layout as the air FX2 (`m1500`) and the
  DM36x `usb_68013` driver. I: it is for an HDMI/DaVinci board, which receives the raw FPGA
  stream.
- `DJI`/`T600` are exactly what `app/awto_dji_app/lib/transport/aoa_identity.dart` and DJI GO 4
  match on.

## 2. DMA channels (V, `CyU3PDmaChannelCreate` = `0x40012b84`)

| Site | Type | Producer → consumer | Buffer |
|---|---|---|---|
| `0x40004ab0` | MANUAL_IN | FPGA PIB2 → CPU | 0x800 × 10 |
| `0x40004ad8` | MANUAL_OUT | CPU → FPGA PIB0 | 0x400 × 5 (created, but no write site found: only create/teardown reference it) |
| `0x40005efc` / `0x40003334` | MANUAL_OUT | CPU → phone (iPhone EP3 / Android) | **0x820** = 2048 + header room |
| `0x40005ed4` / `0x400032f8` | MANUAL_IN | phone → CPU | 0x200 × 10 |
| `0x4000eccc` / `0x4000ecf4` | MANUAL_IN/OUT | UART ↔ CPU (LPP sockets 6/3) | 0x80. UART config 0x1C200 = **115200** |
| `0x40005cd0` / `0x40005cfc` | **AUTO** | USB EP2 → PIB0, PIB2 → USB EP6 | plain-vendor mode only |

DJI threads (`tx_thread_create` = `0x400233e8`): `21:USB_DEBUG` (main loop `0x40004474`),
`Gpio`, `ControlSession`, `threadpool`, `uart` (`0x4000e794`) and `usbsocket` (`0x4000f14c`).

## 3. Where DUML is handled (V)

There is one DUML engine: parser `0x40007798` (sync `0x55`, CRC8 seed `0x77`, CRC16 seed
`0x3692`, tables at `0x400102ac`/`0x4001009c`), packet check `0x4000756c` and builder
`0x40007d1c`. It runs on **exactly two inputs**:

1. **UART session** (ctx `0x40033a24`, set up at `0x4000ed4c`).
   - Read `0x4000e764`, write `0x4000e83c`.
   - Packets for **receiver type 13 index 0** that are requests are handled by FX3 itself
     (`0x4000e64c`, `{cmdset, cmdid}` table at `0x40030608`). I: on GL300b/c the FX3 takes over
     the removed ground DM36x's DUML identity.
   - **Everything else goes to `0x4000f830`, the UART→phone aggregator.** It packs whole
     frames into a 2 KB buffer and flushes to the phone with type **`0x5749`**.
2. **Phone session** (ctx `0x40033bcc`, set up at `0x4000f5f0`).
   - The phone side reads raw bytes: the read path copies USB data straight to the parser,
     with no header check.
   - Packets not for the FX3 are written to the **UART** (`0x4000e83c`).
   - **Nothing from the phone goes to the FPGA.**

The **FPGA input is never parsed.** The main loop calls `0x40004bb8`, which reads up to 0x800
bytes from the PIB2 channel and passes them to `0x4000f7d0`. That writes them to the phone with
type **`0x574A`**.

## 4. RC → phone chunk format (V: code and capture)

Android write (`0x400034e8`) and iPhone write (`0x40006384`) frame every USB chunk as:

```
55 CC  <u16 type LE>  <u32 length LE>  <payload>
type 0x5749 (22345) = DUML: whole frames back to back, from the UART
type 0x574A (22346) = video: one FPGA buffer, H.264 Annex-B
```

DJI GO 4's own `dataType==22346` log line (`apk-analysis.md`) is the video case.

**Capture check.** `scripts/re/aoa_chunk_decode.py` on `captures/sessions/2026-10-23/aoa_relay_server.log`:

| | |
|---|---|
| Chunks | **211 video, 11 DUML** |
| CRC-valid DUML frames in DUML chunks | **116** |
| CRC-valid DUML frames inside video chunks | **0** |
| DUML senders | `gnd_rc_lpc1765` (type 14) 73, FC (3) 15, camera (1) 12, gimbal (4) 8, `air_router_stm32f103` m0900 (9) 3, air DM368 (8) 2, types 16/11/6 one each |

So **all** DUML on the phone link, air-side included, arrives through the FX3's UART, and the
FPGA parallel stream is video only.

**This corrects `aoa-live-test-2026-10-23.md`**, which concluded "no demux header exists". The
header is there, and its leading `0x55` was being read as CRC-failing DUML frames.

## 5. "Why USB?" and "is there another path?"

- **USB exists for the phone, and only the phone.** The FPGA cannot talk USB. Phones accept
  only USB accessories (Android AOA with the RC as host; iPhone via MFi iAP2 with the RC as
  device). The FX3 bridges the FPGA's parallel video port and a 115200 UART onto that one USB
  link, and also handles the Apple and Android accessory protocols. Inside the RC, nothing is
  USB-native: video is parallel GPIF and DUML is UART.
- **There is no other path to the phone** on GL300b/c (V for the FX3 side; I that no second
  phone interface exists). Telemetry, control and video all share this one pipe.
- **Uplink commands** go phone → FX3 → UART → (I) `m1400` → ground FPGA → radio → air FPGA →
  m0900 USART3 → destination (`m0900-can-channels.md`). The FX3 never injects DUML into the FPGA.
- **The air side is the mirror image.** There the DM368's H.264 encoder sends USB *into* an
  FX2 because the DM368's convenient high-speed output is USB. I: the FX2 just converts that
  to the FPGA's parallel FIFO (`m0800-dm368-provenance.md` §7).

## 6. Consequences for the app (proposed, not implemented)

The app's AOA transport feeds the raw stream to its DUML framer, which only works by
resyncing past `55 CC` headers and video bytes. A small demuxer would make both reliable:
- strip the 8-byte header;
- route `0x5749` payloads to the DUML framer;
- route `0x574A` payloads to the H.264 decoder.

## 7. USB port ownership and switching, both ends (2026-10-24)

**Ground (V code; board meaning I).** A boot strap on **FX3 GPIO 41** decides who owns the RC's
phone USB port.
- GPIO setup is at `0x40008074`: GPIO 39 and 33 are outputs (33 is toggled every 30 ms by the
  `Gpio` thread), GPIO 41 is an input read once.
- The flag is stored at `0x40031626` and returned by `0x40008288`.
- Only the main loop (`0x400044ac`, `0x400044d8`) and the USB start function (`0x40006534`)
  branch on it.

| GPIO 41 | USB role | Data path | Threads |
|---|---|---|---|
| low | iPhone iAP2 device (descriptors `0x40010440`/`0x400104a0`) or Android AOA host | FPGA video and UART DUML chunked `55 CC` through the CPU (§3–4) | uart, usbsocket, FPGA pump, threadpool, Gpio (init table `0x400103c8`) |
| high | plain device `0547:1002` (descriptors `0x40010520`/`0x40010560`) | **AUTO** EP2→PIB0, PIB2→EP6, no CPU, no DUML, no phone protocol | USB device + Gpio only (`0x40006770`, loop `0x40006bf8`) |

I: high = GL300a or HDMI-board RC. There, the DaVinci (`m1300`) is USB host to the FX3, binding
`0547:1002` with the same `usb_68013` driver as the air DM368, and the DaVinci owns the
external phone port (wiki m1300: "The external USB connector is managed by the DM368 chip").
Low = GL300b/c, the owner's GL300C.

**Air (V strings/scripts in `m0100`; mux part W).** The camera A9 has one USB port that is
switched between an **external** role and the **internal** FX2 bus:
- **External, device role:** `msc: switch USB class to msc`, `mtp: switch USB class to mtp`
  (SD card to a PC over the camera's micro-USB).
- **Internal, host role:**
  - `setusbmode.sh` runs `echo host > /proc/ambarella/uport` and then loads EHCI/OHCI;
  - "Switch Linux usb to host mode" / `usbsw.sh host`;
  - `AmbaIPC_RpcUsbOwnerSwitch` hands the controller between the RTOS (device) and Linux (host);
  - Linux `68013.ko` drives the FX2, used for FX2 firmware load and the UEG upgrade transmit to
    the FPGA.
- **The FX2 bus itself** is switched between the A9 and the DM368 ("connect usb to A9 /
  connect usb to DM368", `DjiMsgStUsbSwitchStatusSet`).
- **Upgrade interlock:** `[DJI_UEG] Please Discon USB Port.`
- `DjiNotice1765SwitchUsb2A9` (1765 = DJI's legacy name for `air_router_stm32f103`) can request the
  switch.
- W: the camera board has two TI TS3USB221A 2:1 USB muxes (`camera-linux-console-access.md`).
  I: one selects A9 ⇄ {external micro-USB, internal bus}, the other selects FX2 ⇄ {A9, DM368}.

**So yes: the internal USB data paths do meet external ports, through switches.** In the
aircraft, the camera's micro-USB shares the A9's port with the internal FX2 bus. In the RC, the
phone port is either the FX3's own (GL300b/c) or the DaVinci's (GL300a/HDMI). Not established:
- the exact mux wiring and GPIOs on the camera board (needs a board trace or the
  `MCCTRL_SetUsbMode` disassembly, issue #25);
- whether the RC's other USB/micro-USB port (if fitted) reaches anything but the LPC1765 (U).

## 8. Open

- The UART peer is **I** (m1400, by sender type 14 and the existing docs); a board trace or a
  logic probe on the FX3 UART pins would make it V. Narrowed which m1400 UART instance it's
  most likely to be: m1400 has 4 UARTs, and UART3's own init code targets baud-rate constant
  `0x1c200` = 115200 — matching this link's known signature exactly — while UART2 (the other
  candidate considered, see `control-plane-re.md`) targets `0x3e800` = 256000, ruling it out.
  Still I, not V: no pin-level/board confirmation that UART3's physical TX/RX pins are the ones
  wired to FX3, only that it's the one m1400 UART whose configured baud rate matches.
- Re-check `m1601` 02.00.0006 (operator's C1 V01.06.0000).
- Not analysed (CLAUDE.md, no keys): a 68-byte record, obfuscated with +0x55 per byte and
  CRC16-protected, read and written via `0x4000e1dc`/`0x4000e298` (`0x40003ec8`). I: MFi
  auth/config storage.
