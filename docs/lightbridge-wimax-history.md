# WiMAX history and DJI Lightbridge background

**Research status:** 2026-10-26. This is an evidence ledger for the [awto-dji](https://github.com/awto-au/awto-dji) project, not a claim that DJI's physical layer is a stock IEEE 802.16e implementation or that the Intel 6250 can decode it.

## 1. Historical timeline

| Date | Event | Evidence and significance |
|---|---|---|
| 2005 | IEEE 802.16e mobile WiMAX standard completed | Establishes the available OFDMA design family before Lightbridge. |
| 2008 | Intel WiMAX/WiFi Link 5150 and 5350 launched | Intel [product catalogue](https://www.intel.com/content/www/us/en/ark/products/series/97845/intel-wireless-series.html) lists Q2 2008. |
| 2011 | Intel Centrino Advanced-N + WiMAX 6250 launched | [Intel's product specifications](https://www.intel.com/content/www/us/en/products/sku/59468/intel-centrino-advancedn-wimax-6250-dual-band/specifications.html). Already on the market before standalone Lightbridge. |
| 2012 | Altera Cyclone V FPGA family becomes commercially available | Relevant because early Lightbridge boards used a Cyclone V; exact DJI design start not independently established. |
| **2014-04-30** | **DJI releases standalone 2.4 GHz Lightbridge** | [Official DJI announcement](https://www.dji.com/hk-en/newsroom/news/dji-has-released-dji-lightbridge): 1080p/30 video, integrated control uplink, multi-receiver support and *configurable encryption*. |
| **2015-04-08** | **DJI announces Phantom 3 Professional/Advanced with integrated Lightbridge** | [Official DJI announcement](https://www.dji.com/dk/newsroom/news/dji-unveils-the-phantom-3-the-next-evolution-of-the-world-s-most-popular-consumer-drone). |
| 2015 onward | Intel WiMAX and other commercial implementations decline as mobile providers move toward LTE | Commercial market evolution is relevant to hardware availability, but does **not** prove DJI chose an FPGA because chips were unavailable. |
| 2016 onward | DJI transitions its later consumer products towards OcuSync | OcuSync is a successor family, not an established bit-compatible Lightbridge PHY. |

**Interpretation:** Conventional WiMAX silicon existed when DJI developed Lightbridge. The likely motivation for an FPGA + software-defined RF transceiver was control over synchronisation, hopping, framing, FEC and multiplexing, not absolute inability to buy any WiMAX chip. DJI's exact engineering/procurement rationale is not published in these sources.

### Standalone versus Phantom 3

The standalone Lightbridge was marketed in April 2014; the Phantom 3 integration followed in April 2015. They belong to the same product family, **not necessarily identical firmware images, channel plans, FPGA bitstreams or PHY framing**. Use device-specific captures and firmware for any assertion of over-the-air interoperability.

The [original Lightbridge download page](https://www.dji.com/dji-lightbridge) is a useful source for archived Assistant/releases. A [2016 repair/reverse-engineering thread](https://phantompilots.com/threads/lightbridge-firmware-problem-and-solution-firmware-version-not-found-by-dji-assistant-tool.77073/) describes firmware extraction and a \`LB_hack.zip\` package, but its download integrity and exact contents are not verified in this project.

## 2. Chip architecture and vendor options

Early Phantom 3 radio board references identify:

- Analog Devices **AD9363** agile RF transceiver.
- **Altera Cyclone V FPGA**, responsible for a substantial share of programmable baseband processing.
- **STM32F103** configuration/control MCU.
- Later board revisions used **Artosyn** radio/baseband parts instead. Exact variant and air/ground side must be recorded before comparing images.

Sources: [P3X receiver board community documentation](https://github.com/o-gs/dji-firmware-tools/wiki/P3X-OFDM-Receiver-board); this repo's [PHY parameters](phy-params.md) and [FPGA interfaces](fpga-interfaces.md).

Commercial WiMAX chip vendors in that era included Intel, Beceem, Sequans, GCT and Wavesat. An off-the-shelf WiMAX modem generally expects the IEEE network synchronisation and MAC protocol and may not expose demodulated bits before packet validation. A programmable FPGA can bypass those constraints at the cost of implementation effort.

Do **not** infer that Intel acquiring Altera in late 2015 means Intel designed DJI's 2013-2015 FPGA solution; Altera was independent during Lightbridge's initial development.

## 3. What Phantom 3 firmware actually establishes

[Project PHY-parameters investigation](phy-params.md) reports:

- The m0900 MCU firmware configures the AD9363 through an FPGA-mediated SPI interface.
- A channel table contains **39 centres from 2404 MHz to 2480 MHz in 2 MHz steps**.
- With an **inferred 40 MHz reference clock**, register values imply **11.2 MS/s** receive/transmit sample rate, approximately **10 MHz** RF channel bandwidth and **2422 MHz** in the captured configuration.
- The **40 MHz reference remains an inference**, so the absolute sample rate needs an independent on-air measurement.
- The digital low-pass configuration is consistent with around a 10 MHz channel; some analogue calibration registers have unresolved interpretation.

These are *configuration evidence*, **not a recovered video bitstream**.

## 4. Known and claimed OFDM parameters - do not conflate sources

| Parameter | Standard 10 MHz 802.16e baseline | Lightbridge lead | Evidence status |
|---|---|---|---|
| FFT | 1024 | 1024 proposed | *Hypothesis*, not independently confirmed from raw Phantom 3 IQ |
| Sample rate | 11.2 MS/s, common WiMAX setup | 11.2 MS/s from m0900 register configuration | **Inferred**, conditional on reference clock |
| Subcarrier spacing | 10.9375 kHz at 11.2 MS/s / 1024 | 10.9375 kHz reported by secondary technical writing | Consistent with firmware estimate; **not independently captured** |
| Active carriers | Allocation dependent: e.g. PUSC 840, FUSC 850, AMC 864 (verify exact modes/definitions) | 864 claimed in secondary account | **Not evidence of proprietary allocation by itself** |
| Cyclic prefix | Common ratios 1/4, 1/8, 1/16, 1/32 | 128 samples / 1/8 appears in Chinese patent | **Unverified** |
| Synchronisation/preamble | IEEE 802.16e sequences | A researcher reported stock WiMAX long preamble mismatch for a Phantom 4 Pro | Anecdotal *different model*, **requires reproduction** |
| FEC/interleaver | WiMAX modes | Unknown | Need bit recovery or an implementation trace |
| Payload scrambling | WiMAX randomisation vs DJI-specific implementation | Unknown | **Do not assert unkeyed-only**; original DJI 2014 release explicitly advertised configurable encryption |

### Patent caveat

[CN110046591B](https://patents.google.com/patent/CN110046591B/en) gives, in a simulated Phantom 3 classification scenario, **1024 FFT, 202 null carriers, 128 CP samples, 9.3 kHz spacing, QPSK**. At face value those imply **822 non-null carriers** and **9.5232 MS/s** sampling. That conflicts with the m0900-derived **11.2 MS/s** estimate. Treat patent parameters as assumptions/test inputs, **not validated instrument measurements**. Do not claim the patent has settled the PHY.

A [PhantomPilots Lightbridge synchronisation discussion](https://phantompilots.com/threads/lightbridge-synchronization.130951/) is a useful lead on reported different narrow/wideband signals and a failed standard WiMAX-preamble comparison. The source/device, IQ file and code need to be obtained before generalising from Phantom 4 Pro to Phantom 3.

## 5. Available IQ evidence and publications

### Public capture leads

- [GENESYS Hovering UAVs dataset](https://genesys-lab.org/hovering-uavs): public labelled **DJI Matrice 100 Lightbridge** I/Q recordings, with example **10 MS/s**, **2406.5 MHz** centre, float16 complex I/Q according to dataset metadata. **Not yet downloaded and validated in this repo.**
- [KU Leuven drone RF dataset](https://rdr.kuleuven.be/dataset.xhtml?persistentId=doi:10.48804/HZRVNZ): possible wider-band DJI recordings. The model and exact protocol of each file must be confirmed from its metadata.
- [Zenodo DJI RF recordings](https://zenodo.org/records/4264467): a separate public dataset lead. Confirm licence and sample format before use.

### Published analysis leads

- [RF Fingerprinting Unmanned Aerial Vehicles with Non-standard Transmitter Waveforms](https://genesys-lab.org/papers/UAV-TVT-20.pdf): Matrice 100 Lightbridge IQ characterisation; **RF identification, not packet decoding**.
- [Classifying UAVs With Proprietary Waveforms via Preamble Feature Extraction and Federated Learning](https://genesys-lab.org/papers/Classifying_UAVs_TVT.pdf): proprietary-waveform features and cross-correlation for several DJI platforms, including Phantom 3; **not a published complete PHY decoder**.
- [Research on UAV Image Transmission Signal Analysis and Recognition](https://www.globethesis.com/?t=2492306308468534): abstract suggests OFDM/CP/pilot analysis, but the full thesis parameters have **not** been inspected.
- [CN110046591B](https://patents.google.com/patent/CN110046591B/en): a candidate parameter set with the simulation caveat described above.

Do **not** treat an SDR frequency fingerprint classifier, a DJI network-packet parser, or a generic OFDM demodulator as proof of raw Lightbridge-bit decoding.

## 6. Intel WiMAX 6250 experiments and limitations

The **Intel Centrino Advanced-N + WiMAX 6250** predates standalone Lightbridge and is a plausible research platform for *some* PHY stages.

Research work in [issue #61](https://github.com/awto-au/awto-dji/issues/61) and [draft PR #62](https://github.com/awto-au/awto-dji/pull/62) retrieved the authentic \`i6050-fw-usb-1.5.sbcf\` image:

- Length **1,531,932 bytes**, SHA-256 \`bd38e7dc36deebd0ba3601ea8c5dc70dcd11a99b940137811e99387d5f249296\`.
- Whole-image measured Shannon entropy **6.26705 bits/byte**. Not uniformly encrypted/compressed.
- A convincing **ARM Thumb instruction sequence** at file offset \`0x11f624\`, loaded at \`0xea5db0\`; full processor identification is not yet complete.
- Contiguous little-endian frequency constants at file \`0x11f654\`, memory \`0xea5de0\`, include **2300, 2350, 2400, 2450, 2496, 2550, 2600, 2650, 2700 MHz**.
- Those constants do **not prove** that 2450 MHz is an accepted tunable channel or that analog RF filters/synthesiser support it.
- The BCF boot protocol has signed/unsigned pathways and a \`SIGNED_JUMP\` command. The card's real boot mode and the signature's coverage/enforcement still need live validation; do not assume modified code will boot.

Further technical detail: [firmware patch feasibility](intel-wimax-firmware-patch-feasibility.md).

### What the Intel diagnostic API may expose

Intel's public \`wimax-ns\` source defines:

- \`L4_PRODUCTION_OPCODE_GET_PHY_RX_SYNC_STATUS\`
- \`L4_PRODUCTION_OPCODE_GET_PHY_RXIQ_VALUES\`
- \`L4_PRODUCTION_OPCODE_CMD_START_RXIQ_TEST\`
- \`L3L4_TLV_TYPE_MONITOR_SYMBOL_FFT_ANTS_RECORDING = 4044\`
- \`L3L4_TLV_TYPE_MONITOR_CPR_RECORD_BUFFER = 4045\`
- L1 state, BER/PER, FEC/burst-statistics and preamble diagnostics.

A 256-byte filter table maps monitor type IDs \`4013 ... 4268\` to individual byte indices. The Linux \`i2400m\` driver can forward \`I2400M_PT_TRACE\` messages to userspace.

These confirm **interfaces and control paths**, *not* that production i6050 firmware exports arbitrary IQ samples, frequency-bin symbols, or FEC-decoded bits. That must be demonstrated, ideally against a live owned card.

Useful sources:
- [Intel userland monitor TLV IDs](https://github.com/ago/wimax-ns/blob/master/InfraStack/OSDependent/Linux/L4Generated/L3L4TlvTypes.h)
- [Intel production command IDs](https://github.com/ago/wimax-ns/blob/master/InfraStack/OSAgnostic/Common/L4Common/SourceControl/L3L4CommonDefines.h)
- [Linux RX interface](https://github.com/torvalds/linux/blob/v5.10/drivers/net/wimax/i2400m/rx.c)
- [Linux signed-boot loader](https://github.com/torvalds/linux/blob/v5.10/drivers/net/wimax/i2400m/fw.c)

## 7. Recommended next steps

1. Acquire **one** small public *real* IQ recording, preserve URL, licence, checksum, sample datatype, sample rate, centre frequency, aircraft model, transmit state and capture direction.
2. Independently measure **occupied bandwidth and bursts**, **FFT/CP correlations**, **preamble candidates**, **occupied bins and pilot pattern**. Compare alternate sample-rate hypotheses **without forcing an assumed WiMAX answer**.
3. Separate **Phantom 3, original standalone Lightbridge, Matrice 100 and Phantom 4 Pro** before transferring conclusions.
4. Test a receive-only **2450000 kHz scan** and available diagnostics on an owned Intel 6250 if hardware is accessible; document error codes and actual trace bytes.
5. If the Intel hardware synchronises, identify whether **post-FFT, post-FEC or raw IQ** can be obtained ahead of MAC filtering. If not, develop a receive-only software PHY using IQ samples.
6. Keep **whitening, framing, optional payload encryption, device pairing and WiMAX MAC compatibility** as distinct questions.

### Related work

- [Lightbridge IQ analysis issue](https://github.com/awto-au/awto-dji/issues) (specific issue linked after creation)
- [Initial SDR IQ analysis script](https://github.com/awto-au/awto-dji/blob/research/intel-wimax-band-inspection/scripts/re/lightbridge_iq_probe.py) - **currently hardcodes 120 MS/s, 2440 MHz, signed int16 I/Q**. It is **not** valid as-is for GENESYS float16 / 10 MS/s.
- [Chat research record](../chats/2026-10-26-lightbridge-wimax-iq-investigation.md)
