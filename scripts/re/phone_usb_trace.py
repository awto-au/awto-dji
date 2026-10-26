#!/usr/bin/env python3
"""Kernel-level truth for the AOA OUT path on the phone, to locate where the
transfer-length lag enters (awto-dji#64): per accessory read, compare
  wire   : dwc3_complete_trb  (16384 - TRB size remaining = bytes the host sent)
  udc    : dwc3_gadget_giveback / usb_gadget_giveback_request (req->actual)
  driver : kretprobe acc_read ($retval, bytes handed to userspace)
  app    : aoa_relay_server.py RAWUDP read lengths + the 55cc header's declared size
Lengths only - no DMA buffer reads (those were stale under kprobes, see
phone_kprobe_sniff.py). Needs Magisk root, ftrace dwc3/gadget events, kprobe_events.

Usage:
  python3 -I scripts/re/phone_usb_trace.py --device <adb serial> [--reads 400]
  python3 -I scripts/re/phone_usb_trace.py --analyze <trace.txt> <aoa_relay_server.log>
Log: tmp/logs/phone_usb_trace.log. Trace: captures/sessions/<date>/phone_usb_trace_<ts>.txt
"""
import argparse
import re
import struct
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                            text=True, check=True).stdout.strip())
sys.path.insert(0, str(ROOT / "scripts" / "re"))
from duml_proto import session_log_dir  # noqa: E402

APP = "au.awto.dji.awto_dji_app"
RELAY = "192.168.25.114:9900"
TRACING = "/sys/kernel/debug/tracing"
PHONE_TRACE = "/data/local/tmp/usbtrace.txt"
LOG = ROOT / "tmp" / "logs" / "phone_usb_trace.log"
# Relay RAWUDP lines arrive ~10-20/s while connected (this session's captures);
# 20 s with no growth = the link is not delivering, not a lull -> abort (x~200 margin
# on the per-read interval, deliberately loose because connect itself takes ~3 s).
STALL_S = 20
BACKSTOP_S = 120

SETUP = f"""cd {TRACING}
echo 0 > tracing_on
echo 16384 > buffer_size_kb
echo 0 > events/enable
echo > kprobe_events
echo 'r:acc_rr acc_read ret=$retval' >> kprobe_events
echo 1 > events/kprobes/acc_rr/enable
echo 1 > events/dwc3/dwc3_complete_trb/enable
echo 1 > events/dwc3/dwc3_gadget_giveback/enable
echo 1 > events/gadget/usb_gadget_giveback_request/enable
echo > trace
echo 1 > tracing_on
echo armed
"""
TEARDOWN = f"""cd {TRACING}
echo 0 > tracing_on
cat trace > {PHONE_TRACE}
echo 0 > events/enable
echo > kprobe_events
echo disarmed
"""


def log(msg):
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def adb(device, *args, check=True):
    return subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True, check=check)


def su(device, script):
    path = "/data/local/tmp/phone_usb_trace_step.sh"
    tmp = ROOT / "tmp" / "phone_usb_trace_step.sh"
    tmp.write_text(script)
    adb(device, "push", str(tmp), path)
    # Magisk su runs `su 0 sh <file>` as a no-op here; only the `sh -c` form executes.
    r = adb(device, "shell", "su", "0", "sh", "-c", f"'sh {path}'", check=False)
    return r.stdout + r.stderr


def count_rawudp(path):
    try:
        with open(path) as f:
            return sum(1 for line in f if "RAWUDP seq=" in line)
    except FileNotFoundError:
        return 0


def capture(device, reads):
    relay_log = Path(session_log_dir()) / "aoa_relay_server.log"
    out = Path(session_log_dir()) / f"phone_usb_trace_{time.strftime('%Y%m%d-%H%M%S')}.txt"
    adb(device, "shell", "am", "force-stop", APP)
    r = su(device, SETUP)
    log(f"setup: {r.strip()}")
    if "armed" not in r:
        sys.exit("trace setup failed")
    base = count_rawudp(relay_log)
    adb(device, "shell", "am", "start", "-n", f"{APP}/.MainActivity",
        "-a", "au.awto.dji.action.CONNECT", "--es", "relay", RELAY)
    log(f"CONNECT sent; waiting for {reads} RAWUDP reads in {relay_log}")
    t0 = time.time()
    last_n, last_change = base, time.time()
    while True:
        n = count_rawudp(relay_log) - base
        if n != last_n:
            last_n, last_change = n, time.time()
        if n >= reads:
            break
        if time.time() - last_change > STALL_S:
            log(f"STALL: no new reads for {STALL_S}s (got {n}); aborting capture")
            break
        if time.time() - t0 > BACKSTOP_S:
            log(f"BACKSTOP: {BACKSTOP_S}s elapsed (got {n})")
            break
        time.sleep(0.5)
    r = su(device, TEARDOWN)
    adb(device, "shell", "am", "force-stop", APP)
    log(f"teardown: {r.strip()}; reads seen: {last_n} in {time.time() - t0:.1f}s")
    adb(device, "pull", PHONE_TRACE, str(out))
    log(f"trace pulled to {out} ({out.stat().st_size} bytes)")
    return out, relay_log


