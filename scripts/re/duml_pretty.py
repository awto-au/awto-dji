#!/usr/bin/env python3
"""Tail a relay frames log and print one human-readable line per frame - device names
instead of 0x02/0x0e, command names instead of set=0x04 id=0x05, decoded fields instead
of raw hex, for every command with a known payload layout. Other commands fall back to
hex (see duml_telemetry.format_frame and the catalog in duml_catalog.py).

Log: --log PATH, or the newest captures/sessions/<date>/aoa_relay_frames.log.
--since N replays the last N seconds of the log, measured back from the log's last
line (so it works on finished logs), then exits.

Usage:
  python3 -I scripts/re/duml_pretty.py                  # newest log, tail live, forever
  python3 -I scripts/re/duml_pretty.py --since 60       # last 60s of newest log, then exit
  python3 -I scripts/re/duml_pretty.py --log captures/sessions/2026-10-24/aoa_relay_frames.log --since 60
  python3 -I scripts/re/duml_pretty.py --grep gimbal    # only lines containing "gimbal"
"""
import argparse
import datetime
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_proto import repo_root  # noqa: E402
from duml_telemetry import format_frame, parse_line  # noqa: E402

TS_FMT = "%Y-%m-%dT%H:%M:%S"
TS_LEN = 19
# Live-tail poll. Frames arrive every tens of ms (observed 2026-10-24), so 0.1 s keeps up
# without spinning a core; expiry is not a failure, the loop just retries.
POLL_S = 0.1


def newest_log():
    """Newest captures/sessions/<date>/aoa_relay_frames.log that exists, or None."""
    root = os.path.join(repo_root(), "captures", "sessions")
    if not os.path.isdir(root):
        return None
    for day in sorted(os.listdir(root), reverse=True):
        p = os.path.join(root, day, "aoa_relay_frames.log")
        if os.path.isfile(p):
            return p
    return None


def last_timestamp(f):
    """Timestamp of the last complete line in a text file object, or None."""
    f.seek(0, os.SEEK_END)
    f.seek(max(0, f.tell() - 4096))
    for line in reversed(f.read().splitlines()):
        if len(line) >= TS_LEN:
            try:
                return datetime.datetime.strptime(line[:TS_LEN], TS_FMT)
            except ValueError:
                continue
    return None


def cutoff_for(f, since):
    """Lines with a timestamp below this string are older than `since` seconds."""
    last = last_timestamp(f)
    if last is None:
        raise SystemExit("log has no timestamped lines")
    return (last - datetime.timedelta(seconds=since)).strftime(TS_FMT)


def iter_lines(f, follow):
    """Complete lines from f. follow=False: stop at EOF (a trailing partial line is
    still yielded). follow=True: wait for new complete lines, never return."""
    while True:
        pos = f.tell()
        line = f.readline()
        if line.endswith("\n") or (line and not follow):
            yield line
            continue
        if not follow:
            return
        if line:
            f.seek(pos)  # partial line: re-read it once the writer finishes it
        time.sleep(POLL_S)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", default=None, help="relay frames log (default: newest session log)")
    ap.add_argument("--since", type=float, default=None,
                    help="replay the last N seconds of the log, then exit (default: tail "
                         "new lines only, run until Ctrl-C)")
    ap.add_argument("--grep", default=None, help="only print lines containing this text")
    args = ap.parse_args()

    log_path = args.log or newest_log()
    if not log_path or not os.path.exists(log_path):
        raise SystemExit(f"{log_path or 'no captures/sessions/*/aoa_relay_frames.log'} "
                         "not found - is the relay running, or pass --log")

    with open(log_path) as f:
        cutoff = cutoff_for(f, args.since) if args.since is not None else None
        if args.since is not None:
            f.seek(0)
        else:
            f.seek(0, os.SEEK_END)
        try:
            for line in iter_lines(f, follow=args.since is None):
                if cutoff is not None and line[:TS_LEN] < cutoff:
                    continue
                parsed = parse_line(line)
                if not parsed:
                    continue
                pretty = f"{line[:TS_LEN]} {format_frame(*parsed)}"
                if args.grep and args.grep.lower() not in pretty.lower():
                    continue
                print(pretty, flush=True)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
