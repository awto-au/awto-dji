#!/usr/bin/env python3
"""Client for the bench app's TCP control port (default 6560; JSON lines; docs/phone-bridge-
operator-guide.md "Control port"). Normally reached through `./dev.py ctl`.

  python3 -I scripts/re/bench_ctl.py --host 192.168.25.125 mode echo
  python3 -I scripts/re/bench_ctl.py --host 127.0.0.1 --port 40001 mode source test=4 seed=9 size=512 count=100 pattern=prbs
Subcommands: ping | get | reset | result | mode <m> [k=v ...] | send <hex> | raw <json> | tail <s>
Every wait is bounded; a missing reply exits 1 naming the command and the limit.
"""
import argparse
import json
import socket
import sys
import time

DEFAULT_PORT = 6560
CONNECT_S = 3.0   # LAN TCP connect: <1 s expected (one SYN retransmit), 3x
REPLY_S = 2.0     # the app answers in ms; 2 s covers a UI-thread stall, ~100x LAN RTT


class CtlError(Exception):
    pass


class BenchCtl:
    def __init__(self, host, port=DEFAULT_PORT, connect_s=CONNECT_S):
        try:
            self.sock = socket.create_connection((host, port), timeout=connect_s)
        except OSError as e:
            raise CtlError(f"connect {host}:{port} failed within {connect_s}s: {e}") from None
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.buf = b""
        self.results = []   # pushed {t:result} messages, in order

    def close(self):
        self.sock.close()

    def _line(self, deadline):
        while b"\n" not in self.buf:
            left = deadline - time.monotonic()
            if left <= 0:
                raise socket.timeout
            self.sock.settimeout(left)
            d = self.sock.recv(65536)
            if not d:
                raise CtlError("app closed the control connection")
            self.buf += d
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def request(self, obj, timeout=REPLY_S):
        """Send one command; return (reply, rtt_ms). Pushed results are kept in self.results."""
        want = obj["cmd"]
        t0 = time.monotonic()
        self.sock.sendall((json.dumps(obj) + "\n").encode())
        deadline = t0 + timeout
        while True:
            try:
                m = self._line(deadline)
            except socket.timeout:
                raise CtlError(f"no reply to {want!r} within {timeout}s") from None
            if m.get("t") == "result":
                self.results.append(m)
            elif (m.get("t") == "reply" and m.get("cmd") in (want, "?")) or \
                    (want == "ping" and m.get("t") == "pong"):
                return m, (time.monotonic() - t0) * 1000

    def ping(self):
        return self.request({"cmd": "ping", "id": 1})[1]

    def mode(self, m, **params):
        reply, rtt = self.request({"cmd": "mode", "m": m, **params})
        reply["rtt_ms"] = round(rtt, 2)
        return reply

    def get(self):
        return self.request({"cmd": "get"})[0]

    def reset(self):
        return self.request({"cmd": "reset"})[0]

    def wait_result(self, pred, timeout):
        """Next pushed result (new or already seen) satisfying pred, within timeout."""
        deadline = time.monotonic() + timeout
        seen = 0
        while True:
            for r in self.results[seen:]:
                if pred(r):
                    return r
            seen = len(self.results)
            try:
                m = self._line(deadline)
            except socket.timeout:
                raise CtlError(f"no matching result within {timeout}s") from None
            if m.get("t") == "result":
                self.results.append(m)


def _val(v):
    try:
        return json.loads(v)
    except ValueError:
        return v


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("cmd", choices=["ping", "get", "reset", "result", "mode", "send", "raw", "tail"])
    ap.add_argument("args", nargs="*")
    a = ap.parse_args(argv)
    try:
        c = BenchCtl(a.host, a.port)
        try:
            if a.cmd == "ping":
                out = {"rtt_ms": round(c.ping(), 2)}
            elif a.cmd == "mode":
                if not a.args:
                    ap.error("mode needs a name: passive|echo|sink|source|duml")
                out = c.mode(a.args[0], **{k: _val(v) for k, _, v in (x.partition("=") for x in a.args[1:])})
            elif a.cmd == "send":
                out = c.request({"cmd": "send", "hex": a.args[0]})[0]
            elif a.cmd == "raw":
                out = c.request(json.loads(a.args[0]))[0]
            elif a.cmd == "tail":
                try:
                    c.wait_result(lambda r: False, float(a.args[0]))
                except CtlError:
                    pass  # window over: print what arrived
                out = c.results
            else:
                out = c.request({"cmd": a.cmd})[0]
        finally:
            c.close()
    except CtlError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print(json.dumps(out))
    return 0 if not isinstance(out, dict) or out.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
