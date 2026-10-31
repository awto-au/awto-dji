# Lightbridge ground/air radio SPI configuration

Research for [#87](https://github.com/awto-au/awto-dji/issues/87), 31 October 2026.
This is static firmware analysis and comparison with public Analog Devices code.
No simulator is implemented. Generic FPGA lifting remains in Pluribus; this document
owns the DJI firmware, radio configuration and board interpretation. See [SAFETY.md](SAFETY.md).

**V** means reproduced from hash-pinned bytes or checked against the cited public source.
**I** means an interpretation requiring an assumption. **U** means unresolved. A script's
last write is not necessarily a register's live value: calibration self-clears, indirect
RAM loads, read-dependent writes and subsequent firmware/FPGA transactions matter.

## Inputs, coverage and reproduction

| Input | SHA-256 | Scope |
|---|---|---|
| P3X 1.11.20 m0900 | `72156b4b18e8db4c35c74cf2e8ae90d216fd260cdb5b508087840a8d7313fe6d` | Air STM32F103, AD boards 2/4/5 |
| C1 1.6 m1400 | `43bc7d6cb9f9c916dcfee0146378a3a6c823d0c65ac9613ca5adecae25f9d93f` | Ground LPC1765, firmware mode 1/3 profiles |

Both were freshly downloaded from DJI's CDN, extracted and matched to
[data-manifest.md](data-manifest.md). The C1 container is
`https://dl.djicdn.com/downloads/lightbridge2/C1_FW_V01.06.0000.bin`;
the aircraft archive is
`https://dl.djicdn.com/downloads/phantom_3/20170706/P3P_FW_V01.11.0020.bin.zip`.
Firmware remains local, outside git.

Coverage is these exact builds, not every P3/Lightbridge variant. In particular, the
owned GL300C reported a newer 2017 build; this m1400 identifies itself as a 2016 build.
The separate LPC1549 m1401 module has **not** been assigned these tables or decoded in
this pass. Firmware mode numbers are not a verified physical RC-model mapping.

Run:

```sh
python scripts/re/lightbridge_radio_inventory.py --adi-source /path/to/ad9361.c
```

The optional ADI file is the official no-OS source described below. Without it the
inventory still runs, but does not assert an external gain-table comparison.
Outputs:

- [data/lightbridge-radio-registers.tsv](data/lightbridge-radio-registers.tsv): all
  261 distinct radio addresses in each long profile, register names, final table
  literals, applied-value caveats and source file offsets.
- [data/lightbridge-radio-inventory.json](data/lightbridge-radio-inventory.json):
  operation counts, table bounds, gain/FIR fingerprints and external match counts.
- `tmp/radio-inventory/`: complete ordered record logs and per-register histories,
  including polls/delays/markers; local-only, reproducible from the original inputs.

Register names are reference labels. Not every undocumented field has a verified
physical interpretation. Table-port addresses represent streams into internal memories;
their final byte alone is not the programmed FIR or gain table.

## Trace from MCU to radio

The air boot selection is in [fpga-bringup.md](fpga-bringup.md): board straps select the
AD9363 path for codes 2/4/5. `init_fpga_config` at flash `0x0800d7c6` invokes the record
interpreter at `0x0800d318`. Ground script selection is at m1400 **file offset** `0xbb86`,
interpreter `0xba6c`. Ground flash addresses equal file offsets plus `0xa000`; air flash
addresses equal file offsets plus `0x08008000`. Do not mix these conventions.

| Profile | File offset | Bytes | Records | Radio writes | FPGA writes | Radio reads | Polls | Delays |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Air AD boards | `0xe660` | `0x293c` | 2639 | 2614 | 0 | 7 | 12 | 4 |
| Ground mode 3 | `0x1d1d4` | `0x313c` | 3151 | 2607 | 512 | 10 | 12 | 4 |
| Ground mode 1 | `0x20c2c` | `0x313c` | 3151 | 2607 | 512 | 10 | 12 | 4 |

Remaining records are markers. Ground mode 0 selects a different 583-record table at
`0x20310` (512 FPGA writes and 65 other register writes). Its transceiver/register-map
identity is **U** here; do not apply AD9363 meanings to it. A further 25-record FPGA-only
overlay at `0x23d68` runs conditionally in mode 3 when the tested version/state halfword
is at least `0x0910`. Neither is silently combined with the long-profile radio matrix.

Transport, corroborated by the two firmware implementations:

1. MCU writes FPGA register 1 to bridge mode, using `[0x0e, 0x01, 0x01]`.
2. Separate chip-select frame carries the radio command/address/data.
3. MCU restores FPGA register 1 to the selected idle/engine mode.

Air uses SPI2 and PB12 chip select; ground uses LPC legacy SPI0 and P2.9, not SSP0/SSP1.
Ground helpers are `0xbec8` write and `0xbf16` read; FPGA raw register helpers are
`0xbdf6`/`0xbe24`. Bridge protocol and port evidence are in
[ground-upgrade-path.md](ground-upgrade-path.md#q2-fpga-image-upgrade-path) and
[phy-params.md](phy-params.md#protocol-ad9363-is-behind-the-fpga-on-spi2-verified).

Interpreter operations are radio write/read, FPGA write/read, bit poll, delay and
bridge-control markers. Polls wait for the indicated bit value with a finite retry
count; a static table is not evidence that a physical chip passed those polls.

**Read-dependent exception:** a radio write to `0x0a3` uses the cached read result,
masked to six bits and ORed with `0x40`. The record's literal data byte is not the
applied value. The export explicitly preserves this as a symbolic expression.

## Settings comparison

The following are **table-end** values, before post-table control writes. Full register
facts and offsets are in the TSV. Frequency/rate numbers assume Fref = 40 MHz and the
public ADI clock model; that reference frequency remains **I**, not measured here.

| Setting / registers | Air | Ground mode 3 | Ground mode 1 | Interpretation |
|---|---|---|---|---|
| TX enable/filter `0x002` | `ce` | `8e` | `8e` | Air TX1+TX2; ground TX2 only; same digital filter factor codes |
| RX enable/filter `0x003` | `ce` | `ce` | `ce` | Both RX channels enabled |
| RF input/output `0x004` | `03` | `03` | `03` | RX A balanced, TX A per ADI map |
| RF VCO dividers `0x005` | `11` | `11` | `11` | RX/TX divider codes 1, nominal divide by 4 |
| RX timing delay `0x006` | `0f` | `0f` | `0f` | Clock-delay nibble 0; data-delay nibble 15 |
| TX timing delay `0x007` | `0f` | `0f` | `00` | Mode-specific TX data timing |
| Port config `0x010..012` | `08 00 02` | same | same | CMOS, DDR, dual-port/full-duplex; frame pulse; no configured swaps/inversions |
| ENSM mode/config `0x013..015` | `01 0d 84` | same | same | FDD selected; control-state values must be interpreted with later writes |
| Reference cycles `0x03a` | `27` | `27` | `27` | ADI's MHz-minus-one convention suggests 40 MHz |
| BBPLL `0x041..045` | `1d 53 33 11 00` | same | same | Ratio approximately 17.92; nominal 716.8 MHz |
| ADC divider `0x00a` | `03` | `03 → 06` | `03 → 06` | Air stays /8; ground later changes /8 to /64 |
| RX FIR config `0x0f5` | `78` | `78` | `78` | 64 configured taps; programming control bits are distinct from tap count |
| TX FIR config `0x065` | `78` | `78` | `78` | 64 configured taps |
| RX BB target `0x1fb/1fc` | `05/00 → 00/50` | `05/00` | `05/00` | Air calibrates 5 MHz then 0.625 MHz BB; ground calibrates 5 MHz BB |
| RX tuner divider `0x1f8` | `0c → 5b` | `0c` | `0c` | Supports the different final calibration targets |
| TX1/TX2 attenuation low bytes | `00/00` | `18/18` | `00/00` | Table values only; high bytes zero; mode-3 code gives 6 dB attenuation by ADI's 0.25 dB step |
| RFPLL RX/TX, assuming 40 MHz | 2422/2422 MHz | 2402/2422 MHz | 2700/2700 MHz | Initial profile words, not demonstrated live channels or owned-board capabilities |

The mode-1 2700 MHz result is a warning against assigning every profile to the owned
P3 without proving mode, board and reference-clock selection. It is the arithmetic of
the extracted words under the stated assumption, not a claim that the owned radio
operates there.

### Clock contradiction to resolve

Direction matters: ground **receives video** and **transmits control/DUML**. Its
narrow transmit requirement is expected. The question below is whether its receive
path can retain the bandwidth needed for the wide video downlink.

ADI's `ad9361_get_clk_scaler` gives ADC = BBPLL / 2^divider-code. With the loaded filter
codes, sample rate is ADC /8. Thus:

- Air and the ground profile's early `/8` state give approximately 11.2 MS/s.
- The ground table's late `/64` state gives approximately 1.4 MS/s, inconsistent with
  receiving the measured wide video downlink if left unchanged.

The public driver derives DAC clock from ADC clock, with an optional further divide
by two. This is not a TX-only divider that can be assigned to narrow uplink while
leaving wide RX unaffected. Switching the common clock configuration between
receive and transmit periods is a plausible hypothesis, not an observed result.

The exact late writes are ground-mode3 file `0x20238` and mode1 `0x23c90`; each writes
`0x00a = 0x06`. Air has only its earlier `0x00a = 0x03` script write. A later FPGA/MCU
rewrite, conditional operating phase or interpretation gap remains **U**. Do not
"correct" the extracted byte to fit the expected bandwidth.

### Filters: loaded memory versus active filter

All three profiles load 128 coefficient addresses in each RX/TX FIR memory. They select
64 active taps. The active 64-tap filters are symmetric; the full 128-word arrays need
not be. RX and TX loaded arrays agree within each profile, and their fingerprints also
agree across the three profiles. This separates the 128-address programming sweep
from the 64-tap operating configuration, which a last-write register map cannot do.

Air's two BB calibration passes are real ordered writes. ADI's calibration routine
confirms the fractional BB target is in 1/128 MHz units, so `0x50` means 0.625 MHz,
not 80 kHz. Ground does not have that second narrow calibration in these scripts.

## Exact public gain-table fingerprint

**New external match, V:** all 77 entries at indices 0..76 of the air and ground-mode3
gain tables match, byte for byte and index for index, ADI no-OS's first
`full_gain_table` band (commented `800 MHz`, associated with the 200-1300 MHz range).
The other 14 loaded entries at 77..90 are zero in these two profiles. The configured
maximum index is 76.

Against the same three public 77-entry bands, aligned matches are:

| Firmware table | ADI band 0 | ADI band 1 | ADI band 2 |
|---|---:|---:|---:|
| Air | 77/77 | 52/77 | 25/77 |
| Ground mode 3 | 77/77 | 52/77 | 25/77 |
| Ground mode 1 | 30/77 | 16/77 | 14/77 |

This identifies exact reused table content, not the entire firmware implementation.
It does not show that 800 MHz is the operating RF band or prove the table is appropriate
or inappropriate for the actual front end. In particular, do not assign 2.4 GHz gain
in dB simply by borrowing the gain labels of an unrelated reference table. Investigate
older ADI table versions, custom tables and actual chip/front-end settings next.

This is a gain-table fingerprint, unrelated to authentication secrets or a radio key.

## Beyond initialisation: directly traced runtime paths

Ground `0xbb86` writes `0x014 = 0x29` after the long table (call at file `0xbc52`),
then checks ENSM state `0x017` and lock/status registers. This is already different
from the table-end `0x0d` value. On success it returns FPGA register 1 to engine mode
and toggles the FPGA control bit. Air's existing emulated capture also ends with
`0x014 = 0x29`; that is not evidence of a physical-chip measurement.

Ground function `0xcd54`, reached from `0xd1a6`, reads and updates `0x073/0x075` in
modes 1/3 from a configuration byte at state base `0x100041d8 + 0x94`, and has further
conditional fixed-value updates. Therefore table attenuation is not a live-power
measurement. This work documents settings; it does not change them.

A separate function at `0xcef8` writes RF port/divider settings and FPGA PLL-word
registers conditionally. The direct-call scan found no callers; indirect reachability
is unresolved. A generic indexed setter at `0xdb60` can tail-call the radio writer.
These are reasons a constant-address search is not an exhaustive live-state proof.

Reproduce the caller checks:

```sh
python scripts/re/mcu_trace.py --img firmware/C1_FW_V01.06.0000_m1400.bin who 0xbec8 1
python scripts/re/mcu_trace.py --img firmware/C1_FW_V01.06.0000_m1400.bin dis 0xbb86 130
python scripts/re/mcu_trace.py --img firmware/C1_FW_V01.06.0000_m1400.bin dis 0xcd54 160
```

The tracer's nearest-prologue grouping is heuristic; inspect the disassembly before
adopting a function name or declaring a path unreachable.

## Public source provenance

Official ADI no-OS revision checked: `b8f9317a7f426046b9a9004b6c05ae95120fa8fe`.

- [ad9361.c](https://github.com/analogdevicesinc/no-OS/blob/b8f9317a7f426046b9a9004b6c05ae95120fa8fe/drivers/rf-transceiver/ad9361/ad9361.c):
  `full_gain_table`, `ad9361_get_clk_scaler`, `ad9361_rx_bb_analog_filter_calib`,
  `ad9361_get_tx_atten`. Download SHA-256
  `9d4e6e460f9a6a03cfaad360155e96f6d7ecf5f0ce5332a702a7f3f12f7192bc`.
- [ad9361.h](https://github.com/analogdevicesinc/no-OS/blob/b8f9317a7f426046b9a9004b6c05ae95120fa8fe/drivers/rf-transceiver/ad9361/ad9361.h):
  register bits and PLL moduli. Download SHA-256
  `a26530fef4d449e5c6fd07159bfe90b7b3d9f1408e3523ca1ed6fbe36a1876c7`.
- [ADI AD9363 datasheet](https://www.analog.com/media/en/technical-documentation/data-sheets/ad9363.pdf):
  device/interface context. Shared-family register semantics are checked against the
  official driver; a common register address alone is not proof of every chip-specific
  behaviour.

The ADI files are external reference inputs, not vendored in this repository.

## Remaining work

1. Trace every later writer of `0x00a`, including FPGA engine transactions; determine
   whether `/64` is restored before wide receive operation. A real SPI capture is the
   decisive check if static closure remains incomplete.
2. Resolve mode/board selection and analyse m1401/newer live firmware independently.
3. Trace the generic indexed setters and indirect callers rather than assuming the
   initial script is exhaustive. Classify control writes by boot, calibration, receive,
   transmit and retune phase.
4. Decode remaining gain-table bytes to hardware gain stages, compare historical ADI
   versions and verify the front-end mapping before reporting gain in dB.
5. Compare exact band-AMC/MIMO pilot/null maps against held-out IQ captures. Preserve
   the distinction between shared IEEE 802.16 PHY structures and complete WiMAX.
6. Continue Altera example recovery separately. No sample authentication-secret/MAC
   match has been established; the SHA constants alone cannot establish one.

This inventory closes the lack of an explicit ground/air table comparison. It does
not close the live configuration, physical-board mapping or end-to-end PHY decode.
