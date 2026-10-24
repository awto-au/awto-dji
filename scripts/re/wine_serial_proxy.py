#!/usr/bin/env python3
"""Transparent serial proxy: relay + log every byte between a real device and a pty,
so a Wine app (DJI Assistant) can be pointed at the pty while we capture the real
traffic to/from the flight controller. Also frames/decodes DUML (SOF 0x55) on the fly.

Why a proxy and not just opening the real device twice: POSIX ttys allow concurrent
opens, but two independent readers race for bytes unpredictably - not a reliable
capture. This is a single reader on the real device, fanned out to the log and to a
pty whose slave Wine's COM-port mapping points at.

Usage:
    python3 -I scripts/re/wine_serial_proxy.py --real /dev/ttyACM11 --baud 9600
Prints the pty slave path on stdout (first line) for the caller to wire up Wine's
HKEY_LOCAL_MACHINE\\Software\\Wine\\Ports mapping to.
Log: tmp/logs/wine_serial_proxy.log (raw hex, one line per read, with direction/time)
     tmp/logs/wine_serial_proxy_frames.log (decoded DUML frames only)
Stop with Ctrl-C (SIGINT) or SIGTERM; closes cleanly either way.
"""
import argparse
import os
import pty
import selectors
import signal
import subprocess
import sys
import termios
import time
import tty
from pathlib import Path


def repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parent)
        return Path(out.stdout.strip())
    except Exception:
        return Path(__file__).resolve().parents[2]


ROOT = repo_root()
LOG = ROOT / "tmp/logs/wine_serial_proxy.log"
FRAMELOG = ROOT / "tmp/logs/wine_serial_proxy_frames.log"


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


class DumlReframer:
    """Resyncing DUML (SOF 0x55) framer fed one direction's byte stream."""

    def __init__(self, tag):
        self.buf = bytearray()
        self.tag = tag  # ">" app-to-fc, "<" fc-to-app

    def feed(self, data, log_fn):
        self.buf.extend(data)
        while True:
            sof = self.buf.find(0x55)
            if sof < 0:
                if len(self.buf) > 1:
                    self.buf = self.buf[-1:]  # keep a possible partial SOF byte
                return
            if sof > 0:
                del self.buf[:sof]
            if len(self.buf) < 3:
                return
            length = self.buf[1] | ((self.buf[2] & 0x03) << 8)
            if length < 13 or length > 1024:
                del self.buf[:1]  # not a real SOF, resync
                continue
            if len(self.buf) < length:
                return  # wait for more bytes
            frame = bytes(self.buf[:length])
            del self.buf[:length]
            self._decode(frame, log_fn)

    def _decode(self, frame, log_fn):
        hdr_crc_ok = crc8(0x77, frame[:3]) == frame[3]
        body_crc_ok = False
        if len(frame) >= 2:
            calc = crc16(0x3692, frame[:-2])
            body_crc_ok = calc == int.from_bytes(frame[-2:], "little")
        sender, receiver = frame[4], frame[5]
        seq = frame[6] | (frame[7] << 8)
        ctype = frame[8]
        cset, cid = frame[9], frame[10]
        payload = frame[11:-2]
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        line = (f"{ts} {self.tag} sender={sender:#04x} receiver={receiver:#04x} "
                f"seq={seq} type={ctype:#04x} set={cset:#04x} id={cid:#04x} "
                f"payload={payload.hex()} hdrCRC={'ok' if hdr_crc_ok else 'BAD'} "
                f"crc16={'ok' if body_crc_ok else 'BAD'}")
        log_fn(line)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--real", required=True, help="real serial device, e.g. /dev/ttyACM11")
    ap.add_argument("--baud", type=int, default=9600,
                     help="baud to configure on the real device (DUML over this FC port "
                          "is 9600 8N1 per probe_fc_usb.py; override if a different rate "
                          "is confirmed)")
    args = ap.parse_args()

    LOG.parent.mkdir(parents=True, exist_ok=True)
    logf = open(LOG, "a", buffering=1)
    framef = open(FRAMELOG, "a", buffering=1)

    def log(line):
        print(line, flush=True)
        logf.write(line + "\n")

    def logframe(line):
        print("FRAME " + line, flush=True)
        framef.write(line + "\n")

    real_fd = os.open(args.real, os.O_RDWR | os.O_NOCTTY)
    baud_const = getattr(termios, f"B{args.baud}", None)
    if baud_const is None:
        raise SystemExit(f"unsupported baud {args.baud}")
    attrs = termios.tcgetattr(real_fd)
    attrs[4] = baud_const  # ispeed
    attrs[5] = baud_const  # ospeed
    termios.tcsetattr(real_fd, termios.TCSANOW, attrs)
    tty.setraw(real_fd, termios.TCSANOW)  # Python's cfmakeraw equivalent; re-fetches
    # attrs internally so it keeps the baud just set, only flips the line-discipline flags

    pty_master, pty_slave_fd = pty.openpty()
    pty_slave_path = os.ttyname(pty_slave_fd)
    # raw-ify now so there's no canonical-mode buffering window before Wine's own
    # serial driver (re)configures the slave when it opens this COM port
    tty.setraw(pty_master, termios.TCSANOW)
    os.close(pty_slave_fd)  # we don't need to hold it open; Wine will open the path
    print(pty_slave_path, flush=True)  # first line of stdout: the path to wire up
    log(f"=== proxy start: real={args.real} baud={args.baud} pty_slave={pty_slave_path} ===")

    app_to_fc = DumlReframer(">")  # pty(app) -> real(fc)
    fc_to_app = DumlReframer("<")  # real(fc) -> pty(app)

    running = True

    def stop(signum, frame):
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    sel = selectors.DefaultSelector()
    sel.register(real_fd, selectors.EVENT_READ, "real")
    sel.register(pty_master, selectors.EVENT_READ, "pty")

    try:
        while running:
            for key, _ in sel.select(timeout=0.5):
                tag = key.data
                try:
                    data = os.read(key.fd, 4096)
                except OSError:
                    data = b""
                if not data:
                    continue
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                if tag == "real":
                    log(f"{ts} <  {data.hex()}")  # fc -> app
                    os.write(pty_master, data)
                    fc_to_app.feed(data, logframe)
                else:
                    log(f"{ts} >  {data.hex()}")  # app -> fc
                    os.write(real_fd, data)
                    app_to_fc.feed(data, logframe)
    finally:
        log("=== proxy stop ===")
        os.close(real_fd)
        os.close(pty_master)
        logf.close()
        framef.close()


if __name__ == "__main__":
    main()
