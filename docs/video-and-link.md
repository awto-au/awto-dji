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
  Wi-Fi instead). It's a proprietary **OFDM** downlink, not Wi-Fi.
- **RF band: 2.4 GHz only (2.400–2.483 GHz).** The HD video downlink **and** the RC
  control uplink share this one band on the P3 Pro/Advanced — they are multiplexed on
  the same link, not on separate frequencies. There is **no 5.8 GHz** (that split
  arrived with the Phantom 4 / Inspire). Consequence: 2.4 GHz interference or range loss
  degrades picture and stick response together. GPS (~1.575 GHz, receive-only) and the
  compass/IMU are not part of this link.
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

### Video formats (from the real firmware)

Confirmed by unpacking the actual P3 Pro firmware (`P3X_FW_V01.11.0020`) and reading
the camera module (`m0100`) strings — so this is what the camera genuinely supports,
not marketing copy:

**Recorded to the SD card (high quality):**
- Resolutions: **DCI 4K 4096×2160**, **UHD 4K 3840×2160**, 2.7K, **1920×1080**,
  **1280×720** (strings `4096x2160`, `3840x2160`, `1920x1080`, `1280x720`, `60fps`).
- Codec: **H.264 (AVC)**; the hardware also supports **MJPEG**
  (`video_type … none(0)/h264(1)/mjpeg(2)`).
- Containers: **.MOV** and **.MP4**.
- Photo: **JPEG** and **DNG** raw (`.DNG` strings present).

**Transmitted to the phone (live downlink, transcoded down):**
- `dji sto video [set][resolution][val]` → **0: 720P, 1: WVGA, 2: WQVGA**, H.264.
  So the live feed is a separate, lower-res **720p** H.264 transcode — the 4K never
  goes over the air, only to the card.

### Control channel for the video chain (DUML)

The transcoders and radio MCUs are themselves DUML devices, with their own command
sets seen in the dissector:

- `cmd_set` **0x08 — DM36x** transcoder control: `DM36x Gnd Ctrl Info Send/Recv`,
  `DM36x UAV Ctrl Info Send/Recv` (ground↔air control of the video transcode).
- HD-link device types: `DM36x transcoder air/gnd side`, `HD transmission MCU
  air/gnd side`, `HD transmission FPGA air/gnd side`.
- Camera command set has `SDK Ctrl Camera Start/Stop Video Ctrl` (0x21/0x22) to
  start/stop the stream.

## What is Lightbridge

Lightbridge is **DJI's proprietary long-range digital HD transmission system** — the
thing that carries the live video down and the control up. The P3 Pro uses
**Lightbridge 2**.

- **What it does:** a one-way **HD video downlink** plus a **bidirectional control +
  telemetry** link, all on the single 2.4 GHz OFDM radio. The camera's H.264 stream is
  modulated by the air-side FPGA and MCU, sent over the air, and demodulated on the
  ground.
- **Not Wi-Fi:** it's a custom OFDM PHY with forward error correction and adaptive
  bitrate/coding (it drops video quality as the link degrades to keep latency low and
  the link alive), rather than 802.11. That's what buys the range (~several km) and the
  low (~220 ms) latency versus the Wi-Fi-based P3 Standard.
- **The hardware that implements it** (from the firmware module map): air-side **FPGA**
  (`m1900`) + **STM32F103** MCU (`m0900`); ground-side FPGA + **LPC1765** MCU; and the
  **Cypress FX2LP** USB bridge to the phone. The DM368/DM365 DaVinci chips encode/
  transcode the video that rides the link.
- **Lineage:** Lightbridge (2014) → Lightbridge 2 (Inspire 1, Phantom 3) → superseded by
  **OcuSync** from the Phantom 4 Pro / Mavic onward. So the P3 is the Lightbridge-2
  generation; OcuSync is a different, later system.

## Which chip feeds the FPGA (data flow)

There is an FPGA at each end; what feeds it differs by direction:

- **Aircraft (TX):** Ambarella A9SE camera → **TI DaVinci DM368** H.264 encoder (`m0800`)
  → **air FPGA** (`m1900`: OFDM + scrambler) → **AD9363** transceiver → PA → antenna.
  The **DM368 sends the video payload into the FPGA**; the A3 FC / center board feed
  telemetry in over UART/CAN.
- **Remote (RX):** antenna → LNA → **AD9363** → **ground FPGA** (Cyclone V `5CEFA4`) →
  **Cypress FX2LP (CY7C68013A)** → USB to phone. Here the **AD9363 feeds the FPGA** the
  received samples, and the FPGA hands recovered H.264 to the FX2LP. The **STM32F103**
  (`m0900`) only sends *configuration* (AD9363 over SPI, FPGA config/reset) — not payload.

Summary: **DM368 → FPGA** (air), **AD9363 → FPGA → FX2LP** (ground).

