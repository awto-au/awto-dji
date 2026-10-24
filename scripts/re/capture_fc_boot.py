#!/usr/bin/env python3
"""Passive capture across an FC power cycle: log every byte with a timestamp relative to
capture start, so a real power-on -> first-traffic interval can be read off directly and
compared against the Renode-simulated ~6s-to-IRQn67-unmask finding (docs/fc-usb-duml.md).

Purely passive (no bytes transmitted) - sending during an unknown boot phase is what earlier
probes did and may itself be part of why they got no reply; this run rules that variable out.

Usage: python3 scripts/re/capture_fc_boot.py [port] [duration_s]
Log: tmp/logs/capture_fc_boot.log (human) and tmp/logs/capture_fc_boot_raw.hex (raw stream)
"""
import os, select, subprocess, sys, time

PORT = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyACM11"
DURATION_S = float(sys.argv[2]) if len(sys.argv) > 2 else 30.0


def repo():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def main():
    log_dir = os.path.join(repo(), "tmp", "logs")
    os.makedirs(log_dir, exist_ok=True)
    lf = open(os.path.join(log_dir, "capture_fc_boot.log"), "a", buffering=1)
    rawf = open(os.path.join(log_dir, "capture_fc_boot_raw.hex"), "a")

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
        print(line, flush=True)
        lf.write(line + "\n")

    subprocess.run(["stty", "-F", PORT, "9600", "raw", "-echo", "-hupcl",
                     "cs8", "-cstopb", "-parenb", "clocal", "cread"], check=True)
    fd = os.open(PORT, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)

    log(f"=== capture start, port={PORT}, duration={DURATION_S}s, passive (no TX) ===")
    log("reboot the aircraft now if testing boot timing")
    t0 = time.monotonic()
    end = t0 + DURATION_S
    total = 0
    first_byte_t = None
    while time.monotonic() < end:
        r, _, _ = select.select([fd], [], [], 0.2)
        if r:
            d = os.read(fd, 4096)
            if d:
                t = time.monotonic() - t0
                if first_byte_t is None:
                    first_byte_t = t
                    log(f"FIRST BYTE at t={t:.3f}s")
                total += len(d)
                log(f"t={t:.3f}s  +{len(d)}B  {d.hex()}")
                rawf.write(f"{t:.3f} {d.hex()}\n")
    log(f"=== capture end: {total}B total, first_byte_t={first_byte_t} ===")
    os.close(fd)


if __name__ == "__main__":
    main()
