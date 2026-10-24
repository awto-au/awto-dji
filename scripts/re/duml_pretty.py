#!/usr/bin/env python3
"""Tail captures/sessions/<date>/aoa_relay_frames.log and print one human-readable line
per frame - device names instead of 0x02/0x0e, command names instead of set=0x04 id=0x05,
decoded fields instead of raw hex, for every command the catalog knows. Falls back to hex
only for commands with no known payload layout (most of the catalog - see duml_commands.py
vs duml_catalog.py docstrings).

Usage:
  python3 -I scripts/re/duml_pretty.py                  # tail live, forever
  python3 -I scripts/re/duml_pretty.py --since 60        # last 60s, then exit
  python3 -I scripts/re/duml_pretty.py --grep gimbal     # only lines containing "gimbal"
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_proto import session_log_dir  # noqa: E402
from duml_telemetry import format_frame, parse_line  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--since", type=float, default=None,
                     help="seconds of past log to replay before tailing live (default: "
                          "tail new lines only, run until Ctrl-C)")
    ap.add_argument("--grep", default=None, help="only print lines containing this text")
    args = ap.parse_args()

    log_path = os.path.join(session_log_dir(), "aoa_relay_frames.log")
    if not os.path.exists(log_path):
        raise SystemExit(f"{log_path} doesn't exist yet - is the relay running?")

    f = open(log_path)
    cutoff = None
    if args.since is not None:
        cutoff = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() - args.since))

    try:
        while True:
            line = f.readline()
            if not line:
                if args.since is not None:
                    break
                continue
            if cutoff is not None and line[:19] < cutoff:
                continue
            parsed = parse_line(line)
            if not parsed:
                continue
            pretty = f"{line[:19]} {format_frame(*parsed)}"
            if args.grep and args.grep.lower() not in pretty.lower():
                continue
            print(pretty, flush=True)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
