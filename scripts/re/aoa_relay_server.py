#!/usr/bin/env python3
"""TCP listener for the app's diag relay (app/awto_dji_app/lib/debug/tcp_relay.dart):
accepts the phone's channel-tagged v1 records over WiFi and independently decodes them,
so protocol changes don't need an APK rebuild+install cycle. Bidirectional: also reads
hex-encoded DUML frames (one per line) from a command FIFO and forwards them to the phone,
which writes them straight to the accessory - a PC-side command proxy with no app UI
involved. Send with scripts/re/aoa_send.py, not by typing into the FIFO directly.

Also runs a UDP listener on port+1 for the raw ground-truth stream (see
app/awto_dji_app/lib/debug/udp_raw_relay.dart): one datagram per accessory byte
chunk, verbatim, before AoaMux touches it. Decoded
independently of the TCP side's AoaMux-sourced output, so the two can be diffed instead
of trusting AoaMux's own framing - that's the whole point, since DUML's self-described
length/CRC can't be used to validate DUML's own framing.

Usage: python3 -I scripts/re/aoa_relay_server.py [--port 9900]
Point the app's "Diag relay host:port" field at this machine's LAN IP:port.
Log: captures/sessions/<today>/aoa_relay_server.log (raw hex, all kinds) and
     captures/sessions/<today>/aoa_relay_frames.log (decoded from AoaMux's own output).
Ground truth: captures/sessions/<today>/aoa_relay_frames_raw.log - the same decode run
     independently over the raw UDP stream, so AoaMux's own demuxing can be diffed
     against it instead of trusted blindly.
Command FIFO: tmp/aoa_send.fifo (created on startup; one hex-encoded frame per line)
"""
import argparse
import os
import socket
import struct
import sys
import threading
import time
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_proto import repo_root, session_log_dir  # noqa: E402
from aoa_mux import AoaMux, CAMERA_VIDEO, COMMAND  # noqa: E402
from relay_records import RecordParser, command_verdict, ENVELOPE, DISCARDED  # noqa: E402


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
    """Remove the 8-byte AOA envelope before parsing commands or exporting video.

    Command channel 0x5749 contains DUML; camera channel 0x574a contains video.
    H.264 start codes and NALs can span multiple AOA envelopes and TCP chunks.
    """

    def __init__(self, on_video=None):
        self.mux = AoaMux()
        self.on_video = on_video
        self.buf = bytearray()
        self.duml_bytes = 0
        self.video_bytes = 0

    def feed(self, data, log_fn):
        for packet in self.mux.feed(data):
            if packet.channel == CAMERA_VIDEO:
                self.video_bytes += len(packet.payload)
                if self.on_video is not None:
                    self.on_video(packet.payload)
            elif packet.channel == COMMAND:
                self.buf.extend(packet.payload)
                self._commands(log_fn)

    def _commands(self, log_fn):
        i = 0
        n = len(self.buf)
        while i < n:
            b = self.buf[i]
            if b == 0x55:
                if i + 4 > n:
                    break
                length = self.buf[i + 1] | ((self.buf[i + 2] & 0x03) << 8)
                if length >= 13 and crc8(0x77, self.buf[i:i + 3]) == self.buf[i + 3]:
                    if i + length > n:
                        break
                    frame = bytes(self.buf[i:i + length])
                    if (crc8(0x77, frame[:3]) == frame[3]
                            and crc16(0x3692, frame[:-2]) == int.from_bytes(frame[-2:], "little")):
                        self._decode(frame, log_fn)
                        self.duml_bytes += length
                        i += length
                        continue
            i += 1
        del self.buf[:i]

    def _decode(self, frame, log_fn):
        sender, receiver = frame[4], frame[5]
        seq = frame[6] | (frame[7] << 8)
        ctype = frame[8]
        verdict = command_verdict(frame)
        if not verdict['accepted']:
            log_fn(f"seq={seq} type={ctype:#04x} unsupported DUML semantics wire={frame.hex()}")
            return
        cset, cid = verdict['cmdSet'], verdict['cmdId']
        payload = verdict['payload']
        log_fn(f"sender={sender:#04x} receiver={receiver:#04x} seq={seq} type={ctype:#04x} "
               f"set={cset:#04x} id={cid:#04x} protection={verdict['protection']} payload={payload}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=9900)
    ap.add_argument("--video-out", help="save only demultiplexed camera H.264 payloads to this file")
    ap.add_argument("--input-format", choices=['records', 'raw'], default='records',
                    help='v1 phone records (default); raw for older apps only')
    args = ap.parse_args()

    video_out = open(args.video_out, 'wb', buffering=0) if args.video_out else None

    log_dir = session_log_dir()
    rawf = open(os.path.join(log_dir, "aoa_relay_server.log"), "a", buffering=1)
    framef = open(os.path.join(log_dir, "aoa_relay_frames.log"), "a", buffering=1)
    framef_raw = open(os.path.join(log_dir, "aoa_relay_frames_raw.log"), "a", buffering=1)

    def log(line):
        print(line, flush=True)
        rawf.write(line + "\n")

    def logframe(line):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        full = f"{ts} {line}"
        print("FRAME " + full, flush=True)
        framef.write(full + "\n")

    def logframe_raw(line):
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        full = f"{ts} {line}"
        print("RAWFRAME " + full, flush=True)
        framef_raw.write(full + "\n")

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

    # Ground-truth raw stream: UDP on port+1, one datagram per accessory byte chunk,
    # verbatim, before AoaMux sees it. Long-lived (not per-TCP-connection) since it's
    # independent of the TCP relay entirely - see udp_raw_relay.dart.
    raw_framer = StreamDemuxer()
    raw_seq_state = {"last": None}

    def udp_listener():
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        udp.bind(("0.0.0.0", args.port + 1))
        log(f"=== raw ground-truth UDP listener on 0.0.0.0:{args.port + 1} ===")
        while True:
            datagram, addr = udp.recvfrom(1024 * 1024 + 8)
            if len(datagram) < 8:
                log(f"=== raw UDP: {len(datagram)}B datagram from {addr}, too short for header ===")
                continue
            seq, stated_crc = struct.unpack_from("<II", datagram, 0)
            payload = datagram[8:]
            actual_crc = zlib.crc32(payload)
            if actual_crc != stated_crc:
                log(f"=== raw UDP: CRC mismatch seq={seq} stated={stated_crc:#010x} "
                    f"actual={actual_crc:#010x} - datagram corrupted in transit ===")
                continue
            last = raw_seq_state["last"]
            if last is not None and seq != (last + 1) & 0xffffffff:
                log(f"=== raw UDP: sequence gap, expected {(last + 1) & 0xffffffff} got {seq} "
                    f"- dropped/reordered datagram(s) ===")
            raw_seq_state["last"] = seq
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            log(f"{ts} RAWUDP seq={seq} +{len(payload)}B {payload.hex()}")
            raw_framer.feed(payload, logframe_raw)

    threading.Thread(target=udp_listener, daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.port))
    srv.listen(1)
    log(f"=== listening on 0.0.0.0:{args.port}, waiting for the phone ===")

    while True:
        conn, addr = srv.accept()
        log(f"=== connection from {addr} ===")
        # Telemetry pushes arrive every tens of ms while the phone is actually streaming
        # (duml_telemetry.py's own observed rate) - 30s is a "something is wrong, not just
        # a brief lull" threshold (~1000x that rate), not a tight bound on normal traffic.
        # Without this, a connection that goes silent without closing (seen 2026-10-24:
        # the phone reconnected, the server logged it, then nothing for 14+ minutes with
        # no exception and no exit - recv() was just blocked forever) wedges the single-
        # connection accept loop permanently, since nothing else is waiting on srv.accept().
        conn.settimeout(30)
        with lock:
            state["conn"] = conn
        records = RecordParser()
        discarded_bytes = 0
        framer = StreamDemuxer(on_video=video_out.write if video_out else None)
        def received(raw):
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            log(f"{ts} +{len(raw)}B {raw.hex()}")
            framer.feed(raw, logframe)
        try:
            while True:
                data = conn.recv(4096)
                if not data:
                    break
                if args.input_format == 'raw':
                    received(data)
                    continue
                for kind, channel, payload in records.feed(data):
                    if kind in (ENVELOPE, DISCARDED):
                        received(payload)
                        if kind == DISCARDED:
                            discarded_bytes += len(payload)
                            log(f'=== phone discarded {len(payload)} USB bytes ===')
            if args.input_format == 'records':
                records.finish()
        except TimeoutError:
            log(f'=== no data for 30s from {addr}, assuming stalled - dropping connection '
                f'(waiting for a fresh one to accept) ===')
        except (OSError, ValueError, KeyError, TypeError) as error:
            log(f'=== relay protocol error: {error} ===')
        finally:
            log(f'=== phone discarded total={discarded_bytes}B ===')
            with lock:
                if state["conn"] is conn:
                    state["conn"] = None
            conn.close()
            log(f"=== {addr} disconnected ===")


if __name__ == "__main__":
    main()
