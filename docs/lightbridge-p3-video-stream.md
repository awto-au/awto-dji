# DJI Phantom 3 (Lightbridge) video + telemetry stream: format at each hop

Tags: **V** = shown in code/capture (source named), **I** = inferred, **U** = unknown.
Sources (awto-dji, read-only): `docs/video-and-link.md`, `ground-fx3-m1601.md`, `m0800-dm368-provenance.md`, `dataflow.md`, `air-id-and-stream-survey.md`, `air-router-deep-dive.md` §6a, `lightbridge-phy-measured.md`, `pc-video-preview.md`, `scripts/re/aoa_chunk_decode.py`; captures `capture_local/live-camera.h264` (30 MB, 2026-10-24), `captures/sessions/2026-10-23/aoa_relay_server.log`, `capture_local/aoa_relay_server-2026-10-26.log` (first 20 MB of RAWUDP bytes).

## 0. One-line model
- Air: A9 camera -> DM365/368 `encode_usb` -> raw H.264 Annex-B, **no framing** -> USB bulk EP2 -> FX2 slave FIFO -> air FPGA (mux with DUML + control) -> OFDM -> AD9363.
- Ground: AD9363 -> ground FPGA (m2001, EP4CGX150) -> raw H.264 Annex-B bytes, **no framing, PKTEND after each AUD** -> FX3 PIB socket 2 -> FX3 wraps `55 CC 4A 57 <u32 len>` -> phone.
- DUML never rides the FPGA->FX3 video port: DUML = FX3 UART (115200) -> `55 CC 49 57` chunks (V, 116 CRC-valid DUML frames in DUML chunks, 0 inside video chunks).

## 1. Layers, per hop (what is added / removed)

