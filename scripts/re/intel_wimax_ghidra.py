#!/usr/bin/env python3
"""Headless Ghidra pass over the Intel i6050 SBCF firmware (issue awto-au/awto-dji#61). Static only.

1. intel_wimax_sbcf.py extracts final-memory regions to tmp/intel-wimax/ (never committed).
2. analyzeHeadless imports reg_e80000.bin raw at 0xe80000 as ARM:LE:32:v5t; pre-script
   IntelWimaxSetup.java adds the other regions + seeds ARM/Thumb functions; auto-analysis runs;
   post-script IntelWimaxNames.java applies docs/symbols/intel_i6050_fw1.5.tsv and dumps to
   tmp/intel-wimax/dump.txt; second post-script IntelWimaxDecompile.java decompiles DECOMPILE_TARGETS
   (high-caller-count + known-interesting functions) to tmp/intel-wimax/decompile.txt.
Project: tmp/intel-wimax/proj (regenerable; not committed: contains vendor code).
Usage: intel_wimax_ghidra.py [--image PATH]   default ~/vendors/intel/wimax/sources/i6050-fw-usb-1.5.sbcf
Log: tmp/logs/intel_wimax_ghidra.log (headless: tmp/logs/intel_wimax_ghidra_headless.log)
Stall guard: no headless output for 60 s -> kill, fail, log last line.
"""
import argparse, os, shutil, subprocess, sys, time
from pathlib import Path

# Functions to decompile each pass: top call-count unnamed functions (#61 step 2) plus every
# function this pass identified as a table reader/accessor/entry point (#61 steps 3-4).
DECOMPILE_TARGETS = [
    "0xebfd32",  # main
    "0xec4e58",  # scheduler/event loop (I)
    "0xea5ce8",  # rf_freq_khz_to_band_idx
    "0xe9255c",  # rf_band_plan_cfg_get
    "0xe982e8",  # rf_band_plan_cfg_validate (caller of the above)
    "0xea3918",  # rf_cal_gain_lut_lookup (cal-table cluster)
    "0xdfd7f4", "0xe805b0", "0xe05984", "0xe8775c", "0xed6240",
    "0xe87490", "0xe832a0", "0xe31f68", "0xe3a1e0", "0xdc03e4", "0xeed994",
    "0xea449c",  # rf_cal_bin_lookup candidate (called by ea3918 before the LUT byte read)
    "0xea39d8", "0xea4330", "0xea4a28",  # ea3918's callees (calib coefficient unpack/apply)
    "0xe9e49c",  # second band/channel index conversion used by ea3918
    "0xe9ac58",  # sole caller of rf_freq_khz_to_band_idx
]


def repo_root():
    e = os.environ.get("AWTO_DJI_REPO")
    if e:
        return Path(e)
    try:
        return Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
    except Exception:
        return Path(__file__).resolve().parents[2]


REPO = repo_root()
OUT = REPO / "tmp" / "intel-wimax"
LOGF = REPO / "tmp" / "logs" / "intel_wimax_ghidra.log"
STALL = 60


def log(m):
    LOGF.parent.mkdir(parents=True, exist_ok=True)
    line = time.strftime("%Y-%m-%dT%H:%M:%S%z ") + m
    print(line, flush=True)
    with LOGF.open("a") as f:
        f.write(line + "\n")


def run(cmd, logfile):
    with logfile.open("w") as fh:
        p = subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT)
        last, t0 = -1, time.monotonic()
        while p.poll() is None:
            sz = logfile.stat().st_size
            if sz != last:
                last, t0 = sz, time.monotonic()
            elif time.monotonic() - t0 > STALL:
                p.kill()
                tail = logfile.read_text().splitlines()[-1:]
                log("STALL: no output for %ds, killed; last line: %s" % (STALL, tail))
                sys.exit(2)
            time.sleep(1)  # poll interval for the stall check only
        return p.returncode


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=str(Path.home() / "vendors/intel/wimax/sources/i6050-fw-usb-1.5.sbcf"))
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    log("extract regions")
    subprocess.check_call([sys.executable, "-I", str(REPO / "scripts/re/intel_wimax_sbcf.py"), a.image, "--out", str(OUT)],
                          stdout=open(REPO / "tmp/logs/intel_wimax_sbcf.log", "w"))
    proj = OUT / "proj"
    if proj.exists():
        shutil.rmtree(proj)
    proj.mkdir()
    sd = REPO / "scripts/re/ghidra"
    cmd = ["analyzeHeadless", str(proj), "IntelWimax", "-import", str(OUT / "reg_e80000.bin"),
           "-processor", "ARM:LE:32:v5t", "-loader", "BinaryLoader", "-loader-baseAddr", "0xe80000",
           "-scriptPath", str(sd),
           "-preScript", "IntelWimaxSetup.java", str(OUT),
           "-postScript", "IntelWimaxNames.java", str(REPO / "docs/symbols/intel_i6050_fw1.5.tsv"), str(OUT),
           "-postScript", "IntelWimaxDecompile.java", ",".join(DECOMPILE_TARGETS), str(OUT)]
    log("running: " + " ".join(cmd))
    rc = run(cmd, REPO / "tmp/logs/intel_wimax_ghidra_headless.log")
    log("analyzeHeadless rc=%d" % rc)
    sys.exit(rc)


if __name__ == "__main__":
    main()
