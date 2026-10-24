#!/usr/bin/env python3
"""Read-only DUML probe over every known command in docs/data/apk-dynamic-cmdset-ids.tsv
(723 real cmdset/cmdid facts from the dynamically-unpacked DJI GO 4 dex - see
docs/apk-analysis.md section 0 for the scope this data comes from).

Safety filter: only sends names starting with "Get" (case-sensitive) - the "safe to send" tier
documented in docs/apk-vs-dissector-gap-report-2026-10-23.md. Never Set*/Control*/anything else.
Sentinel entries ("Other", "ERROR") are skipped.

Usage: python3 -I scripts/re/full_command_probe.py /dev/ttyACM4 [--receiver 0x03] [--baud 115200]
Log: tmp/logs/full_command_probe.log (every probe) and tmp/logs/full_command_probe_hits.log
(replies only, for quick review)
"""
import argparse
import csv
import os
import select
import subprocess
import termios
import time


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def crc8(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8C if seed & 1 else seed >> 1
    return seed & 0xFF


def crc16(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8408 if seed & 1 else seed >> 1
    return seed & 0xFFFF


def duml(src, dst, seq, ctype, cset, cid, payload=b""):
    n = 13 + len(payload)
    h = bytes([0x55, n & 0xFF, ((n >> 8) & 3) | 0x04])
    body = h + bytes([crc8(0x77, h), src, dst, seq & 0xFF, seq >> 8, ctype, cset, cid]) + payload
    return body + crc16(0x3692, body).to_bytes(2, "little")


SENTINEL_NAMES = {"Other", "ERROR"}


def load_safe_commands(tsv_path):
    """Returns [(cmdset_value, cmdset_name, cmdid_value, cmdid_name)], Get*-only, deduped."""
    seen = set()
    out = []
    with open(tsv_path) as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            name = row["cmdid_name"]
            if name in SENTINEL_NAMES or not name.startswith("Get"):
                continue
            cv, iv = int(row["cmdset_value"]), int(row["cmdid_value"])
            key = (cv, iv)
            if key in seen:
                continue
            seen.add(key)
            out.append((cv, row["cmdset_name"], iv, name))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--receiver", type=lambda s: int(s, 0), default=0x03,
                     help="receiver devicetype (default 0x03 flight controller; use 0x06 for RC)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--settle", type=float, default=0.25, help="listen window per probe, seconds")
    ap.add_argument("--tsv", default=None, help="override docs/data/apk-dynamic-cmdset-ids.tsv path")
    args = ap.parse_args()

    root = repo_root()
    tsv_path = args.tsv or os.path.join(root, "docs", "data", "apk-dynamic-cmdset-ids.tsv")
    commands = load_safe_commands(tsv_path)

    log_path = os.path.join(root, "tmp", "logs", "full_command_probe.log")
    hits_path = os.path.join(root, "tmp", "logs", "full_command_probe_hits.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lf = open(log_path, "a")
    hf = open(hits_path, "a")

    def log(msg, hit=False):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
        print(line)
        lf.write(line + "\n")
        if hit:
            hf.write(line + "\n")
            hf.flush()

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY)
    baud_const = getattr(termios, f"B{args.baud}")
    attrs = [0, 0, termios.CLOCAL | termios.CREAD | termios.CS8, 0, baud_const, baud_const, [0] * 32]
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    log(f"=== full command probe start: port={args.port} receiver={args.receiver:#04x} "
        f"baud={args.baud}, {len(commands)} safe (Get*) commands to try ===")
    seq = 0x6000
    hits = 0
    for cset, cset_name, cid, cid_name in commands:
        pkt = duml(0x0A, args.receiver, seq, 0x40, cset, cid)
        seq += 1
        os.write(fd, pkt)
        end = time.monotonic() + args.settle
        got = b""
        while time.monotonic() < end:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                d = os.read(fd, 4096)
                if d:
                    got += d
        label = f"{cset_name}.{cid_name} (set={cset:#04x} id={cid:#04x})"
        if got:
            hits += 1
            log(f"{label}: REPLY {len(got)}B {got.hex()}", hit=True)
        else:
            log(f"{label}: silent")
    os.close(fd)
    log(f"=== done: {hits} replies out of {len(commands)} safe commands tried ===")


if __name__ == "__main__":
    main()
