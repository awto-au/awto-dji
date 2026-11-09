#!/usr/bin/env python3.15t
"""One-shot TX loopback-sim driver (#89 step 3): stimulus -> build -> long run -> TXD summary, all logged.

Chains the pieces so the sim runs unattended and writes a compact result, instead of iterating by hand:
  1. cycloneiv_clean_tx_stimulus.py --trigger   -> tmp/cycloneiv_clean/tx_stimulus.txt (581 writes)
  2. pluribus cycloneiv_clean_image_sim.py run --src rtl --tag tx  (builds Vtb with the +stim path)
  3. Vtb +stim=<file> +cyc=N   (replays boot+record, then free-runs; captures all output pads)
  4. cycloneiv_clean_txd_analyze.py  -> trace_tx_txd_summary.json + headline

  python3.15t fpga/m2001/scripts/cycloneiv_clean_tx_sim.py [--cyc 3000000] [--no-build] [--no-trigger]
Everything (stdout+stderr of each stage) -> tmp/logs/tx_sim.log.
"""
import argparse
import logging
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _repo import PLURIBUS as REPO, DJI  # noqa: E402
PY = sys.executable
LOG = os.path.join(DJI, "tmp", "logs", "tx_sim.log")
os.makedirs(os.path.dirname(LOG), exist_ok=True)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                    handlers=[logging.StreamHandler(), logging.FileHandler(LOG)])
log = logging.getLogger("tx_sim")


def run(stage, cmd, cwd=None):
    t = time.time()
    log.info("STAGE %s: %s", stage, " ".join(cmd))
    r = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for ln in r.stdout.splitlines()[-25:]:
        log.info("  | %s", ln)
    log.info("STAGE %s done rc=%s %.0fs", stage, r.returncode, time.time() - t)
    if r.returncode:
        sys.exit(f"stage {stage} failed rc={r.returncode}; see {LOG}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cyc", type=int, default=1_000_000, help="total clock cycles to run (covers the ~460k-cycle config replay + observation)")
    ap.add_argument("--no-build", action="store_true", help="reuse the existing Vtb binary")
    ap.add_argument("--no-trigger", action="store_true", help="omit the documented (unverified) post-boot arm pulse")
    a = ap.parse_args()
    stim = os.path.join(DJI, "tmp", "cycloneiv_clean", "tx_stimulus.txt")
    vtb = os.path.join(REPO, "tmp", "image_sim", "obj_tx", "Vtb")

    sc = [PY, os.path.join(HERE, "cycloneiv_clean_tx_stimulus.py")]
    if not a.no_trigger:
        sc.append("--trigger")
    run("stimulus", sc)
    if not a.no_build:
        run("build", [PY, os.path.join(REPO, "scripts", "cycloneiv_clean_image_sim.py"),
                      "run", "--src", "rtl", "--sim", "verilator", "--tag", "tx"], cwd=REPO)
    run("sim", [vtb, f"+stim={stim}", f"+cyc={a.cyc}"], cwd=REPO)
    run("analyze", [PY, os.path.join(HERE, "cycloneiv_clean_txd_analyze.py")])
    log.info("DONE -> %s and trace_tx_txd_summary.json", LOG)


if __name__ == "__main__":
    main()
