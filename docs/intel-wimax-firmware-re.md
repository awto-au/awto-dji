# Intel i6050 WiMAX firmware: container, load map, first Ghidra pass (#61)

Static analysis only (never executed). Owner waived the licence no-RE clause for this, 2026-11-02. Tags: **V** verified, **I** inferred, **U** unknown.
Image: `~/vendors/intel/wimax/sources/i6050-fw-usb-1.5.sbcf` (1531932 bytes; fetch + manifest in `~/vendors/intel/wimax/README.md`). Not in the repo; no extracted images are committed.

## Reproduce
- `python3 -I scripts/re/intel_wimax_sbcf.py ~/vendors/intel/wimax/sources/i6050-fw-usb-1.5.sbcf --out tmp/intel-wimax` (container + flat regions)
- `python3 -I scripts/re/intel_wimax_base_check.py` (base verification)
- `python3 -I scripts/re/intel_wimax_phy_tables.py` (PHY/RF tables)
- `python3 -I scripts/re/intel_wimax_ghidra.py` (headless Ghidra; applies `docs/symbols/intel_i6050_fw1.5.tsv`; output `tmp/intel-wimax/dump.txt`)
- `python3 -I scripts/re/intel_wimax_dis.py <hexaddr> <n> thumb|arm` (capstone, regions from tmp)

## 1. Container (SBCF) - V
- Format from Linux `i2400m` (`fw.c`, `i2400m.h` at v5.10; removed in 5.13, readable in git history `f54ec58fee83^`).
- BCF header 0xa1 dwords (0x284 bytes): type 6, version 0x10000, module_id 0x8ff1c1a1, vendor 0x8086, date 0x20100127, size 0x5d766 dwords (1531288 bytes), key/modulus 0x40 dwords (256 B), exponent 1 dword. Reserved bytes zero.
- Then 757 boot-command records `{cmd 0xcbbc0x0y, addr, size, checksum}` + payload, dword aligned; opcode WRITE (2) only; cmd bit 0x100 = checksum present.
- Checksum = sum(payload dwords) + cmd + addr + size (mod 2^32): all 754 checked records match, 3 records carry none. V
- Terminal command at 0x175d88: SIGNED_JUMP (0xcbbc0208) to **0xe80000**, 0x100 bytes (signature). 644 trailing bytes = a second BCF header (key block). No compression, no encryption at this layer (code disassembles directly). RSA signature scheme: see `intel_wimax_signature.py` (not repeated here).
- Write sequence (boot order), merged by contiguity:

| # | load addr | size | content |
|---|---|---|---|
| 0 | 0x828000 | 0x5994 | mostly zero + small header words (U) |
| 1,3,5 | 0x821128 | 4 | values 0,1,0: stage flag/doorbell (I) |
| 2,4 | 0x850000 | 0x1976c, 0xe454 | two stage payloads at the same address; 3-byte-field tables (U) |
| 6 | 0xc90000 | 0x34000 | data/config; patched by 9, 12 |
| 7 | 0xdc0000 | 0x8d210 | **ARM/Thumb code + data** (second image) |
| 8 | 0x086020 | 4 | 0xdc0534 (pointer into seg 7; I: hook/entry) |
| 9 | 0xc9001c | 0xedb | config bytes (includes string `BTS Autodetection 2.5GHz`) |
| 10 | 0xc8fc00 | 0x3f2 | magic 0xcafe900d block: band plan (below) |
| 11 | 0x740000 | 0x7720 | vector table + ITCM code; **copied to address 0** by `itcm_image_copy` (V, 0x6828 bytes) |
| 12 | 0xc90000 | 0xc | patch |
| 13 | 0xe80000 | 0x7ba44 | **main image, entry point** |

- Final-memory regions (later writes win) are what Ghidra loads: `regions.tsv` from the parser. Stale tail of the first 0x850000 payload remains (U).