| # | Hop | Format on the wire | Added | Removed | Tag |
|---|---|---|---|---|---|
| L0 | air encoder (DM365 `encode_usb`, TI DVSDK 4.02 H264VENC) | H.264 Annex-B elementary stream, slice-level callback `getEncodedSliceProvideSpace`; one `libusb_Send(slice,len,&sent,100)` per slice/NAL | start codes, SPS/PPS, AUD, slices (TI codec output) | nothing | V (`m0800-dm368-provenance.md` §7) |
| L1 | DM365 -> FX2 | `usb_68013.ko` ioctl 0x1001 -> URB bulk OUT EP2, data copied to URB offset 0 | nothing (no header, length, CRC, trailer) | nothing | V |
| L2 | FX2 m1500 (CY7C68013A) | `IFCONFIG=0x03` slave FIFO ext clock, EP2CFG 0xA0 (bulk OUT 512 B) EP2FIFOCFG 0x10 (**AUTOOUT**); 8051 never touches payload | nothing | USB packetisation (512 B packets) | V (full disassembly, #31) |
| L3 | air FPGA m1900 (Cyclone V, bitstream not decoded) | FIFO master reads 8-bit; muxes video + DUML (from m0900 USART3 257143 baud) + control into the OFDM payload; scrambler | **U**: framing/mux headers, FEC, scrambling, CRC | | I (no decode, #3) |
| L4 | RF | OFDM 1024-FFT @ 11.2 MS/s, 10937.5 Hz spacing, CP 1/8, 864 used carriers (768 data + 96 pilots), symbol 102.857 us, burst every 14.000 ms, video burst 9.98 ms ~97 symbols, second narrowband link 2.2 ms between video bursts | | | V on Matrice 100 (proxy), I for P3 |
| L5 | ground FPGA m2001 (EP4CGX150) | demod -> (descramble, FEC) -> **byte stream = L0 stream** -> 8-bit GPIF to FX3 | PKTEND short packet after each AUD (V from capture, section 3); strobes SLWR#/PKTEND# | all radio framing, FEC, mux, DUML (DUML goes to MCU m1400 -> FX3 UART, I) | V (stream), I (logic) |
| L6 | FX3 m1601 (PIB socket 2 -> CPU -> USB) | `55 CC <u16 type LE> <u32 len LE> <payload>`; type 0x574A video, 0x5749 DUML; payload = one FPGA DMA buffer (<= 0x800 B) | 8-byte envelope per DMA buffer | | V |
| L7 | phone | AOA bulk IN; app strips envelope, concatenates type 0x574A payloads -> H.264 decoder; type 0x5749 -> DUML framer | | envelope | V |

## 2. Field tables

### 2.1 FX3 -> phone envelope (V: FX3 firmware 0x400034e8/0x40006384, 211 + 9141 video chunks in captures)
| off | width | field | value |
|---|---|---|---|
| 0 | 2 | magic | `55 CC` |
| 2 | 2 LE | type | 0x574A (22346) video; 0x5749 (22345) DUML; 0x574B-0x574D parsed by GO4, unseen on P3 |
| 4 | 4 LE | length | payload bytes; video: 0x0800 for a full buffer, shorter at PKTEND (1..2047 seen) |
| 8 | n | payload | video: raw bytes of the FPGA buffer; DUML: whole frames back to back |
- No CRC, no sequence number in the envelope. FX3 DMA: PIB2->CPU MANUAL_IN 0x800 x 10; CPU->phone MANUAL_OUT 0x820 (2048 + 8 header, +room); phone->CPU 0x200 x 10; UART LPP 0x80 buffers.
- FX3 never parses the FPGA stream (`0x40004bb8` reads up to 0x800 B -> `0x4000f7d0` -> type 0x574A). Chunk boundaries are therefore set by the FPGA: PKTEND or a full 2048-byte DMA buffer.
- Open-source (MIT) parser of the same envelope for the N3 goggles, 1Basco/openfpvcast `LogicLink.kt`: magic 55 CC, port u16 LE, **payload length u16 LE**, 2 reserved zero bytes, 8-byte header; port 0x574A = H.264 Annex-B (same constants). For len < 65536 identical to our u32 form.
- #64: ~13% of bytes in the 2026-10-26 raw stream (2.58 MB of 20 MB) sit outside any envelope (bare, CRC-valid DUML frames, mostly sender 0x0E/OSD); not video.

### 2.2 H.264 stream (V: live-camera.h264, 14,775 NALs; ffprobe)
- Profile High (0x64), level 5.0 (0x32), 1280x720, yuvj420p (full range), 25 fps (VUI). 4-byte start codes (14,771 of 14,775 start codes `00 00 00 01`).
- Per access unit (AU): AUD (`00 00 00 01 09 10`, 6 bytes) first; 1613 AUDs; SPS (38 B incl. start code region) + PPS (`68 ee 3c b0`, 4 B) repeated 26 times = every ~62 AUs (~2.5 s); then slices.
- Slices: NAL type 1 only (13,105); **IDR (type 5): 0 in 31 MB**; no SEI (type 6). All slice_type = 5 (P). Slice size by `first_mb_in_slice`: boundaries in multiples of 400 MB (5 MB-rows) or 480 MB (6 rows); 5-12 slices per AU (median 8). AU bytes: avg 19.4 KB, max 70.9 KB (avg ~3.9 Mbit/s at 25 fps, I).
- The SPS/PPS AU's first slice is 17-19 KB (intra-coded content in a type-1 NAL, header byte 0x61), the following slices of that AU are 17-45 B each. Decoding with `ffmpeg -flags +output_corrupt -err_detect ignore_err` from the first SPS gives a real picture whose rows fill in over later AUs (gradual refresh); plain `ffmpeg` fails ("non-existing PPS", "top/left block unavailable").
- Marker: chunk tails. 958 short video chunks (of 9141) in 20 MB of 2026-10-26 bytes: **950 end exactly with `00 00 00 01 09 10`** (AUD), 2 of 8183 full chunks do. The FPGA asserts PKTEND right after the AUD's second byte. 983 of 9141 chunks start with a start code.

### 2.3 DUML (V: FX3 parser 0x40007798; aoa_chunk_decode.py)
| off | width | field |
|---|---|---|
| 0 | 1 | SOF `0x55` |
| 1-2 | 10 bit len (u16 LE & 0x3FF) + 2 bit version | total frame length (min 13) |
| 3 | 1 | CRC8 over bytes 0..2: poly 0x31 reflected (0x8C), seed 0x77 |
| 4 | 1 | sender (type low 5 bits, index high 3) |
| 5 | 1 | receiver |
| 6-7 | 2 LE | sequence |
| 8 | 1 | cmd type |
| 9 | 1 | cmd set |
| 10 | 1 | cmd id |
| 11.. | n | payload |
| len-2 | 2 LE | CRC16 over bytes 0..len-3: poly 0x1021 reflected (0x8408), seed 0x3692 |
- Ground UART FX3 <-> peer (I: m1400) 115200 8N1; aggregator packs whole frames in a 2 KB buffer (type 0x5749). Air: DM365 `ttyS1` 115200 DUML; m0900 USART3 257143, USART1 256228 (V).
- Air control path inside m0900 (V code, I meaning): FPGA SPI reg 0xE9 poll, 0x38-byte payload, XOR with 8-byte key (zero in RAM), two-stage chained checksum seed 0x55AA, 28-byte (0x1C) chunk pushed to ring -> USART1 relay.

## 3. Telemetry multiplexing and rates
- Video and DUML are separate physical inputs of the FX3 (parallel GPIF vs UART); the FX3 interleaves them chunk by chunk. Air-side mux point (video + DUML into OFDM) is the air FPGA (I, by elimination, m0800 §7); ground demux is the ground FPGA/m1400 (I).
- Rates: H.264 ~3.9 Mbit/s average (I); FX3 chunk 2056 B on the USB; radio frame 14 ms with 9.98 ms burst; OFDM symbol 102.857 us.
- Idle fill: none seen in the video stream (chunks are contiguous Annex-B; zero runs are start-code padding only).

## 4. Netlist-checkable constants / structures, with image results (m2001, nl: 89,282 LUT / 36,993 FF / 542 M9K (8 populated) / 87 MAC)
Tool: `scripts/cycloneiv_clean_const_search.py` in the pluribus repo (netlist-constant search).

| Constant / structure | Expected in a packetiser | Image result |
|---|---|---|
| `55 CC`, `4A 57`, `49 57`, 8-byte header, `00 08 00 00` (FX3-side, written by FX3 CPU) | none in FPGA (FX3 adds it) | 0 comparators, 0 M9K words/sequences outside chance (negative as expected) |
| AUD `00 00 00 01 09 10`, NAL type 0x09 | detector for PKTEND | 16-literal compare: 0; **8-literal compare of the DQ output byte register with 2 ones (value class of 0x09), plus 4/5/7-literal zero detects of the same byte register** (`lc_21_50_4`, `lc_21_50_15`, `lc_22_47_15`, `lc_21_50_11`) -> LUT cone in the 16-LE LAB (21,50) -> state FFs ff_25_83_3/6 -> reaches pad F896 G10 = F672 D10 (write-side strobe, SLWR#/PKTEND# class) within 3-4 FF hops: **I** (bit order of DQ not known, so 0x09 vs another 2-ones byte not separated) |
| zero-run / start-code scan (`00 00 00 01`) | zero detects on the byte register | present as above (zero detects feed the byte-class FSM); no 32-bit comparator exists: **start-code scan is a byte-serial FSM, not a 32-bit compare** (I) |
| SPS/PPS/slice NAL bytes 0x67/0x68/0x61/0x65 | only if the FPGA classifies NALs | 8-literal compares with right popcount: 1/3/3/7, all but the AUD one on counters or unrelated (not on the DQ byte register): treat as chance (no evidence) |
| DUML SOF 0x55, seeds 0x77/0x3692 | none expected in FPGA | 8-bit CRC (poly 0x31 and 0x07): **0** LFSR/parallel groups; no CRC table in any M9K; 1 serial CRC-16 (see CRC row) |
| CRC-16-CCITT (poly 0x1021 = DUML CRC16 polynomial) | possible radio-payload CRC | **1 bit-serial CRC-16 group** (16 FF, Galois, 1 serial input FF), cell (19-20,76), main clock, enable lc_21_76_7 <- lc_24_58_8 (cell near the strobe FSM), serial input ff_21_83_9, no constant seed (aclr only: not the DUML 0x3692 seed form, I), no pad within 5 FF hops |
| CRC-8 poly 0x31/0x07, CRC-32 0x04C11DB7 | | **0 / 0** (negative) |
| Scrambler | radio-side | 2 PRBS15 LFSR x^15+x^14+1 (802.16/DVB randomiser form), 2 PRBS11 (x^11+x^2+1), all autonomous, main clock; whitening consumers 1 + 1 (counts only; the detector's per-design list) |
| Chunk size 2048 (0x800) / 2056 / 2080 | terminal count of a byte counter | 12-bit counter `0x800` partial decode exists but is the top-bit decode of a 12-bit **2304-period** counter (cell 34,58); 16-bit counters at (27,90) and (51,4) with value 0x820 are the pair-bit decodes of two identical sequencers (not a size). No 11-bit natural-wrap (2048) counter in the cone of any FX3 strobe pad. **Negative: no 2 KB counter in the FX3 write path; 2048 is the FX3 buffer fill (FLAG/ready) + PKTEND on AUD.** |
| Other modulo counters (sclr = full compare of own bits, 16 total) | | periods 10,000,000 (24 b), 100,000 (20 b), 62,500 (2 x 16 b), **2,304 (12 b), 768 (11 b), 384, 256, 192, 96, 48, 30, 29, 24, 23, 65**; main clock. 768 = OFDM data carriers, 96 = pilots: PHY symbol sequencers (I) |
| M9K ROM headers | | 193 blocks emitted as unmodelled INIT; **8 non-zero**: 5 are ROM/microcode, none contain the header/NAL/DUML constants beyond chance; the B14-domain pair (36-bit 137 non-zero words incl. a `0123 89AB FEDC 7654` pattern block and 8 random 20-bit words; 28-bit 10 words) is a sequencer table (SPI/AD9363 or BIST), not a packet header |

## 5. FX3 output side (FPGA drives, FX3 GPIF sync slave)
- FX3 (V): GPIF_CONFIG 0x80000380 sync, FPGA drives clock; GPIF_BUS_CONFIG 0x1003 (8-bit DQ + OE); thread from A1:A0; video = PIB socket 2 (FPGA -> FX3); DMA buffer 0x800; CTL4/5 flags outputs of the FX3 (ready/partial).
- FPGA FSM (local draft README): S1 lc_18_53_11, S2 lc_24_56_12, shared DQ OE lc_24_56_7 (drops in S1&S2), strobes F672 D12, B9 (read-side, both fall in S1&S2), A12/D10 (write side: SLWR#, PKTEND#), DQ out = per-bit LUT mux of two byte registers (ff_9_41_x and ff_21/22_x) gated by S1/S2.
- Stream behaviour (V, capture): packets of 2048 B back-to-back, a short packet ending exactly at AUD. So PKTEND is data-dependent (AUD in the byte stream), not a fixed byte count; consistent with the byte-class FSM at (21,50) reaching D10.
- B14-clock domain (218 FF, 2 wide M9K): sequencer table, not in the stream path (no byte compare in it).

## 6. What the ground FPGA's packet-level logic therefore is
- Input: recovered radio payload -> **byte stream already equal to H.264 Annex-B** (no radio framing visible at the FX3 port): FPGA must strip/finish all link framing, FEC, scrambling and demux DUML to the m1400 path.
- Packetiser: byte FIFO (M9K) -> DQ register -> GPIF writes while the FX3 ready flag allows; FX3 closes full 2048-B buffers by itself; **FPGA asserts PKTEND after the AUD (`00 00 00 01 09 10`)** => start-code/NAL-type scan = zero-run counter + NAL-type compare (I; the byte-class FSM in LAB (21,50)).
- No in-FPGA CRC for video (DUML-style CRC8/16/32 absent except one serial CRC16, purpose U); no sequence counters in the stream; telemetry multiplexing in the FPGA = rejecting DUML bytes from the video path.

## 7. Open-source app vs ours (U: not identified in awto-dji docs/issues/chats)
- Docs only record: Dan parked the app's own decoder (issue #67 `VideoShim` crash, branch fix/video-decoder-lifecycle-67 on hold, 2026-10-27) "pending an open-source Android app alternative". The app's name is not written anywhere (searched docs, chats, issues, HANDOVER, HISTORY).
- Public candidates checked: `1Basco/openfpvcast` (MIT, goggles N3 only, Capacitor/Android; `LogicLink.kt`, `VideoDecoder.kt`), `fpvout/DigiView-Android` (not read), `levv-lab/DjiStreamReader` (not read). openfpvcast shares the envelope and constants (0x574A video, 0x5749 DUML) but its `VideoDecoder.kt` waits for an IDR before feeding slices, so it would never display this P3 stream (0 IDR in 31 MB).
- Differences relevant to our app (V from our captures): the P3 stream has SPS/PPS every ~62 AUs but never an IDR; it refreshes gradually. Our issue #26 ("zero IDR -> zero frames") is consistent: any decoder/shim that waits for NAL type 5 (or ffmpeg without `-flags +output_corrupt`) never outputs. Our envelope parser and AnnexB extraction decode the same bytes as ffmpeg (picture appears when errors are tolerated). Fix direction: start decoding at SPS/PPS + first slice, accept non-IDR refresh, MediaCodec with tolerant start (I). Not verified on the phone.
- If Dan names the app, read its repo and compare `isKeyFrame`/IDR gating, slice reassembly (AU = AUD-delimited, not slice-delimited) and EOS handling.
