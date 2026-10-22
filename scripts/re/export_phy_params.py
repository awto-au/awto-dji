#!/usr/bin/env python3
"""Export the recovered m0900 PHY parameters as machine-readable files for the FPGA RE work.

Outputs (committed, regenerate with this script):
  docs/data/phy-params.json        values + status (verified|inferred|unknown) + source
  docs/data/ad9363-registers.tsv   effective AD9363 register map (addr, value, name)
  docs/data/channel-table.tsv      39-entry channel plan (idx, N, frac, LO MHz, boards)

Inputs: renode/captures/m0900-ad9363-spi2.txt, firmware/P3X_FW_V01.11.0020_m0900.bin.
Status words follow docs/phy-params.md. Inferred values are NOT proof.
Log: tmp/logs/export_phy_params.log
"""
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decode_ad9363 as d  # noqa: E402

ROOT = d.ROOT
OUT = os.path.join(ROOT, "docs", "data")


def last_writes(path):
    w = {}
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) >= 4 and p[0] == "W" and p[1] == "ad9363":
                w[int(p[2], 16)] = int(p[3], 16)
    return w


def chan(img, base_addr, n):
    rows = []
    for i in range(n):
        o = base_addr - d.BASE + i * 9
        r = img[o:o + 9]
        N = int.from_bytes(r[0:2], "little")
        frac = int.from_bytes(r[2:5], "little")
        mhz = struct.unpack("<f", r[5:9])[0]
        rows.append((i, N, frac, mhz))
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    cap = os.path.join(ROOT, "renode", "captures", "m0900-ad9363-spi2.txt")
    fw = os.path.join(ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin")
    w = last_writes(cap)
    img = open(fw, "rb").read()
    names = d.load_names()

    bb_int = w[0x044]
    bb_frac = (w[0x041] << 16) | (w[0x042] << 8) | w[0x043]
    bb_ratio = bb_int + bb_frac / d.BBPLL_MOD
    rx_int = (w[0x232] << 8) | w[0x231]
    rx_frac = (w[0x235] << 16) | (w[0x234] << 8) | w[0x233]
    rx_n = rx_int + rx_frac / d.RFPLL_MOD
    fref = d.FREF_HZ

    params = {
        "source": {
            "firmware": "P3X_FW_V01.11.0020_m0900.bin",
            "capture": "renode/captures/m0900-ad9363-spi2.txt",
            "method": "Renode emulation, direct calls with forced state; no real DUML session or SDR yet",
        },
        "bus": {"value": "SPI2 0x40003800 via FPGA bridge", "status": "verified"},
        "bbpll": {
            "integer": bb_int, "fraction": bb_frac, "modulus": d.BBPLL_MOD,
            "multiplier_of_fref": round(bb_ratio, 6), "status": "verified",
        },
        "rfpll": {
            "integer": rx_int, "fraction": rx_frac, "modulus": d.RFPLL_MOD,
            "n": round(rx_n, 6), "rx_equals_tx": True, "status": "verified",
        },
        "channel_table": {
            "address": "0x080190e0", "entries": 39, "lo_mhz_first": 2404.0,
            "lo_mhz_last": 2480.0, "step_mhz": 2.0,
            "file": "docs/data/channel-table.tsv", "status": "verified (table); MHz meaning inferred",
        },
        "fref_hz": {"value": fref, "status": "inferred",
                    "why": "reg 0x03A=0x27 (=Fref/1MHz-1 in no-OS), VCO range, RF ref 80 MHz fits channel table"},
        "bbpll_vco_hz": {"value": round(fref * bb_ratio), "status": "inferred (needs Fref)"},
        "adc_clk_hz": {"value": round(fref * bb_ratio / 8), "status": "inferred"},
        "sample_rate_hz": {"value": 11_200_000, "status": "verified bits; absolute value needs Fref", "why": "ADC=BBPLL/8, HB2 /2, HB1 /2, FIR /2 from regs 0x00A,0x003"},
        "lo_hz_base_profile": {"value": round(rx_n * 20_000_000), "status": "inferred (RF ref 80 MHz / 4)"},
        "rf_bandwidth_hz": {"value": 10_000_000, "status": "inferred",
                            "note": "FIR cutoff 5.0 MHz, TX BB ~5 MHz, RX BB pass 1 5 MHz; last RX BB calibration target is 0.625 MHz (exact), likely not the operating bandwidth"},
        "gains": {"agc_mode": "fast attack (inferred)", "max_gain_index": 76, "gain_table_entries": 91,
                  "tx_attenuation": "unknown (set at run time via 0x073/0x075)"},
        "unknown": ["Fref confirmation", "why last RX BB calibration targets 0.625 MHz", "run-time channel hop index",
                    "TX attenuation values", "board code to hardware revision"],
    }
    with open(os.path.join(OUT, "phy-params.json"), "w") as f:
        json.dump(params, f, indent=2)
        f.write("\n")

    with open(os.path.join(OUT, "ad9363-registers.tsv"), "w") as f:
        f.write("addr\tvalue\tname\n")
        for a in sorted(w):
            f.write(f"0x{a:03X}\t0x{w[a]:02X}\t{names.get(a, '')}\n")

    with open(os.path.join(OUT, "channel-table.tsv"), "w") as f:
        f.write("idx\tN_int\tfrac24\tN\tlo_mhz\tboards\n")
        for i, N, fr, mhz in chan(img, *d.CHAN_A):
            f.write(f"{i}\t{N}\t{fr}\t{N + fr / d.RFPLL_MOD:.6f}\t{mhz:.1f}\t2,4,5\n")
        for i, N, fr, mhz in chan(img, *d.CHAN_B):
            f.write(f"{i}\t{N}\t{fr}\t{N + fr / d.RFPLL_MOD:.6f}\t{mhz:.1f}\t6,7\n")

    os.makedirs(os.path.join(ROOT, "tmp", "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "tmp", "logs", "export_phy_params.log"), "w") as f:
        f.write(f"wrote {OUT}: {len(w)} regs\n")
    print(f"wrote {OUT}: {len(w)} registers, 78 channel rows")


if __name__ == "__main__":
    main()
