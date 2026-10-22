#!/usr/bin/env python3
"""Reduce a captured m0900 AD9363 SPI sequence to its effective register map + derived RF params.

Input: capture written by renode/peripherals/AD9363SpiTap.cs (SaveCapture):
    W ad9363 0xRRR 0xVV   / R ad9363 0xRRR 0xVV
Names: scripts/re/ad9361_regs.tsv (ADI AD9361/AD9363 register header, UG-570 map).
Also decodes the firmware's channel table (0x080190e0) when the firmware image is present.
Interop/structural RF-parameter recovery of an owned device (CLAUDE.md). No keys/geofence.

Evidence tags in the output: [reg] read straight from registers, [asm] stated assumption,
[inf] inferred from ADI driver semantics (not bench-verified).

Usage:  python3 scripts/re/decode_ad9363.py [renode/captures/m0900-ad9363-spi2.txt]
Log:    tmp/logs/ad9363_decode.txt
"""
import math
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=HERE,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return os.path.abspath(os.path.join(HERE, "..", ".."))


ROOT = repo_root()
BASE = 0x08008000
CHAN_A = (0x080190E0, 39)   # boards 2/4/5 (radio_config_apply -> FPGA regs 0xBA..0xBE)
CHAN_B = (0x0801923F, 39)   # boards 6/7   (-> FPGA regs 0xB8..0xBB)
RFPLL_MOD = 8388593         # RFPLL fractional modulus (ADI)
BBPLL_MOD = 2088960         # BBPLL fractional modulus (ADI)

# Assumptions, printed with the results. FREF is corroborated by reg 0x03A (ADI writes
# REFERENCE_CLOCK_CYCLES = Fref/1MHz - 1; 0x27 -> 40 MHz).
FREF_HZ = 40_000_000


HIST = {}   # addr -> value sequence with consecutive repeats collapsed


def load_names():
    names = {}
    path = os.path.join(HERE, "ad9361_regs.tsv")
    with open(path) as f:
        for ln in f:
            if ln.startswith("#") or not ln.strip():
                continue
            a, n = ln.split("\t")[:2]
            names[int(a, 16)] = n
    return names


def load_caps(path):
    writes, order, reads = {}, [], {}
    HIST.clear()
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) < 4 or p[1] != "ad9363":
                continue
            addr, val = int(p[2], 16), int(p[3], 16)
            if p[0] == "W":
                h = HIST.setdefault(addr, [])
                if not h or h[-1] != val:
                    h.append(val)
                if addr not in writes:
                    order.append(addr)
                writes[addr] = val
            elif p[0] == "R":
                reads[addr] = reads.get(addr, 0) + 1
    return writes, order, reads


def channel_table(img, base, n):
    out = []
    for i in range(n):
        o = base + 9 * i - BASE
        r = img[o:o + 9]
        integer = r[0] | (r[1] << 8)
        frac = r[2] | (r[3] << 8) | (r[4] << 16)
        mhz = struct.unpack("<f", r[5:9])[0]
        out.append((i, integer, frac, integer + frac / RFPLL_MOD, mhz))
    return out


