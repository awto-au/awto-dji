"""In-process stand-in for the phone bench app, for bench_host tests (no phone, no USB).
Speaks the same JSON-lines protocol and mirrors the Dart mode engine's observable
behaviour (sink via aoa_testkit.SinkModel, source, echo). LoopPeer is the matching
Peer: tx() delivers straight to the fake app, rx() reads what the fake app sourced."""
import json
import queue
import socket
import threading
import time

import aoa_testkit as tk
from bench_host import Peer, PeerTimeout


class FakeApp:
    def __init__(self, port, state_period=0.05, host="127.0.0.1"):
        self.sock = socket.create_connection((host, port), timeout=3)
        self.sock.settimeout(None)
        self.lock = threading.Lock()
        self.cmds = []
        self.mode, self.params = "passive", {}
        self.model = None
        self.out = queue.Queue()          # bytes the app "wrote" on bulk-out
        self.echo_chunks = 0
        self.source_result = None
        self.drop_next = 0                # test hook: swallow N sink chunks (data loss)
        self.corrupt_next = None          # test hook: (offset) flip a byte in the next sink chunk
        self._stop = threading.Event()
        self._send({"t": "hello", "app": "fake-bench", "build": "test"})
        self._rd = threading.Thread(target=self._read, daemon=True)
        self._st = threading.Thread(target=self._ticker, args=(state_period,), daemon=True)
        self._rd.start()
        self._st.start()

    def _send(self, obj):
        with self.lock:
            try:
                self.sock.sendall((json.dumps(obj) + "\n").encode())
            except OSError:
                pass

    def log(self, msg, lvl="I"):
        self._send({"t": "log", "ts": "2026-11-02T00:00:00.000+10:00", "lvl": lvl, "msg": msg})

    def _result_body(self):
        tid = self.params.get("test", 0)
        if self.mode == "sink":
            body = self.model.report()
            body.update(test=tid, mode="sink")
            return body
        if self.mode == "source":
            return self.source_result
        return {"test": tid, "mode": self.mode, "pass": True, "frames": self.echo_chunks, "bytes": 0}

    def state(self):
        md = {"m": self.mode, "test": self.params.get("test", 0), "frames": 0, "bytes": 0,
              "bad": 0, "first_mismatch": None, "pass": None}
        if self.mode == "sink":
            r = self.model.report()
            fm = r["first_mismatch"]
            md.update(frames=r["frames"], bytes=r["bytes"], bad=r["bad_frames"],
                      first_mismatch=fm["offset"] if fm else None, **{"pass": r["pass"]})
        return {"t": "state", "usb": {"attached": True, "permission": True},
                "power": {"plugged": "usb", "charging": "charging"}, "speed": {"label": "fake"},
                "msgs": {"per_s_1": 0, "bytes_per_s_1": 0, "total": 0, "crc_bad": 0},
                "port": {"state": "connected"}, "host": {"connected": True}, "mode": md}

    def _ticker(self, period):
        while not self._stop.is_set():
            self._send(self.state())
            self._stop.wait(period)

    def _read(self):
        f = self.sock.makefile("r")
        for line in f:
            try:
                c = json.loads(line)
            except ValueError:
                continue
            self.cmds.append(c)
            self._cmd(c)

    def _cmd(self, c):
        k = c.get("cmd")
        if k == "ping":
            self._send({"t": "pong", "id": c["id"]})
        elif k == "result":
            self._send({"t": "result", **self._result_body()})
        elif k == "mode":
            self.mode, self.params = c["m"], c
            self.model = tk.SinkModel(c.get("test")) if c["m"] == "sink" else None
            self.echo_chunks = 0
            self._send(self.state())
            if c["m"] == "source":
                threading.Thread(target=self._source, args=(c,), daemon=True).start()

    def _source(self, c):
        size, count, seed, tid = c.get("size", 64), c.get("count", 1), c.get("seed", 1), c.get("test", 0)
        sent = 0
        for seq in range(count):
            if size == 0:
                f = b""
            elif size < tk.MIN_FRAME:
                f = tk.short_transfer(size, seed, seq, tid)
            else:
                f = tk.build_frame(size, tk.PATTERN_NAMES.get(c.get("pattern", "addr"), 0), seed, seq, tid)
            self.out.put(f)
            sent += len(f)
        self.source_result = {"test": tid, "mode": "source", "frames": count, "bytes": sent,
                              "pass": True, "done": True, "bytes_per_s": 0}
        self._send({"t": "result", **self.source_result})

    # called by LoopPeer
    def on_chunk(self, data):
        if self.mode == "sink":
            if self.drop_next:
                self.drop_next -= 1
                return
            if self.corrupt_next is not None and len(data) > self.corrupt_next:
                data = bytearray(data)
                data[self.corrupt_next] ^= 0x01
                data = bytes(data)
                self.corrupt_next = None
            self.model.feed(data)
        elif self.mode == "echo":
            self.echo_chunks += 1
            self.out.put(data)

    def close(self):
        self._stop.set()
        try:
            self.sock.shutdown(socket.SHUT_RDWR)
            self.sock.close()
        except OSError:
            pass


class LoopPeer(Peer):
    name = "loop"

    def __init__(self, app, max_packet=512):
        self.app, self.max_packet = app, max_packet
        self.sent = []

    def tx(self, data, timeout=2.0):
        self.sent.append(len(data))
        self.app.on_chunk(data)

    def rx(self, timeout=2.0):
        try:
            return self.app.out.get(timeout=timeout)
        except queue.Empty:
            return None
