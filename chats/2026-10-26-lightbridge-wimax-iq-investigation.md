# Chat research record - WiMAX, DJI Lightbridge and SDR IQ analysis

**Date:** 2026-10-26 (covers investigation discussed over 24-26 October and preceding messages)  
**Repository:** [awto-au/awto-dji](https://github.com/awto-au/awto-dji)  
**Relevant work:** [issue #61](https://github.com/awto-au/awto-dji/issues/61), [PR #62](https://github.com/awto-au/awto-dji/pull/62), [issue #71](https://github.com/awto-au/awto-dji/issues/71)  
**Reference report:** [WiMAX/Lightbridge history and background](../docs/lightbridge-wimax-history.md)

> **Integrity / completeness:** This is a comprehensive *research conversation reconstruction* of the messages and technical details accessible to the assistant as of this commit, including original user wording when available. **It is not a verbatim export of every assistant and tool message.** The repository integration does not expose a full downloadable transcript of this ChatGPT session; inaccessible/unavailable turns are not fabricated. For a byte-for-byte full transcript, export the ChatGPT conversation separately and add it to \`chats/\`.

## Research motivation

The central idea is to receive the Phantom 3 Professional Lightbridge signal using an old Intel WiMAX chipset - ideally extracting demodulated/FEC-decoded bits and implementing DJI-specific descrambling, framing and video extraction on a Linux host. The user repeatedly asked that conclusions be grounded in original firmware, hardware and captures rather than assumptions from marketing frequency ranges. An alternative is a wideband SDR receiver and a software PHY.

## 1. Intel chipset history and firmware reverse engineering

User questions in the preceding discussion included:
- "The Intel surly supports the frequencies we need"
- "Ok and check the firmware"
- "What cpU is used"
- "Entrphy"
- "Public documentation other Intel chips used for wifi itr womax"
- "Keep going"

Key discoveries made through real GitHub Actions jobs:

- Authentic \`i6050-fw-usb-1.5.sbcf\` was obtained from upstream Linux firmware in GitHub Actions. File length **1,531,932 bytes**; SHA256 \`bd38e7dc36deebd0ba3601ea8c5dc70dcd11a99b940137811e99387d5f249296\`.
- Historical \`i2400m-fw-usb-1.5.sbcf\` is **1,334,532 bytes**, SHA256 \`1260178fd15f356f347a34f7a7e542ad2128258bedef5b4f711cb24c06d4bece\`.
- Measured whole-file Shannon entropy: **i6050 6.26705**, **i2400m 6.72747 bits/byte**. These are heterogeneous, structured images, not uniformly encrypted ciphertext.
- Actual **ARM Thumb** instruction sequence identified near \`i6050\` file offset \`0x11f624\`, loaded \`0xea5db0\`; comparison and branch instructions. Intel WiFi's publicly documented ARC/ARCompact implementations do not settle the CPU of this different WiMAX firmware. A larger valid control-flow disassembly is still desirable.
- A contiguous table of little-endian kHz frequency constants near file offset \`0x11f654\`, loaded \`0xea5de0\`, includes **2300000, 2350000, 2400000, 2450000, 2496000, 2550000, 2600000, 2650000, 2700000**. Its relation to allowed ranges, RF configurations or rejection thresholds remains unconfirmed.
- Linux host/userland code can express arbitrary scan-frequency requests; a 2450 MHz literal appearing in the image **does not prove analog 2.45 GHz hardware operation**, regulatory permission, or modem acceptance.

Actions/jobs:
- [Initial firmware scan](https://github.com/awto-au/awto-dji/actions/runs/40198458411)
- [Entropy measurements](https://github.com/awto-au/awto-dji/actions/runs/40202154397)
- [Deep frequency contexts](https://github.com/awto-au/awto-dji/actions/runs/40202327160)
- [Signature investigation](https://github.com/awto-au/awto-dji/actions/runs/40203131304)

Scripts committed on \`research/intel-wimax-band-inspection\`:
- \`scripts/re/intel_wimax_band_scan.py\`
- \`scripts/re/intel_wimax_entropy.py\`
- \`scripts/re/intel_wimax_deep.py\`
- \`scripts/re/intel_wimax_signature.py\`
- \`scripts/re/intel_wimax_monitor_filter.py\`
- \`scripts/re/lightbridge_iq_probe.py\`

## 2. Intel firmware readability and signed boot

User: **"Is the firmware readable could it be modified even slightly to suit ligjtbridge"**  
User: **"Keep reversing it and look at how Intel signs FromWare if that binyage"**

Findings:
- The BCF/SBCF container is parseable, and code in the frequency neighbourhood is recognisable Thumb. A read-only offline patch is technically trivial; getting modified code to execute is not.
- Linux \`drivers/net/wimax/i2400m/fw.c\` handles *signed* and *unsigned* boot via distinct paths. On a signed boot, it uploads original image commands then finalises with a \`SIGNED_JUMP\` and cryptographic signature. Linux userspace does **not** verify signature; the modem's boot environment decides.
- The image contains signature-related header fields and key/exponent-sized fields; exact RSA signature digest coverage and enforcement on a real production Intel 6250 remained unproven in the available record. Do **not** imply that a signed Intel image can be patched without satisfying device boot enforcement.
- The embedded executable likely performs classifications around band thresholds, but the frequency table's purpose remains open.
- Even a permissive tuning policy does not prove matching PHY, analog filters, calibration, baseband or media streams.

[Patch feasibility report](../docs/intel-wimax-firmware-patch-feasibility.md)

## 3. Can Intel perform the PHY, with our own descrambling?

User: **"Does it can we take days and desvrmble our sepves"**  
User: **"Ok bits see what the fish layer can do"** (interpreted as *PHY layer*)

Findings from published \`ago/wimax-ns\` code and the Linux driver:
- Linux \`i2400m\` RX path has \`I2400M_PT_DATA\`, \`I2400M_PT_CTRL\`, \`I2400M_PT_TRACE\` and \`I2400M_PT_EDATA\`. It forwards diagnostic trace messages to userspace, not indiscriminate unrecognised over-the-air bits.
- Original Intel production interface defines \`GET_PHY_RX_SYNC_STATUS\`, \`GET_PHY_RXIQ_VALUES\`, \`START_RXIQ_TEST\`.
- Intel diagnostic TLVs include \`MONITOR_SYMBOL_FFT_ANTS_RECORDING = 4044\`, \`MONITOR_CPR_RECORD_BUFFER = 4045\`, L1 state, BER/PER, FEC/burst statistics, preamble and RF gain information.
- The monitor-filter table is **256 individual bytes**, with IDs 4013..4268 mapped to \`filter[id - 4013]\` rather than bitmap bits. Monitor records can travel via diagnostic/trace output. \`scripts/re/intel_wimax_monitor_filter.py\` generates an offline filter.
- None of those names establishes that a **production** Intel 6250 returns continuous raw IQ, complex FFT symbols or post-FEC bits. A receiver could fail synchronisation before delivering anything due to a DJI-specific preamble.

Suggested receive-only live experiment: submit 2450000 kHz scan request; monitor L1 sync, preamble, BER/PER, 4044/4045 and RXIQ; capture raw return values and error codes. Goal: tap the modem **after OFDM/FEC but before MAC**, if available.

## 4. Lightbridge and WiMAX historical timeline

User: **"What is the timeframe of lightbridge annd womax was it hard to find chipsets when DJI used altrerra"**

- IEEE mobile WiMAX 802.16e completed 2005, available in commercial chips 2006-2011.
- Intel WiMAX 5150/5350 launched 2008; 6250 launched 2011.
- Altera Cyclone V family available by 2012.
- DJI announced original **standalone Lightbridge 30 April 2014**; development likely began prior to that public announcement.
- DJI announced **Phantom 3 Professional and Advanced 8 April 2015** with integrated Lightbridge.
- Vendors such as Intel, Sequans, Beceem, GCT and Wavesat existed, so assertion that *no chips were for sale* is unsupported. Better hypothesis: commercial WiMAX PHY/MAC silicon was **less customisable** than an FPGA with RF transceiver, especially for unusual framing, hopping, bidirectional control and low-latency video.
- Early boards contain Altera Cyclone V and AD9363 (plus STM32 radio controller); subsequent variants use Artosyn components.
- Intel purchased Altera **after** the original standalone Lightbridge era, so the corporate relationship does not explain DJI's original choice.

See [history report](../docs/lightbridge-wimax-history.md).

## 5. Public SDR captures and original standalone firmware

User: **"Are there any sdr captures and is there firmware for the standalone light bride"**

Research leads:
- [GENESYS Hovering UAVs RF dataset](https://genesys-lab.org/hovering-uavs), labelled **Matrice 100 Lightbridge**, example metadata 10 MS/s, 2406.5 MHz, short IQ sections.
- [KU Leuven RF dataset](https://rdr.kuleuven.be/dataset.xhtml?persistentId=doi:10.48804/HZRVNZ).
- [Zenodo public DJI RF data](https://zenodo.org/records/4264467).
- [DJI original Lightbridge downloads](https://www.dji.com/product/dji-lightbridge/download): Assistant software and standalone component revision listings.
- [2016 firmware extraction thread](https://phantompilots.com/threads/lightbridge-firmware-problem-and-solution-firmware-version-not-found-by-dji-assistant-tool.77073/) discusses \`LB_hack.zip\`, \`LightbridgeTerminal\`, decrypted firmware and DaVinci bootloader. Original archive availability and integrity not established.

These captures and standalone images **were not successfully downloaded and byte-verified in this chat**. Distinguish from in-repository *P3 firmware* already unpacked.

## 6. Published Lightbridge signal characterisation

User: **"Is there any public analysis of the data"**  
User: **"It seems odd surly some has an idea of hoee it works"**  
User: **"Keep searching I am sure there is more"**

Public leads and claims encountered:
- [GENESYS, RF Fingerprinting Unmanned Aerial Vehicles with Non-standard Transmitter Waveforms](https://genesys-lab.org/papers/UAV-TVT-20.pdf). Real M100 RF capture and burst/statistical signal characterisation, **not an end-to-end decoder**.
- [Classifying UAVs With Proprietary Waveforms via Preamble Feature Extraction and Federated Learning](https://genesys-lab.org/papers/Classifying_UAVs_TVT.pdf): comparisons involving Phantom 3 and Matrice 100 preamble-like regions, not proven full preamble/PHY recovery.
- [B. Peng, 2021 thesis abstract](https://www.globethesis.com/?t=2492306308468534) describes OFDM synchronisation/pilots/CP analyses; original thesis tables were **not** obtained.
- [PhantomPilots Lightbridge synchronization](https://phantompilots.com/threads/lightbridge-synchronization.130951/): researcher reports nonmatching **standard WiMAX long preamble** for **Phantom 4 Pro** and narrow/wideband links (~1.4 vs ~10 MHz); needs replication before extending to Phantom 3.
- Secondary account reported **10.9375 kHz** spacing, **864** active carriers (downlink) and narrow uplink. Important correction: **864 active carriers is also a standard 802.16e AMC allocation possibility**, so this number alone does **not** demonstrate proprietary PHY.
- [CN110046591B Chinese patent](https://patents.google.com/patent/CN110046591B/en) lists Phantom 3 test/simulation parameters: 1024 carriers, 202 null, CP 128, 9.3 kHz, QPSK. It appears in **simulation context**, with no verified independent IQ-derived measurement. 1024 * 9.3 kHz = 9.5232 MS/s, inconsistent with the current m0900-derived 11.2 MS/s estimate. Note the **822** non-null inference vs the other 864 claim.
- Crucial correction: DJI's [April 2014 official Lightbridge release](https://www.dji.com/hk-en/newsroom/news/dji-has-released-dji-lightbridge) states **configurable encryption**. Earlier project text describing all Lightbridge data as merely unkeyed whitening is **not proven**.

No verified open and reproducible full 2014-2015 Lightbridge video/control PHY decoder was identified in this investigation.

## 7. Standalone Lightbridge vs Phantom 3, and modern DJI

User: **"The patent needs to be cotrect"**  
User: **"Isodern lightbridge the same"**  
User clarifying: **"I meant what does DJI use mow"**

DJI's original standalone Lightbridge, Phantom 3 integrated Lightbridge and later Lightbridge variants must not be treated as confirmed bit-compatible merely from a shared name. DJI's later mainstream ecosystem moved to **OcuSync** (O2/O3/O4/O4+) and separate professional SDR transmission products; no evidence modern systems are bit-compatible with WiMAX or original Lightbridge. This is a *background history note*, not evidence about a Phantom 3 IQ capture.

## 8. IQ-data analysis proposed, not yet measured

User: **"Can U analyse splrs"** (interpreted as IQ samples / SDR data)

A first exploratory \`scripts/re/lightbridge_iq_probe.py\` was committed to PR #62 for spectrum/OFDM CP checks, but it is **hardcoded** to 120 MS/s centre 2440 MHz signed int16 complex IQ, so **do not feed it 10 MS/s GENESYS float16 IQ as-is**. Its estimator has not yet been benchmarked against a published, byte-verified Lightbridge capture. Claimed results would be invented.

Needed measurements: provenance/hash, occupied spectrum, FFT size, symbol duration, CP ratio, CFO, pilots, carrier count, WiMAX preamble compatibility, and whether data can pass through Intel's receiver. Strongly prefer a *Phantom 3* specific sample to validate P3 claims; M100 is useful but may differ.

### User's latest requests

> "can you make a gh issue for the iq analysis please asl odo a doc about what we discovedovered re the wimax history and lightbridge background ?"
>
> "same the complete chat to the repo unde chats"

Created:
- [Issue #71](https://github.com/awto-au/awto-dji/issues/71) - plan to measure Lightbridge PHY from real I/Q data.
- [Background history and evidence document](../docs/lightbridge-wimax-history.md).
- This research chat record under \`chats/\`.

**Transcript limitation:** This record preserves the substance, chronology, original user excerpts and links available in the conversation context. It is explicitly **not** a verified word-for-word export of every exchanged message.

## Important unresolved questions

1. Is the exact original Lightbridge / Phantom 3 OFDM preamble conventional IEEE 802.16e or proprietary?
2. Are FFT=1024, 11.2 MS/s, 864 active carriers, CP=1/8 really observed *on air* on a P3?
3. What are packet headers, carrier/pilot assignments, FEC and scrambler; are data frames encrypted at another layer?
4. Can Intel 6250 accept 2.45 GHz, synchronise with DJI, and export symbols/bits before its MAC?
5. Does a production Intel card enforce secure boot; what does the actual vendor signature cover?
6. Can a public M100 IQ dataset inform P3, and which model variants are really interoperable?
