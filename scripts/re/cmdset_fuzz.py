#!/usr/bin/env python3
"""Read-only DUML cmdset fuzz: send Get-Version (id 0x01) and a few other safe Get* probes to
every known cmdset number (0-33, from the public dissector's DJI_DUMLv1_CMD_SET_TEXT table,
including product generations the Phantom 3 doesn't nominally use) against a real port, and log
any reply. Only Get*-style read queries are sent - never Set*/control.

Usage: python3 -I scripts/re/cmdset_fuzz.py /dev/ttyACM4 [--receiver 0x03] [--baud 115200]
Log: tmp/logs/cmdset_fuzz.log
"""
import argparse
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


# Every cmdset number the public dissector names, including product generations Phantom 3
# doesn't nominally use - the "a command from another product might still be a hint" probe.
CMDSETS = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 28, 33]
# Safe, read-only probe ids: 0x01 Get Version (near-universal), 0x00 Ping.
PROBE_IDS = [0x01, 0x00]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("port")
    ap.add_argument("--receiver", type=lambda s: int(s, 0), default=0x03,
                     help="receiver devicetype (default 0x03 flight controller)")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--settle", type=float, default=0.3, help="listen window per probe, seconds")
    args = ap.parse_args()

    log_path = os.path.join(repo_root(), "tmp", "logs", "cmdset_fuzz.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    lf = open(log_path, "a")

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
        print(line)
        lf.write(line + "\n")

    fd = os.open(args.port, os.O_RDWR | os.O_NOCTTY)
    baud_const = getattr(termios, f"B{args.baud}")
    attrs = [0, 0, termios.CLOCAL | termios.CREAD | termios.CS8, 0, baud_const, baud_const, [0] * 32]
    attrs[6][termios.VMIN] = 0
    attrs[6][termios.VTIME] = 0
    termios.tcsetattr(fd, termios.TCSANOW, attrs)

    log(f"=== cmdset fuzz start: port={args.port} receiver={args.receiver:#04x} baud={args.baud} ===")
    seq = 0x5000
    hits = 0
    for cset in CMDSETS:
        for cid in PROBE_IDS:
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
            if got:
                hits += 1
                log(f"cmdset={cset:#04x} id={cid:#04x}: REPLY {len(got)}B {got.hex()}")
            else:
                log(f"cmdset={cset:#04x} id={cid:#04x}: silent")
    os.close(fd)
    log(f"=== done: {hits} cmdset/id combos got a reply out of {len(CMDSETS) * len(PROBE_IDS)} ===")


if __name__ == "__main__":
    main()