GIVEBACK_RE = re.compile(r"dwc3_gadget_giveback: (\S+): req \S+ length (\d+)/(\d+)")
UGIVEBACK_RE = re.compile(r"usb_gadget_giveback_request: (\S+): length (\d+)/(\d+)")
TRB_RE = re.compile(r"dwc3_complete_trb: (\S+): \d+/\d+ trb \S+ buf \S+ size (\d+) ctrl")
ACC_RE = re.compile(r"acc_rr: .*ret=(0x[0-9a-f]+|\d+)")
RAW_RE = re.compile(r"RAWUDP seq=(\d+) \+(\d+)B ([0-9a-f]+)")


def analyze(trace_path, relay_log):
    gb = Counter()
    seqs = {"trb": [], "udc": [], "udc2": [], "driver": []}
    ep = None
    lines = Path(trace_path).read_text(errors="replace").splitlines()
    for line in lines:
        m = GIVEBACK_RE.search(line)
        if m and int(m.group(3)) == 16384:
            gb[m.group(1)] += 1
    if gb:
        ep = gb.most_common(1)[0][0]
    log(f"OUT endpoint with 16384-byte requests: {ep} ({dict(gb)})")
    for line in lines:
        m = GIVEBACK_RE.search(line)
        if m and m.group(1) == ep and int(m.group(3)) == 16384:
            seqs["udc"].append(int(m.group(2)))
            continue
        m = UGIVEBACK_RE.search(line)
        if m and m.group(1) == ep and int(m.group(3)) == 16384:
            seqs["udc2"].append(int(m.group(2)))
            continue
        m = TRB_RE.search(line)
        if m and m.group(1) == ep:
            seqs["trb"].append(16384 - int(m.group(2)))
            continue
        m = ACC_RE.search(line)
        if m:
            seqs["driver"].append(int(m.group(1), 0))
    # userspace: last connection segment of the relay log
    reads = []
    for line in open(relay_log):
        if "=== connection from" in line:
            reads = []
        m = RAW_RE.search(line)
        if m:
            reads.append((int(m.group(1)), bytes.fromhex(m.group(3))))
    reads.sort()
    app = [len(d) - 8 for _, d in reads]
    declared = [struct.unpack_from("<I", d, 4)[0] if d[:2] == b"\x55\xcc" else None for _, d in reads]
    seqs["app"] = app
    for k, v in seqs.items():
        log(f"{k:7}: {len(v)} entries, first 20: {v[:20]}")

    def lag_of(seq):
        hits = Counter()
        for k in range(len(seq)):
            for lag in range(0, 10):
                j = k - lag
                if j >= 0 and j < len(declared) and declared[j] is not None and seq[k] == declared[j]:
                    hits[lag] += 1
        return hits.most_common(3)

    def align(a, b):
        n = min(len(a), len(b))
        best = None
        for off in range(-5, 6):
            eq = sum(1 for i in range(n) if 0 <= i + off < len(b) and a[i] == b[i + off])
            if best is None or eq > best[1]:
                best = (off, eq)
        return best, n

    for k in ("trb", "udc", "udc2", "driver", "app"):
        if seqs[k]:
            log(f"{k:7} vs declared header size: best lags {lag_of(seqs[k])}")
    for a, b in (("trb", "udc"), ("udc", "driver"), ("driver", "app"), ("trb", "app")):
        if seqs[a] and seqs[b]:
            (off, eq), n = align(seqs[a], seqs[b])
            log(f"{a} vs {b}: best offset {off}, {eq}/{n} equal")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device")
    ap.add_argument("--reads", type=int, default=400)
    ap.add_argument("--analyze", nargs=2, metavar=("TRACE", "RELAY_LOG"))
    args = ap.parse_args()
    if args.analyze:
        analyze(*args.analyze)
        return
    if not args.device:
        sys.exit("--device required")
    out, relay_log = capture(args.device, args.reads)
    analyze(out, relay_log)


if __name__ == "__main__":
    main()