## The DaVinci chipsets

**TI DaVinci** is Texas Instruments' DMxxx video-SoC family — an ARM926 CPU plus a
hardware **H.264 video coprocessor** (HDVICP/MJCP), built for IP cameras/camcorders. DJI
uses two across the link:

- **DM368** — `m0800`, "video encoder in air": compresses the camera feed to H.264 for
  transmission.
- **DM365** — `m1300`, "video decoder" on the ground/RC side.

They bracket the radio: DM368 encodes on the aircraft, the Lightbridge link carries it,
and the live stream is decoded on the phone (`libdjivideo`); the RC's DM365 is the
ground-side DaVinci.

## Relevance to the app

For a direct app, the USB-AOA link from the phone carries **both** the DUML telemetry we
decode **and** the H.264 video, multiplexed. Reading telemetry needs only the DUML side.
Showing live video additionally needs: de-multiplexing the video substream from the AOA
container, then an H.264 decoder (the platform `MediaCodec` on Android can replace
`libdjivideo`). Video is therefore a separable, later milestone — telemetry and control
do not depend on it.

## OSD is client-rendered, not burned at the aircraft

The aircraft sends **clean H.264 video** and **telemetry as separate data**; the OSD
overlay is composited at the **ground/remote/app**, not at the bird. Evidence is in this
repo: the `OSD General` push (`cmd_set 0x03 / cmd_id 0x43`) that `app/packages/duml`
decodes into lat/lon/height/attitude is a *structured telemetry* message — if the overlay
were burned into pixels on the aircraft there would be no reason to also send those numbers
as data. The DJI GO app draws vector OSD from it; the Lightbridge ground unit's HDMI/SDI
"built-in OSD" likewise composites at the ground box from received telemetry.

### Where telemetry meets video (the mux point)

They are multiplexed onto the downlink, never pixel-composited:

- **Air:** FC (`m0306`) emits telemetry DUML; camera (A9SE `m0100`) emits H.264; the air
  video encoder (DM368 `m0800`) + air radio MCU (`m0900`) + air FPGA (`m1900`) multiplex
  **video + telemetry + control as separate logical channels** into the OFDM frames.
- **Ground:** ground FPGA (`m2000/01/02`) demuxes -> video to the DM365 decoder (`m1300`)
  -> FX2LP USB (`m1600`) -> app; telemetry DUML -> ground MCU (`m1400`) -> app.
- **Client:** app/ground recombine them visually (decoded video + telemetry-drawn OSD).

(Module roles are verified from the firmware set; the exact encapsulation — a separate link
channel vs a data PID — is inference, confirmable from one capture.)

Consequence for interop: telemetry arrives as **clean structured data** (what
`tool/telemetry_scan.dart` parses) and the video arrives with **no overlay to strip**.

### Public captures

Protocol knowledge is public; ready-made P3 link captures are not. DUML is documented/
dissected (`samuelsadok/dji_protocol`, `o-gs/dji-firmware-tools`), but no shared P3 usbmon
pcap or SDR capture of the video link was found — generate your own (usbmon on the ground
USB, or the MCU UART). Caveat: the standalone **Lightbridge 2** product markets an optional
encryption toggle; our P3 firmware analysis found no payload cipher on the integrated link —
keep the two separate.

### How to confirm it's data, not burned OSD (bOSD) — no capture needed

Converging evidence, cheapest first:

1. **Degradation test (observable in any P3 flight video).** If the OSD were burned into the
   H.264, it would macroblock *with* the video when the link weakens. It does not — the video
   pixelates while the OSD stays crisp (redrawn locally from the last telemetry packet; the
   telemetry channel is lower-rate and better protected, so it often survives when video is
   breaking up). Sharp OSD over blocky video = separately transmitted data. Any weak-signal
   moment in a public P3 YouTube flight shows this.
2. **Flight control / geofence need real numbers.** No-fly enforcement runs on the aircraft
   from its own onboard GPS (independent of the downlink), and the app's map/warnings/zone
   dialogs need real position too. The data demonstrably exists as numbers. (This is about
   where the data lives, not about altering enforcement.)
3. **`.SRT` telemetry files.** DJI recordings ship a `.SRT` subtitle sidecar with per-frame
   GPS, altitude/height, etc. as plain text — telemetry persisted as structured data. If it
   were only burned pixels there would be no `.SRT`.
4. **Decodable DUML.** `app/packages/duml` already turns `OSD General` (0x03/0x43) into
   height/velocity/attitude numbers — the on-wire message is structured data.

Burned OSD *does* exist in the system, but only as a **ground-side output option** (the
Lightbridge ground unit can composite the overlay onto its HDMI/SDI out for monitors that
can't draw it) — generated at the ground from the received data, never sent from the bird.
