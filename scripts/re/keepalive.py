#!/usr/bin/env python3
"""Keep the RC from idle-timing-out during an AOA bench session, PC-side only - no
app/Dart changes, so tuning this never needs a rebuild+reinstall cycle (awto-dji#65).

Sends two independent timers of empty-payload Get* queries through
aoa_relay_server.py's command FIFO (same path as aoa_send.py/duml_cli.py):

  fast (default 1s): GetPushLinkMode (0x09/0x43) - link state, confirmed NOT already
    in the RC's own auto-push stream (captures/sessions/2026-10-26), so this is genuine
    inbound traffic proving a live session, not a duplicate of free telemetry.
  slow (default 60s): GetFPGA (0x09/0x05), Get9363 (0x09/0x07), GetVersion (0x00/0x01),
    GetPushBasebandState (0x09/0x03) - static-ish diagnostics (FPGA/AD9363/baseband
    register reads, firmware version); no reason to poll these at the fast rate.

Evidence a periodic send prevents the idle shutdown: docs/fc-usb-duml.md 2026-10-24,
a 0.5s ping over serial kept the RC's radio MCU link alive 574/574 ACKs over 4.75 min
with zero drops. fast=1s here is double that interval since this is AOA (not serial)
and the tolerance on this link hasn't been measured yet - tighten to 0.5s if 1s proves
insufficient.

aoa_relay_server.py must already be running; the app must already be connected
(phone_bench.py connect) for sends to reach the RC - this prints a warning but keeps
running otherwise, since the FIFO itself doesn't require a live phone connection.

Usage:
  python3 -I scripts/re/keepalive.py [--fast-s 1.0] [--slow-s 60] [--minutes N]
Log: tmp/logs/keepalive.log (loop status - not tracked hardware evidence itself,
the frames it sends show up in captures/sessions/<date>/aoa_relay_server.log same
as any other FIFO-sent frame).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from duml_proto import build_frame, send_via_proxy, repo_root  # noqa: E402
from _log import log  # noqa: E402

PC = 0x0A
REMOTE_CONTROLLER = 0x06
SEQ_BASE = 0x7300  # distinct block from aoa_send.py's default (0x7200) and the app's
                    # own one-shot diag queries (0x7000), so TX lines are distinguishable

FAST = [(0x09, 0x43, "GetPushLinkMode")]
SLOW = [
    (0x09, 0x05, "GetFPGA"),
    (0x09, 0x07, "Get9363"),
    (0x00, 0x01, "GetVersion"),
    (0x09, 0x03, "GetPushBasebandState"),
]


def send_one(seq, cmd_set, cmd_id, name):
    frame = build_frame(sender=PC, receiver=REMOTE_CONTROLLER, seq=seq, ack_type=2,
                         cmd_set=cmd_set, cmd_id=cmd_id, payload=b"")
    try:
        send_via_proxy(frame)
        log(f"sent {name} (set={cmd_set:#04x} id={cmd_id:#04x} seq={seq:#06x})")
    except SystemExit as e:
        log(str(e), "ERROR")
        return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fast-s", type=float, default=1.0)
    ap.add_argument("--slow-s", type=float, default=60.0)
    ap.add_argument("--minutes", type=float, default=None, help="stop after this long; default: until Ctrl+C")
    args = ap.parse_args()

    fifo = os.path.join(repo_root(), "tmp", "aoa_send.fifo")
    if not os.path.exists(fifo):
        log(f"no command FIFO at {fifo} - start aoa_relay_server.py first", "ERROR")
        return 1

    log(f"keepalive: fast={args.fast_s}s ({len(FAST)} msg), slow={args.slow_s}s ({len(SLOW)} msg)")
    seq = SEQ_BASE
    next_fast = next_slow = time.monotonic()
    end = time.monotonic() + args.minutes * 60 if args.minutes else None
    try:
        while end is None or time.monotonic() < end:
            now = time.monotonic()
            if now >= next_slow:
                for cmd_set, cmd_id, name in SLOW:
                    send_one(seq, cmd_set, cmd_id, name)
                    seq += 1
                next_slow = now + args.slow_s
            elif now >= next_fast:
                for cmd_set, cmd_id, name in FAST:
                    send_one(seq, cmd_set, cmd_id, name)
                    seq += 1
                next_fast = now + args.fast_s
            time.sleep(0.05)
    except KeyboardInterrupt:
        log("stopped (Ctrl+C)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