## 2. CPU and base - V/I
- ARM, little-endian, ARMv5TE with Thumb interworking (`blx imm`, `clz`, `bkpt`). Entry stub sets FIQ/IRQ/ABT/UND/SVC stacks (CPSR 0xd1/d2/d7/db/d3). V
- `mcr p15 c9,c1` (TCM regions) and 8x `c6 c0..c7` (protection regions) => ARM946E-S class core (I; exact core not named anywhere). V for the register usage.
- MPU map (`mpu_region_cfg`, 0xe808c4): 0+16MB, 0+64KB, 0xe80000+512KB, 0xf00000+128KB, 0x200000+2MB, 0xff8000+32KB, 0xffe00000+1MB, 0xffff0000+32KB. V (literal decode); roles U.
- Stack top 0xfffc or 0x3cffc chosen by reg 0x80001c == 3. V; meaning U.
- Interrupts: VIC at 0xfff000 (IRQ stub reads +0x30). V
- Base verification (`intel_wimax_base_check.py`, literals that point into the segment and land on a prologue):

| segment | declared base | ARM prologue hits | Thumb prologue hits | best shifted base (+-0x1000, 0x10000, 4, 0x100) |
|---|---|---|---|---|
| 0xdc0000 | 0xdc0000 | 90 | 1590 | <=56 |
| 0xe80000 | 0xe80000 | 3 | 1039 | <=68 |
| ITCM image at 0 | 0 | 0 | 35 | 3 at -0x40 |

  Declared bases confirmed by branch targets too: `b 0xe80044` at ITCM 0x6c matches the `bl` after stack setup in the main image. V
- Ghidra: ARM:LE:32:v5t, blocks per region + ITCM copy at 0; seeded 11 ARM + 2357 Thumb functions (105 Thumb/ARM context conflicts skipped), 5677 functions after analysis (`dump.txt`). Setup is `scripts/re/ghidra/IntelWimaxSetup.java` + `IntelWimaxNames.java`; the project is regenerable, not committed (contains vendor code).

## 3. Naming pass (`docs/symbols/intel_i6050_fw1.5.tsv`, 60 entries)
- Trace/log: `trace_event` (0xe09128, 5102 callsites) and ITCM twin `trace_event_itcm` (0x4198) via ARM veneer `trace_event_thunk` (0xe80cc4, 5012). V
  - r0 = header (level in bits 31:29, module id in low byte, level table 0xe63c7c), r1 = format pointer stored as `(ptr - 0x0c104000) >> 2`. Format strings live outside the SBCF, so the image carries few readable strings. V
- Assert/halt helpers `fatal_assert2/3` (603 callers), bitmap helpers `bitmap_test` (824) / `bitmap_assign` (499), `memcpy_chunk12`, `load_be_uint`. V
- Embedded source paths (`Y:\networking_1\...`): Fsm.h, TlvLib.Inl, GeHdi_Ul.c, TxArqUtils.inl, GenericControlSequencer, `Modem\L1FW\L1Processes\Calibration\RxGainCalib_Evp_Kp.c`. Names taken from them are V.
- Version string `WIMAX_SW.5.10.1046` @0xe4b3ff. V
- Crypto/security strings: TLS labels (`master secret`, `key expansion`, `client/server finished`), `CMAC_KEYS+KEK`, `bek@wimaxforum.org`, WiMAX Forum Root-CA subject strings, base64 alphabet. => EAP-TLS/PKMv2 stack in firmware. I (function purpose), V (strings).
- "LTA" (`LtaRx`, `K:\LtaScenarios`): internal lab-test automation hooks incl. RX calibration states. I

