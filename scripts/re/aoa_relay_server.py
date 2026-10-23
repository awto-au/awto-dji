#!/usr/bin/env python3
"""TCP listener for the app's diag relay (app/awto_dji_app/lib/debug/tcp_relay.dart):
accepts the phone's AOA accessory byte stream over WiFi and decodes it here, natively,
so protocol changes don't need an APK rebuild+install cycle.

Usage: python3 -I scripts/re/aoa_relay_server.py [--port 9900]
Point the app's "Diag relay host:port" field at this machine's LAN IP:port.
Log: tmp/logs/aoa_relay_server.log (raw hex) and tmp/logs/aoa_relay_frames.log (decoded)
"""
import argparse
import os
import socket
import subprocess
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


class DumlReframer:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data, log_fn):
        self.buf.extend(data)
        while True:
            sof = self.buf.find(0x55)
            if sof < 0:
                if len(self.buf) > 1:
                    self.buf = self.buf[-1:]
                return
            if sof > 0:
                del self.buf[:sof]
            if len(self.buf) < 3:
                return
            length = self.buf[1] | ((self.buf[2] & 0x03) << 8)
            if length < 13 or length > 1024:
                del self.buf[:1]
                continue
            if len(self.buf) < length:
                return
            frame = bytes(self.buf[:length])
            del self.buf[:length]
            self._decode(frame, log_fn)

    def _decode(self, frame, log_fn):
        hdr_ok = crc8(0x77, frame[:3]) == frame[3]
        body_ok = len(frame) >= 2 and crc16(0x3692, frame[:-2]) == int.from_bytes(frame[-2:], "little")
        sender, receiver = frame[4], frame[5]
        seq = frame[6] | (frame[7] << 8)
        ctype = frame[8]
        cset, cid = frame[9], frame[10]
        payload = frame[11:-2]
        log_fn(f"sender={sender:#04x} receiver={receiver:#04x} seq={seq} type={ctype:#04x} "
               f"set={cset:#04x} id={cid:#04x} payload={payload.hex()} "
               f"hdrCRC={'ok' if hdr_ok else 'BAD'} crc16={'ok' if body_ok else 'BAD'}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9900)
    args = ap.parse_args()

    log_dir = os.path.join(repo_root(), "tmp", "logs")
    os.makedirs(log_dir, exist_ok=True)
    rawf = open(os.path.join(log_dir, "aoa_relay_server.log"), "a", buffering=1)
    framef = open(os.path.join(log_dir, "aoa_relay_frames.log"), "a", buffering=1)

    def log(line):
        print(line, flush=True)
        rawf.write(line + "\n")

    def logframe(line):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        full = f"{ts} {line}"
        print("FRAME " + full, flush=True)
        framef.write(full + "\n")

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    log(f"=== listening on 0.0.0.0:{args.port}, waiting for the phone ===")

    while True:
        conn, addr = srv.accept()
        log(f"=== connection from {addr} ===")
        framer = DumlReframer()
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                log(f"{ts} +{len(data)}B {data.hex()}")
                framer.feed(data, logframe)
        finally:
            conn.close()
            log(f"=== {addr} disconnected ===")


if __name__ == "__main__":
    main()