def main():
    names = load_names()
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "renode", "captures", "m0900-ad9363-spi2.txt")
    w, order, reads = load_caps(path)
    out = []

    def p(s=""):
        out.append(s)
        print(s)

    def g(a, default=0):
        return w.get(a, default)

    p(f"# AD9363 effective register map from {os.path.relpath(path, ROOT)}")
    p(f"# {len(w)} registers written, {len(reads)} registers polled/read\n")
    p("## Effective config (last write wins), address order")
    for a in sorted(w):
        p(f"  0x{a:03X} = 0x{w[a]:02X}   {names.get(a, '')}")
    p("\n## Registers read during bring-up")
    for a in sorted(reads):
        p(f"  0x{a:03X}  x{reads[a]}   {names.get(a, '')}")

    p("\n## Assumptions")
    p(f"  [asm] Fref = {FREF_HZ / 1e6:g} MHz (reg 0x03A = {g(0x03A):#04x} -> ADI Fref/1MHz-1 = "
      f"{g(0x03A) + 1} MHz [inf]; not read from a schematic)")
    p("  [asm] BBPLL ref scaler code 0 (reg 0x045[1:0]) = x1")
    p("  [asm] ADC_CLK = BBPLL / 2^code (reg 0x00A[2:0]); RF LO = Fvco / 2^(div+1) (reg 0x005)")
    p("  [asm] RF PLL ref divider code 3 (0x2AB[0]:0x2AC[7]) = x2 -> Fref_rf = 80 MHz")

    p("\n## Derived")
    # BBPLL: integer 0x044, fractional 0x041(MSB) 0x042 0x043(LSB). Byte order is set by data:
    # MSB-first gives 17.92 exactly; LSB-first gives 3363613 > modulus (impossible).
    b_int = g(0x044)
    b_frac = (g(0x041) << 16) | (g(0x042) << 8) | g(0x043)
    b_ratio = b_int + b_frac / BBPLL_MOD
    fvco = FREF_HZ * b_ratio
    div = 1 << (g(0x00A) & 7)
    adc = fvco / div
    p(f"  BBPLL [reg]: int={b_int} frac={b_frac}/{BBPLL_MOD} (0x041 is the MSB) -> x{b_ratio:.6f}")
    p(f"  BBPLL VCO [asm]: {fvco / 1e6:.3f} MHz (ADI range 715-1430)")
    p(f"  BBPLL divider code {g(0x00A) & 7} -> ADC_CLK [asm] = {adc / 1e6:.3f} MHz")

    rx3 = g(0x003)
    tx2 = g(0x002)
    rx_hb2, rx_hb1 = (rx3 >> 3) & 1, (rx3 >> 2) & 1
    rx_dec3, rx_fir = (rx3 >> 4) & 3, rx3 & 3
    tx_hb2, tx_hb1 = (tx2 >> 3) & 1, (tx2 >> 2) & 1
    tx_int3, tx_fir = (tx2 >> 4) & 3, tx2 & 3
    p(f"  RX path [reg]: ch_en={(rx3 >> 6) & 3} DEC3 code={rx_dec3} HB2={rx_hb2} HB1={rx_hb1} "
      f"FIR code={rx_fir}")
    p(f"  TX path [reg]: ch_en={(tx2 >> 6) & 3} INT3 code={tx_int3} THB2={tx_hb2} THB1={tx_hb1} "
      f"FIR code={tx_fir}")
    # ADI: FIR code 0 = bypass, 1 = x1, 2 = x2, 3 = x4. DEC3/INT3 code 0 = bypass.
    fir_f = {0: 1, 1: 1, 2: 2, 3: 4}
    d3_f = {0: 1, 1: 2, 2: 3, 3: 4}   # no-OS: DEC3/THB3 divider = code + 1
    rx_ratio = (2 if rx_hb2 else 1) * (2 if rx_hb1 else 1) * fir_f[rx_fir] * d3_f[rx_dec3]
    tx_ratio = (2 if tx_hb2 else 1) * (2 if tx_hb1 else 1) * fir_f[tx_fir] * d3_f[tx_int3]
    p(f"  RX decimation [inf]: {rx_ratio}; TX interpolation [inf]: {tx_ratio}")
    p(f"  RX sample rate [asm+inf] = {adc / rx_ratio / 1e6:.3f} MHz; "
      f"TX = {adc / tx_ratio / 1e6:.3f} MHz (DAC_CLK_DIV2={(g(0x00A) >> 3) & 1})")

    # RFPLL: integer = 0x231 | 0x232<<8 ; fractional = 0x233 | 0x234<<8 | (0x235 & 0x7F)<<16
    for tag, bi, bf in (("RX", 0x231, 0x233), ("TX", 0x271, 0x273)):
        n_int = g(bi) | ((g(bi + 1) & 0x7) << 8)
        n_frac = g(bf) | (g(bf + 1) << 8) | ((g(bf + 2) & 0x7F) << 16)
        n = n_int + n_frac / RFPLL_MOD
        dsel = (g(0x005) & 0xF) if tag == "RX" else (g(0x005) >> 4) & 0xF
        vco = n * FREF_HZ * 2
        lo = vco / (1 << (dsel + 1))
        p(f"  {tag} RFPLL [reg]: int={n_int} frac={n_frac}/{RFPLL_MOD} -> N={n:.6f}, "
          f"VCO divider code {dsel}")
        p(f"  {tag} LO [asm]: VCO {vco / 1e6:.1f} MHz (AD936x VCO 6000-12000), "
          f"LO = {lo / 1e6:.3f} MHz")

    def hist(a):
        return "->".join(f"{v:#04x}" for v in HIST.get(a, []))

    p("  BBBW / tune-divider write history (script sets RX BW twice; final state is the 2nd):")
    for a in (0x1FB, 0x1FC, 0x1F8, 0x1F9, 0x0D6, 0x0D7):
        p(f"    0x{a:03X} {names.get(a, '')}: {hist(a)}")
    def bbbw(mhz, khz128):
        return mhz + khz128 / 128      # no-OS: 0x1FC = (bw % 1 MHz) * 128 / 1 MHz

    bw1, bw2 = bbbw(5, 0), bbbw(0, 0x50)
    p(f"    1st pass: 0x1FB=5, 0x1FC=0 -> RX BB bandwidth {bw1:g} MHz [reg+ADI]; "
      f"RF bandwidth {2 * bw1:g} MHz [ADI: real_rx_bandwidth = rf/2]")
    p(f"    2nd pass (script records 2581-2590): 0x1FB=0, 0x1FC=0x50 -> {bw2:g} MHz (= TX clamp "
      "minimum 625 kHz in no-OS); purpose UNKNOWN; final register state is this value")
    # no-OS dividers: RX = ceil(bbpll / (126906 * (bw/10 kHz))), TX = ceil(bbpll / (145036 * (bw/10 kHz)))
    for tag, k, bw, d in (("RX 1st", 126906, bw1, 12), ("RX 2nd", 126906, bw2, 0x5B),
                          ("TX", 145036, 5.0, g(0x0D6) | ((g(0x0D7) & 1) << 8))):
        calc = -(-int(fvco) // (k * int(bw * 1e6 // 10000)))
        p(f"  {tag}: no-OS divider for BB bw {bw:g} MHz = {calc}; firmware wrote {d}"
          f"{'  (match)' if calc == d else '  (differs by %d)' % (d - calc)}")

    p("\n## Gain / AGC [reg]; semantics [inf]")
    mode = g(0x0FA)
    p(f"  AGC_CONFIG_1 0x0FA={mode:#04x}: RX1 ctrl code {mode & 3}, RX2 ctrl code "
      f"{(mode >> 2) & 3} (ADI: 0 manual, 1 fast-attack, 2 slow-attack, 3 hybrid)")
    p(f"  MAX_LMT_FULL_GAIN 0x0FD={g(0x0FD):#04x} (max table index {g(0x0FD) & 0x7F})")
    p(f"  DIGITAL_GAIN 0x100={g(0x100):#04x} (max dig gain {g(0x100) & 0x1F}, "
      f"step {(g(0x100) >> 5) & 7})")
    p(f"  RX1 manual idx 0x109={g(0x109):#04x} LPF 0x10A={g(0x10A):#04x}; "
      f"RX2 0x10C={g(0x10C):#04x} 0x10D={g(0x10D):#04x}")
    p("  TX attenuation: not set by the init script (0x073/0x075 are written at runtime from "
      "radio_state+0x11b); the captured 0xFF is forced by m0900_trigger_capture.resc")

    # Channel table from firmware.
    fw = os.path.join(ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin")
    if os.path.exists(fw):
        with open(fw, "rb") as f:
            img = f.read()
        p("\n## Channel table A @0x080190e0 (39 x 9 B: int16, frac24, float32 MHz) [reg-in-flash]")
        rows = channel_table(img, *CHAN_A)
        r_int = g(0x231) | ((g(0x232) & 7) << 8)
        r_frac = g(0x233) | (g(0x234) << 8) | ((g(0x235) & 0x7F) << 16)
        for i, ni, nf, n, mhz in rows:
            hit = "   <== programmed by init script" if (ni, nf) == (r_int, r_frac) else ""
            p(f"  ch{i:02d}: N={n:9.5f} (int {ni} frac {nf:#08x})  {mhz:7.1f} MHz  "
              f"MHz/N={mhz / n:.4f}{hit}")
        p("\n## Channel table B @0x0801923f (boards 6/7; different Fref, ratio MHz/N ~19.35-19.5)")
        for i, ni, nf, n, mhz in channel_table(img, *CHAN_B):
            p(f"  ch{i:02d}: N={n:9.5f}  {mhz:7.1f} MHz  MHz/N={mhz / n:.4f}")

    logdir = os.path.join(ROOT, "tmp", "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "ad9363_decode.txt"), "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