## 4. PHY / RF tables vs `lightbridge-phy-measured.md`
- Band classifier `rf_freq_khz_to_band_idx` (0xea5ce8, the function behind the 0xea5db0 literal-pool table cited in `intel-wimax-firmware-patch-feasibility.md`): kHz -> idx 0..17 by cmp chain. Limits: 2350000, 2400000, 2450000, 2496000, 2550000, 2600000, 2650000, 2700000, 3300000, 3350000 .. 3800000 (50 MHz steps). Only f < 2.3 GHz or > 3.8 GHz is logged. **2.4-2.496 GHz is not rejected here.** V. Whether other code gates it: U.
- Band plan block `rf_band_plan_cfg` (0xc8fc00, magic 0xcafe900d), kHz: 2300000-2400000, 2496000-2550000, 2550000-2650000, 2650000-2690000, 3400000-3800000. V values. Reading as the supported-band list (no 2.4-2.496 GHz) matches the 6250 product brief. I
- RF cal-bin table (0xeef5e4): rows `{lo,hi,idx}` kHz in two idx 0..23 groups, 2180000-2861000 and 3165000-4059000 (width 19-38 MHz). The Lightbridge channels (2404-2480 MHz) fall in idx 10-12 (2403000-2482000). V values. Calibration grid: I
- Numerology records (`phy_numerology_*`), V fields, semantics I:

| BW | sample period (ps) | Fs | df (Hz) | frame (samples) | symbol / CP samples | FFT |
|---|---|---|---|---|---|---|
| 5 MHz | 178571 | 5.6 MS/s | 10937 | 28000 | 576 / 64 | 512 |
| 7 MHz | 125000 | 8 MS/s | 7813 | 40000 | 1152 / 128 | 1024 |
| 8.75 MHz | 100000 | 10 MS/s | 9766 | 50000 | 1152 / 128 | 1024 |
| 10 MHz | 89286 | 11.2 MS/s | 10937 | 56000 | 1152 / 128 | 1024 |

  - Frame samples = 5 ms x Fs (arithmetic matches all four). V arithmetic, I meaning.
  - 10 MHz record = Lightbridge measured numerology: Fs 11.2 MS/s, df 10937.5 Hz, symbol 1152 samples (102.86 us), CP 1/8. V match of numbers.
  - Differences: Intel frame 5 ms vs Lightbridge burst period 14.000 ms; Lightbridge 864 used carriers (+-432, pilot every 9th) vs the 802.16e PUSC/AMC sets in the other record fields (0x2c0 = 704, 0x33e = 830 etc., meanings U). Preamble: Lightbridge has no 1-in-3 802.16e preamble. So the radio *numerology* is shared, the *frame/MAC/PHY procedure* is not; stock firmware decoding Lightbridge remains unlikely. I
- Frequency tuning: constants exist for 2.3-2.7 GHz and 3.3-3.8 GHz only in these tables; synthesiser limits U.

## 5. Open
- U: who consumes `rf_band_plan_cfg` (xrefs by pointer are absent; likely read by offset from a base). U: SIGNED boot enforcement on a real card. U: seg 0/2/4 (0x828000, 0x850000) content. U: function of the 0xdc0000 image vs 0xe80000 image (two code images; calls from 0xe80000 into 0xdc0000 exist, e.g. trace_event at 0xe09128).
- Next: find readers of 0xc8fc00 and the cal table via literal xrefs in Ghidra; decode the numerology record fields (0x30, 0x2c0, 0x33e...) against the 802.16e subchannel tables; map the Thumb command dispatcher (host `I2400M_PT_CTRL` handling) to look for diagnostic/IQ-capture modes.

## Sources consulted
- Linux `drivers/net/wimax/i2400m/fw.c`, `include/uapi/linux/wimax/i2400m.h` (v5.10, git history of local kernel mirror): SBCF record/checksum layout.
- https://www.kernel.org/doc/html/v5.4/admin-guide/wimax/i2400m.html : i2400m = Echo Peak / Baxter Peak; no firmware-internal detail.
- https://raw.githubusercontent.com/cernekee/linux-firmware/master/i6050-fw-usb-1.5.sbcf : the image (size matches CI run in the feasibility doc).
- https://github.com/o-gs/dji-firmware-tools/wiki/TP703-RF-Protocols-board : Lightbridge is "WiMAX-based" on P3; later boards use Artosyn AR8001 + AD9361, no Intel firmware detail.
- https://phantompilots.com/threads/hacking-lightbridge.38620/ : forum, nothing on baseband.
- Searches for published i6050 firmware RE, Ghidra loaders for SBCF, and Lightbridge-on-Intel work found none (gh code/repo search, DuckDuckGo via playwrong).
