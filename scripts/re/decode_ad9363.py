#!/usr/bin/env python3
"""Reduce a captured m0900 AD9363 SPI sequence to its effective register map + decode.

Input: a capture written by renode/peripherals/AD9363SpiTap.cs (SaveCapture), i.e. lines
    W ad9363 0xRRR 0xVV   / R ad9363 0xRRR 0xVV
Output (tmp/logs/ad9363_decode.txt + stdout): the final value per register (last write wins,
the effective config the firmware left in the AD9363), in address order, annotated against
the ADI AD9361/AD9363 register map (UG-570), plus the derived BBPLL / sample-rate / RF-PLL
(centre frequency) / bandwidth numbers where the fields are unambiguous.

Interop/structural RF-parameter recovery of an owned device (CLAUDE.md). No keys/geofence.

Usage:  python3 scripts/re/decode_ad9363.py [renode/captures/m0900-ad9363-spi2.txt]
"""
import os
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

# AD9361/AD9363 register names (ADI UG-570 / no-OS ad9361.h). Only load-bearing ones for the
# channel decode are named; others print as the raw address.
NAMES = {
    0x000: "SPI_CONF", 0x001: "MULTICHIP_SYNC_AND_TX_MON_CTRL",
    0x002: "TX_ENABLE_FILTER_CTRL", 0x003: "RX_ENABLE_FILTER_CTRL",
    0x004: "INPUT_SELECT", 0x005: "RFPLL_DIVIDERS", 0x006: "CLOCK_ENABLE",
    0x009: "ENSM_CONFIG_2 / clk ena", 0x014: "ENSM_MODE", 0x015: "ENSM_CONFIG_1",
    0x016: "CAL_CTRL", 0x017: "STATE",
    0x03F: "BBPLL_misc", 0x041: "FRACT_BB_FREQ_WORD_3(MSB)", 0x042: "FRACT_BB_FREQ_WORD_2",
    0x043: "FRACT_BB_FREQ_WORD_1(LSB)", 0x044: "INTEGER_BB_FREQ_WORD", 0x045: "CLOCK_CTRL",
    0x046: "CP_CURRENT", 0x048: "LOOP_FILTER_1", 0x049: "LOOP_FILTER_2",
    0x04A: "LOOP_FILTER_3", 0x04B: "VCO_CTRL", 0x04C: "VCO_PROGRAM_1",
    0x04D: "VCO_PROGRAM_2", 0x04E: "BBPLL_misc", 0x05E: "BBPLL_LOCK(status)",
    0x061: "CLOCK_CTRL",
    # Baseband / sample-rate chain
    0x0A0: "RX_SAMPLE_RATE?", 0x1F8: "clk divider",
    # RX RFPLL synth (centre freq) 0x230-0x27x ; TX RFPLL 0x270-0x2Bx
    0x231: "RX_FRACT_BYTE0", 0x232: "RX_FRACT_BYTE1", 0x233: "RX_FRACT_BYTE2",
    0x234: "RX_INTEGER_BYTE0", 0x235: "RX_INTEGER_BYTE1",
    0x23C: "RX_VCO_CTRL", 0x244: "RX_VCO_CAL(status)", 0x247: "RX_CAL_DONE(status)",
    0x271: "TX_FRACT_BYTE0", 0x272: "TX_FRACT_BYTE1", 0x273: "TX_FRACT_BYTE2",
    0x274: "TX_INTEGER_BYTE0", 0x275: "TX_INTEGER_BYTE1",
    0x284: "TX_VCO_CAL(status)", 0x287: "TX_CAL_DONE(status)",
    # BW / filters
    0x1E2: "RX_BBF_...", 0x1E3: "RX_BBF_...", 0x0C0: "TX_BBF_...",
}


def load_caps(path):
    writes = {}      # addr -> final value (last write wins)
    order = []       # addresses in first-seen order
    reads = {}       # addr -> count
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) < 4 or p[1] != "ad9363":
                continue
            addr = int(p[2], 16)
            val = int(p[3], 16)
            if p[0] == "W":
                if addr not in writes:
                    order.append(addr)
                writes[addr] = val
            elif p[0] == "R":
                reads[addr] = reads.get(addr, 0) + 1
    return writes, order, reads


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        ROOT, "renode", "captures", "m0900-ad9363-spi2.txt")
    writes, order, reads = load_caps(path)
    out = []

    def p(s=""):
        out.append(s)
        print(s)

    p(f"# AD9363 effective register map from {os.path.relpath(path, ROOT)}")
    p(f"# {len(writes)} registers written, {len(reads)} status registers polled\n")
    p("## Effective config (last write wins), address order")
    for a in sorted(writes):
        name = NAMES.get(a, "")
        p(f"  0x{a:03X} = 0x{writes[a]:02X}   {name}")

    p("\n## Status registers polled during bring-up (returned by the tap)")
    for a in sorted(reads):
        p(f"  0x{a:03X}  x{reads[a]}   {NAMES.get(a, '')}")

    # --- best-effort numeric decode of the unambiguous fields -----------------------------
    p("\n## Derived (unambiguous fields; verify against UG-570)")

    def w(a):
        return writes.get(a)

    # BBPLL fractional (0x041..0x043 little-ish) + integer (0x044); ref scaler in 0x045.
    if all(w(a) is not None for a in (0x041, 0x042, 0x043, 0x044)):
        frac = (w(0x041) << 16) | (w(0x042) << 8) | w(0x043)
        integer = w(0x044)
        ratio = integer + frac / 2088960
        p(f"  BBPLL: integer={integer} frac={frac} (modulus 2088960)  "
          f"=> Fvco = Fref x {ratio:.6f}")
        p("        (Fref = BBPLL reference; sample rate = Fvco / BBPLL-divider / decimation)")

    # RX RFPLL (centre freq): fract (0x231..0x233) + integer (0x234..0x235)
    if all(w(a) is not None for a in (0x231, 0x232, 0x233, 0x234)):
        rfrac = w(0x231) | (w(0x232) << 8) | (w(0x233) << 16)
        rint = w(0x234) | ((w(0x235) or 0) << 8)
        p(f"  RX RFPLL: integer={rint} frac={rfrac}  => f_LO = Fref_rf x (N+frac/2^..) / div")
    if all(w(a) is not None for a in (0x271, 0x272, 0x273, 0x274)):
        tfrac = w(0x271) | (w(0x272) << 8) | (w(0x273) << 16)
        tint = w(0x274) | ((w(0x275) or 0) << 8)
        p(f"  TX RFPLL: integer={tint} frac={tfrac}")

    logdir = os.path.join(ROOT, "tmp", "logs")
    os.makedirs(logdir, exist_ok=True)
    with open(os.path.join(logdir, "ad9363_decode.txt"), "w") as f:
        f.write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()
