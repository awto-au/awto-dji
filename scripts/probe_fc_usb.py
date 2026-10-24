#!/usr/bin/env python3
"""Probe the Phantom 3 front micro-USB (CDC-ACM -> FC UART, DUML 9600 8N1).

Phase 1 passive listen, phase 2 one read-only DUML Get-Version (set 0x00 id 0x01) per target.
Log: captures/sessions/<today>/probe_fc_usb.log (tracked, real-hardware data).
Usage: probe_fc_usb.py [port]
"""
import datetime, os, select, subprocess, sys, time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/serial/by-id/usb-DJI_DJI_CONTROLLER_0001A0000000-if00"
# Stall guard: 9600 baud = ~960 B/s; a 13-byte reply is ~14 ms. 1 s of silence = no answer.
STALL_S = 1.0
PASSIVE_S = 3.0  # passive listen window; FC startup log would be continuous if present
TARGETS = {"flight-controller": 0x03, "camera": 0x01, "gimbal": 0x04, "rc/ofdm": 0x07}


def repo():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def session_log_dir():
    d = os.path.join(repo(), "captures", "sessions", datetime.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    return d


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


def main():
    log_path = os.path.join(session_log_dir(), "probe_fc_usb.log")
    lf = open(log_path, "a")

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
        print(line)
        lf.write(line + "\n"); lf.flush()

    subprocess.run(["stty", "-F", PORT, "9600", "raw", "-echo", "-hupcl", "cs8", "-cstopb", "-parenb", "clocal", "cread"], check=True)
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    def listen(window, label):
        got, end, last = b"", time.monotonic() + window, time.monotonic()
        while time.monotonic() < end and time.monotonic() - last < STALL_S + (window if not label else 0):
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                d = os.read(fd, 256)
                if d:
                    got += d; last = time.monotonic()
                    if label and len(got) >= 13 and time.monotonic() - last > 0.1:
                        break
            elif label and got and time.monotonic() - last > 0.1:
                break
            elif label and not got and time.monotonic() - last > STALL_S:
                break
        return got

    log(f"open {PORT}; passive {PASSIVE_S}s")
    d = listen(PASSIVE_S, "")
    log(f"passive rx {len(d)}B: {d.hex()}")

    for name, dst in TARGETS.items():
        pkt = duml(0x2A, dst, 0x1000 + dst, 0x40, 0x00, 0x01)
        os.write(fd, pkt)
        log(f"tx get-version -> {name}(0x{dst:02x}): {pkt.hex()}")
        t0 = time.monotonic(); got = b""
        while time.monotonic() - t0 < STALL_S:
            r, _, _ = select.select([fd], [], [], 0.05)
            if r:
                got += os.read(fd, 256)
                t0 = time.monotonic() - STALL_S + 0.15  # settle 150 ms after last byte
        log(f"rx {len(got)}B: {got.hex()}  ascii={got.decode('latin1').encode('ascii', 'replace').decode()!r}")
    os.close(fd)


if __name__ == "__main__":
    main()
