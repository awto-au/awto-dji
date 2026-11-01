#!/usr/bin/env python3.15t
"""Run a batch of loopback-sim force experiments with bounded parallelism and tabulate TX-slot activity (#91).

  python3.15t fpga/m2001/scripts/loopback_force_sweep.py [--jobs 5]
Jobs: leaf polarity 0 (sets 2, 4) + FSM state hold 0..15 (+fsm=N).  Each = cycloneiv_clean_loopback_sim.py run + analyse.
Table: AC8 toggles, AB12 toggles, distinct TX words in bursts, P19 (radio-SPI wake).  Log tmp/logs/loopback_force_sweep.log.
"""
import argparse
import concurrent.futures as cf
import json
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS as REPO, DJI  # noqa: E402
SIM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cycloneiv_clean_loopback_sim.py")
STIM = os.path.join(REPO, "tmp", "loopback", "stim_tx.txt")
OUT = os.path.join(REPO, "tmp", "loopback")
log = logging.getLogger("force_sweep")
CYC_FORCE, CYC_FSM = 6_000_000, 3_500_000   # leaf pulses need the f1 horizon; FSM hold starts at 1.0 M cycles, +2.5 M = > 1 frame (1.4 M)
STALL_S = 1500                              # one 6 M-cycle run measured ~330 s alone; 4.5x for 5-way contention. Expiry: job reported TIMEOUT


def jobs():
    j = [("p2v0", ["--force", "2", "--fval", "0"], CYC_FORCE), ("p4v0", ["--force", "4", "--fval", "0"], CYC_FORCE)]
    j += [(f"fsm{n:02d}", ["--fsm", str(n)], CYC_FSM) for n in range(16)]
    return j


def one(job):
    tag, extra, cyc = job
    base = [sys.executable, SIM]
    try:
        subprocess.run(base + ["run", "--tag", tag, "--stim", STIM, "--cyc", str(cyc)] + extra, check=True, timeout=STALL_S,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(base + ["analyse", "--tag", tag], check=True, timeout=600, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (subprocess.SubprocessError, OSError) as e:
        log.error("%s FAILED/TIMEOUT after limit %ds: %r", tag, STALL_S, e)
        return tag, None
    d = json.load(open(os.path.join(OUT, f"analysis_{tag}.json")))
    g = d["toggles"]
    words = len({(i, q) for _, i, q in d["tx_samples"]})
    return tag, dict(AC8=g.get("AC8"), AB12=g.get("AB12"), P19=g.get("P19"), bursts=len(d["bursts"]), tx_distinct=words)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--jobs", type=int, default=5)
    a = ap.parse_args()
    os.makedirs(os.path.join(DJI, "tmp", "logs"), exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s",
                        handlers=[logging.StreamHandler(), logging.FileHandler(os.path.join(DJI, "tmp", "logs", "loopback_force_sweep.log"))])
    with cf.ThreadPoolExecutor(a.jobs) as ex:
        for tag, r in ex.map(one, jobs()):
            log.info("%s %s", tag, r)


if __name__ == "__main__":
    main()
