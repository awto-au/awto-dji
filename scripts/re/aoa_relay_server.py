#!/usr/bin/env python3
"""TCP listener for the app's diag relay (app/awto_dji_app/lib/debug/tcp_relay.dart):
accepts the phone's AOA accessory byte stream over WiFi and decodes it here, natively,
so protocol changes don't need an APK rebuild+install cycle. Bidirectional: also reads
hex-encoded DUML frames (one per line) from a command FIFO and forwards them to the phone,
which writes them straight to the accessory - a PC-side command proxy with no app UI
involved. Send with scripts/re/aoa_send.py, not by typing into the FIFO directly.

Usage: python3 -I scripts/re/aoa_relay_server.py [--port 9900]
Point the app's "Diag relay host:port" field at this machine's LAN IP:port.
Log: captures/sessions/<today>/aoa_relay_server.log (raw hex) and
     captures/sessions/<today>/aoa_relay_frames.log (decoded) - tracked, real-hardware data.
Command FIFO: tmp/aoa_send.fifo (created on startup; one hex-encoded frame per line)
"""
import argparse
import os
import socket
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_proto import repo_root, session_log_dir  # noqa: E402


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


class StreamDemuxer:
    """Properly splits the raw AOA byte stream into DUML frames and H.264 Annex-B video,
    the two things actually sharing this pipe with no demux header (confirmed in
    docs/aoa-live-test-2026-10-23.md: DUML's `55`-SOF+length+CRC8+CRC16 framing and
    Annex-B's `00 00 01`/`00 00 00 01` start codes essentially never collide).

    At each position: try a full DUML frame (length field + both CRCs must pass); else
    try a NAL start code and skip straight to the next one (we don't need to decode video
    here, just not waste a scan byte-by-byte through it); else advance one byte. This
    replaces the old DUML-only scanner, which re-scanned every byte of every video region
    looking for stray `55`s and logged each miss as a "bad frame" - correct, but noisy and
    O(n) slower than recognizing and skipping whole video runs at once.
    """

    def __init__(self):
        self.buf = bytearray()
        self.duml_bytes = 0
        self.video_bytes = 0

    def feed(self, data, log_fn):
        self.buf.extend(data)
        i = 0
        n = len(self.buf)
        while i < n:
            b = self.buf[i]
            if b == 0x55 and i + 3 <= n:
                length = self.buf[i + 1] | ((self.buf[i + 2] & 0x03) << 8)
                if 13 <= length <= 1023:
                    if i + length > n:
                        break  # frame not fully buffered yet
                    frame = bytes(self.buf[i:i + length])
                    if (crc8(0x77, frame[:3]) == frame[3]
                            and crc16(0x3692, frame[:-2]) == int.from_bytes(frame[-2:], "little")):
                        self._decode(frame, log_fn)
                        self.duml_bytes += length
                        i += length
                        continue
            if b == 0 and i + 3 <= n and self.buf[i + 1] == 0 and self.buf[i + 2] == 1:
                i += 3  # 3-byte NAL start code, skip past it
                self.video_bytes += 3
                continue
            if b == 0 and i + 4 <= n and self.buf[i + 1] == 0 and self.buf[i + 2] == 0 and self.buf[i + 3] == 1:
                i += 4  # 4-byte form
                self.video_bytes += 4
                continue
            i += 1
            self.video_bytes += 1
        del self.buf[:i]
        if len(self.buf) > 2048:
            # Should only happen if genuinely stuck mid-video with no start code for a
            # long stretch; cap growth rather than buffer unboundedly.
            drop = len(self.buf) - 2048
            del self.buf[:drop]
            self.video_bytes += drop

    def _decode(self, frame, log_fn):
        sender, receiver = frame[4], frame[5]
        seq = frame[6] | (frame[7] << 8)
        ctype = frame[8]
        cset, cid = frame[9], frame[10]
        payload = frame[11:-2]
        log_fn(f"sender={sender:#04x} receiver={receiver:#04x} seq={seq} type={ctype:#04x} "
               f"set={cset:#04x} id={cid:#04x} payload={payload.hex()}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9900)
    args = ap.parse_args()

    log_dir = session_log_dir()
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

    fifo_path = os.path.join(repo_root(), "tmp", "aoa_send.fifo")
    if os.path.exists(fifo_path):
        os.remove(fifo_path)
    os.mkfifo(fifo_path)
    log(f"=== command FIFO at {fifo_path} ===")

    state = {"conn": None}
    lock = threading.Lock()

    def fifo_reader():
        while True:
            # A FIFO reader sees EOF once all writers close; reopen in a loop so the
            # relay server doesn't need to start before the first sender does.
            with open(fifo_path, "r") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        frame = bytes.fromhex(line)
                    except ValueError:
                        log(f"=== bad hex on command FIFO, dropped: {line[:80]} ===")
                        continue
                    with lock:
                        conn = state["conn"]
                    if conn is None:
                        log("=== command FIFO: no phone connected, dropped ===")
                        continue
                    try:
                        conn.sendall(frame)
                        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                        log(f"{ts} TX {len(frame)}B {frame.hex()}")
                    except OSError as e:
                        log(f"=== command send failed: {e} ===")

    threading.Thread(target=fifo_reader, daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    log(f"=== listening on 0.0.0.0:{args.port}, waiting for the phone ===")

    while True:
        conn, addr = srv.accept()
        log(f"=== connection from {addr} ===")
        with lock:
            state["conn"] = conn
        framer = StreamDemuxer()
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                log(f"{ts} +{len(data)}B {data.hex()}")
                framer.feed(data, logframe)
        finally:
            with lock:
                if state["conn"] is conn:
                    state["conn"] = None
            conn.close()
            log(f"=== {addr} disconnected ===")


if __name__ == "__main__":
    main()
