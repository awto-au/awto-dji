# What talks to the phone, and the video downlink

## The chip that talks to the phone

The phone plugs into the **remote controller**, not the aircraft, so the processor that
talks to it is on the **ground side**. From the P3 firmware module table
(`dji_xv4_fwcon.py`), the RC's USB interface is a dedicated controller:

| Module | Role |
|---|---|
| `TX68013` | transmitter USB — "IG810 LB2 **68013** TX" |
| `RX68013` | receiver USB — "IG810 LB2 **68013** RX ground" |
| `RXCY2014` | receiver USB — "IG810 LB2 **CY2014** RX ground" |

`68013` is the **Cypress EZ-USB FX2LP (CY7C68013A)** — a standard USB 2.0 interface
chip. This is what the phone enumerates against over AOA; it moves the combined
downlink (video + telemetry/DUML) between the RC and the phone. Behind it sit the
ground **DaVinci DM365** (video transcoder) and the Lightbridge ground MCU
(**LPC1765**) + ground FPGA that run the radio link.

So the data path to the phone is:

```
aircraft                                     remote controller                phone
Ambarella A9SE ─H.264→ DM368 enc ─→ air FPGA/MCU ))) 2.4GHz ((( gnd FPGA/MCU ─→ DM365 ─→ FX2LP USB ─→ libdjivideo (decode)
 (camera SoC)         (DaVinci)    (Lightbridge radio)         (Lightbridge)  (transcode) (CY7C68013A)   (on the phone)
```

### While we're here — two corrections to earlier notes
- The **flight controller is DJI's "A3"** main controller (module 3: `MCAPP`/`MCLDR`
  "main controller 'A3'"), i.e. what `m0306` is. More specific than "an STM32".
- The **camera has a Xilinx Zynq 7020** (`ZQ7020`) alongside the Ambarella A9SE.

## The video protocol

- **Link:** DJI **Lightbridge** (full Lightbridge on the Pro/Advanced; the Standard uses
  Wi-Fi instead). It's a proprietary **OFDM 2.4 GHz** downlink, not Wi-Fi.
- **Codec / resolution:** **H.264 (AVC)**, live view **720p @ 30 fps** (DJI's spec,
  "depending on conditions and device"). The 4K/2.7K recording is stored on the
  camera's SD card; only the lower-res live stream is transmitted.
- **Latency:** DJI-reported **~220 ms** at close range; real-world rises with distance
  (users report seconds at long range).
- **Where it's decoded:** on the **phone**. The encoded stream is carried over the USB
  link and decoded by `libdjivideo.so` in the app (which is why that lib is a dependency
  of `libSDKRelativeJNI.so`). The RC does not render it; it relays it.
- **Framing to the phone:** a DJI-proprietary container over the USB-AOA byte stream,
  multiplexing H.264 video with the DUML telemetry/command traffic. On the SDK side this
  surfaces through `UsbAccessoryService` (`putVideoBuffer`, `toTransVideoData`,
  `onGetBody(mode=dual)` — the "dual" being video + data on one link).

### Control channel for the video chain (DUML)

The transcoders and radio MCUs are themselves DUML devices, with their own command
sets seen in the dissector:

- `cmd_set` **0x08 — DM36x** transcoder control: `DM36x Gnd Ctrl Info Send/Recv`,
  `DM36x UAV Ctrl Info Send/Recv` (ground↔air control of the video transcode).
- HD-link device types: `DM36x transcoder air/gnd side`, `HD transmission MCU
  air/gnd side`, `HD transmission FPGA air/gnd side`.
- Camera command set has `SDK Ctrl Camera Start/Stop Video Ctrl` (0x21/0x22) to
  start/stop the stream.

## Relevance to the app

For a direct app, the USB-AOA link from the phone carries **both** the DUML telemetry we
decode **and** the H.264 video, multiplexed. Reading telemetry needs only the DUML side.
Showing live video additionally needs: de-multiplexing the video substream from the AOA
container, then an H.264 decoder (the platform `MediaCodec` on Android can replace
`libdjivideo`). Video is therefore a separable, later milestone — telemetry and control
do not depend on it.
