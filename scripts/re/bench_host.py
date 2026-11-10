#!/usr/bin/env python3
"""Host side of the AOA bench app (app/awto_dji_app/lib/bench). The app is a TCP client of
this asyncio server; JSON lines both ways (protocol: docs/phone-bridge-operator-guide.md
"AOA bench app"). Python API for test scripts + CLI + the test-suite runner.

  python3 -I scripts/re/bench_host.py --listen 9910 --tail
  python3 -I scripts/re/bench_host.py --cmd ping
  python3 -I scripts/re/bench_host.py --suite size_sweep --peer none
Log: tmp/logs/bench_host.log
API: BenchHost.start(), wait_for_state(pred, timeout), send_cmd(dict), latest_state(),
     log_lines(), plus wait_for_result(), ping(), results().
Suites take a Peer (the other end of the USB cable: Cynthion / t600_rc_emulator); the
pure-Python catalog is aoa_testkit.py.
"""
import argparse
import asyncio
import json
import logging
import os
import random
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import aoa_testkit as tk  # noqa: E402

DEFAULT_PORT = 9910  # free of the repo's other ports (aoa_relay_server.py uses 9900/9901)
log = logging.getLogger("bench_host")


def _repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env:
        return env
    import subprocess
    return subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True,
                                   cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def _setup_logging(path=None, console=False):
    path = path or os.path.join(_repo_root(), "tmp", "logs", "bench_host.log")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handlers = [logging.FileHandler(path)]
    if console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(level=logging.INFO, handlers=handlers, force=True,
                        format="%(asctime)s %(message)s")
    return path


def compact(state):
    """One dashboard line from a `state` message."""
    u, p, m = state.get("usb", {}), state.get("power", {}), state.get("msgs", {})
    port, host, mode = state.get("port", {}), state.get("host", {}), state.get("mode", {})
    return (f"port={port.get('state')} usb={'att' if u.get('attached') else 'det'}"
            f"{'+perm' if u.get('permission') else ''} pwr={p.get('plugged')}/{p.get('charging')} "
            f"spd={state.get('speed', {}).get('label')} "
            f"msgs={m.get('per_s_1', 0):.1f}/s {m.get('bytes_per_s_1', 0):.0f}B/s tot={m.get('total')} "
            f"crc_bad={m.get('crc_bad')} mode={mode.get('m')} t{mode.get('test')} "
            f"fr={mode.get('frames')} bad={mode.get('bad')} pass={mode.get('pass')} "
            f"host_rtt={host.get('rtt_ms')}")


_DISCRETE = (("port", "state"), ("usb", "attached"), ("usb", "permission"), ("power", "plugged"),
             ("mode", "m"), ("mode", "pass"), ("mode", "first_mismatch"), ("host", "connected"))


def _discrete(state):
    return tuple(state.get(a, {}).get(b) for a, b in _DISCRETE)


class BenchHost:
    """asyncio TCP server on a background thread, synchronous API on top."""

    def __init__(self, port=DEFAULT_PORT, bind="0.0.0.0", print_changes=False, log_path=None):
        self.port, self.bind, self.print_changes = port, bind, print_changes
        self._cv = threading.Condition()
        self._state = None
        self._logs = []
        self._results = []
        self._rx = {"count": 0, "bad": 0, "bytes": 0}
        self._hello = None
        self._pongs = {}
        self._writer = None
        self._loop = None
        self._server = None
        self._ping_id = 0
        self._connected = False
        self._last_discrete = None
        _setup_logging(log_path)

    # -- lifecycle ---------------------------------------------------------------------
    def start(self):
        """Start listening; returns the bound port. Bound: 5 s for the loop thread to bind
        (a local bind takes ms; 5 s = lots of margin, expiry raises)."""
        ready = threading.Event()
        err = []

        def run():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._server = self._loop.run_until_complete(
                    asyncio.start_server(self._on_client, self.bind, self.port))
                self.port = self._server.sockets[0].getsockname()[1]
            except Exception as e:  # noqa: BLE001
                err.append(e)
                ready.set()
                return
            ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True, name="bench_host")
        self._thread.start()
        if not ready.wait(5):
            raise TimeoutError("bench_host: server did not bind within 5 s")
        if err:
            raise err[0]
        log.info("listening on %s:%d", self.bind, self.port)
        return self.port

    def stop(self):
        if self._loop is None:
            return

        async def shut():
            if self._writer:
                self._writer.close()
            self._server.close()
            await self._server.wait_closed()

        asyncio.run_coroutine_threadsafe(shut(), self._loop).result(5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(5)
        self._loop.close()
        self._loop = None

    # -- protocol ---------------------------------------------------------------------------
    async def _on_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        log.info("app connected from %s", peer)
        with self._cv:
            if self._writer:
                self._writer.close()
            self._writer, self._connected = writer, True
            self._cv.notify_all()
        try:
            while True:
                line = await reader.readline()
                if not line:
                    break
                self._on_line(line.decode("utf-8", "replace").strip())
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            log.info("app disconnected")
            with self._cv:
                if self._writer is writer:
                    self._writer, self._connected = None, False
                self._cv.notify_all()
            writer.close()

    def _on_line(self, line):
        try:
            m = json.loads(line)
        except json.JSONDecodeError:
            log.warning("bad json from app: %r", line[:200])
            return
        t = m.get("t")
        with self._cv:
            if t == "hello":
                self._hello = m
            elif t == "state":
                self._state = m
                d = _discrete(m)
                if d != self._last_discrete:
                    self._last_discrete = d
                    line_ = compact(m)
                    log.info("STATE %s", line_)
                    if self.print_changes:
                        print(line_, flush=True)
            elif t == "log":
                self._logs.append(m)
                log.info("APP %s %s %s", m.get("ts"), m.get("lvl"), m.get("msg"))
                if self.print_changes:
                    print(f"  app {m.get('lvl')} {m.get('msg')}", flush=True)
            elif t == "rx":
                self._rx["count"] += 1
                self._rx["bytes"] += m.get("len", 0)
                self._rx["bad"] += 0 if m.get("crc_ok") else 1
            elif t == "result":
                self._results.append(m)
                log.info("RESULT %s", json.dumps(m))
                if self.print_changes:
                    print("  RESULT", json.dumps(m), flush=True)
            elif t == "pong":
                self._pongs[m.get("id")] = time.monotonic()
            elif t == "ping":  # app-initiated: answer so the app can show RTT
                self._send_nowait({"cmd": "pong", "id": m.get("id")})
            self._cv.notify_all()

    def _send_nowait(self, obj):
        w = self._writer
        if w is None:
            raise ConnectionError("no app connected")
        data = (json.dumps(obj) + "\n").encode()
        self._loop.call_soon_threadsafe(w.write, data)
        log.info("CMD %s", json.dumps(obj))

    # -- API -------------------------------------------------------------------------------------
    def send_cmd(self, cmd):
        """Send one command dict to the app. Raises ConnectionError if no app is attached."""
        self._send_nowait(cmd)

    def latest_state(self):
        with self._cv:
            return self._state

    def log_lines(self):
        with self._cv:
            return [f"{m.get('ts')} {m.get('lvl')} {m.get('msg')}" for m in self._logs]

    def results(self):
        with self._cv:
            return list(self._results)

    def rx_stats(self):
        with self._cv:
            return dict(self._rx)

    def hello(self):
        with self._cv:
            return self._hello

    def _wait(self, pred, timeout, what):
        deadline = time.monotonic() + timeout
        with self._cv:
            while True:
                v = pred()
                if v:
                    return v
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError(f"bench_host: {what} not seen within {timeout} s")
                self._cv.wait(left)

    def wait_connected(self, timeout):
        """Wait for the app's TCP connect. Expected: seconds after `am start`; caller bounds."""
        return self._wait(lambda: self._connected, timeout, "app connection")

    def wait_for_state(self, predicate, timeout):
        """Block until predicate(state_dict) is true for the latest state (checked on every
        state message, which arrive at 2 Hz and on change). Raises TimeoutError."""
        def check():
            return self._state if self._state is not None and predicate(self._state) else None
        return self._wait(check, timeout, "state predicate")

    def wait_for_result(self, predicate, timeout, since=0):
        """Block for a `result` message (index >= since) matching predicate."""
        def check():
            for r in self._results[since:]:
                if predicate(r):
                    return r
            return None
        return self._wait(check, timeout, "result")

    def ping(self, timeout=2.0):
        """Round trip to the app in ms. 2 s: LAN RTT is ~10 ms, WiFi power-save wake <300 ms."""
        self._ping_id += 1
        pid = self._ping_id
        t0 = time.monotonic()
        self.send_cmd({"cmd": "ping", "id": pid})
        self._wait(lambda: pid in self._pongs, timeout, "pong")
        return (self._pongs.pop(pid) - t0) * 1000


# ---- peer (the other end of the USB cable) ------------------------------------------------------

class PeerTimeout(Exception):
    pass


class Peer:
    """Accessory-host end. Implemented by the Cynthion shell driver / t600_rc_emulator
    adapter / a test loopback. One call = one USB transfer."""
    name = "peer"
    max_packet = 512

    def tx(self, data, timeout=2.0):
        """Bulk-out `data` as one transfer (b'' = zero-length packet)."""
        raise NotImplementedError

    def rx(self, timeout=2.0):
        """Bulk-in one transfer: bytes, b'' for a ZLP, None if nothing within timeout."""
        raise NotImplementedError


class NullPeer(Peer):
    name = "none"


class EmulatorPeer(Peer):
    """Adapter over t600_rc_emulator.Backend (read_bulk/write_bulk)."""
    name = "emulator"

    def __init__(self, backend, max_packet=512):
        self.b, self.max_packet = backend, max_packet

    def tx(self, data, timeout=2.0):
        self.b.write_bulk(data, int(timeout * 1000))

    def rx(self, timeout=2.0):
        return self.b.read_bulk(65536, int(timeout * 1000)) or None


# ---- suites -----------------------------------------------------------------------------------------

class Result:
    def __init__(self, name, status, **detail):
        self.name, self.status, self.detail = name, status, detail

    def __repr__(self):
        return f"{self.status:4} {self.name} {json.dumps(self.detail, default=str)}"


PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
STATE_WAIT_S = 2.0       # state is pushed immediately on mode change; <100 ms on LAN, 20x
THROUGHPUT_WINDOW_S = tk.THROUGHPUT_WINDOW_S  # 2 s: > 10 state ticks, filters ramp-up; 20 sizes x 2 s = 40 s total
SLOWEST_BYTES_PER_S = 100_000  # slowest plausible full-speed accessory rate, 10x under the ceiling


_tid = [100]


def _new_tid():
    """Unique test id per run: _set_mode must not be satisfied by the previous run's state
    (same mode + id), or data races the mode switch."""
    _tid[0] += 1
    return _tid[0]


def _bound(total_bytes):
    """Wait bound for the app to have counted total_bytes: 1 s (2 state ticks) + at the
    slowest plausible rate. Expiry = data lost or stalled -> FAIL."""
    return 1.0 + total_bytes / SLOWEST_BYTES_PER_S


def _transfers(size, count, seed, test_id, first_seq=0):
    out = []
    for i in range(count):
        seq = (first_seq + i) & tk.MASK
        if size == 0:
            out.append(b"")
        elif size < tk.MIN_FRAME:
            out.append(tk.short_transfer(size, seed, seq, test_id))
        else:
            out.append(tk.build_frame(size, tk.P_ADDR, seed, seq, test_id))
    return out


def _set_mode(host, **p):
    host.send_cmd({"cmd": "mode", **p})
    host.wait_for_state(lambda s: s.get("mode", {}).get("m") == p["m"] and
                        s["mode"].get("test") == p.get("test", 0), STATE_WAIT_S)


def _poll_result(host, test_id, mode, pred, bound):
    """Ask for the app's verdict until pred(result) holds or `bound` s pass (each ask waits
    <= 1 s: the app answers in ms; the loop covers data still in flight through Android's
    reader thread). Returns the last result seen; raises TimeoutError if none arrived."""
    deadline = time.monotonic() + bound
    last = None
    while True:
        n = len(host.results())
        host.send_cmd({"cmd": "result"})
        try:
            last = host.wait_for_result(lambda r: r.get("test") == test_id and r.get("mode") == mode,
                                        1.0, since=n)
        except TimeoutError:
            if time.monotonic() >= deadline:
                raise
            continue
        if pred(last) or time.monotonic() >= deadline:
            return last


def _finish_sink(host, test_id, expect_total_bytes, pred):
    """Wait until the grid shows the data counted, then fetch the app's verdict."""
    host.wait_for_state(pred, _bound(expect_total_bytes))
    return _poll_result(host, test_id, "sink", lambda r: True, STATE_WAIT_S)


def run_to_app(host, peer, name, transfers, test_id, expect, seed):
    """Peer -> app: sink the transfers; `expect` = result keys that must reach these values."""
    try:
        _set_mode(host, m="sink", test=test_id, seed=seed)
        for t in transfers:
            peer.tx(t)
        total = sum(len(t) for t in transfers)
        r = _poll_result(host, test_id, "sink",
                         lambda r: all((r.get(k) or 0) >= v for k, v in expect.items()),
                         _bound(total))
    except (TimeoutError, PeerTimeout) as e:
        return Result(name, FAIL, error=str(e))
    bad = {k: (r.get(k), v) for k, v in expect.items() if r.get(k) != v}
    ok = r.get("pass") is not False and not bad
    return Result(name, PASS if ok else FAIL, result=r, mismatched_expectations=bad)


def run_from_app(host, peer, name, size, count, test_id, seed, pattern="addr"):
    """App -> peer: app sources `count` transfers; peer must read them intact."""
    chk = tk.Checker(test_id)
    n = len(host.results())
    try:
        host.send_cmd({"cmd": "mode", "m": "source", "test": test_id, "size": size,
                       "count": count, "seed": seed, "pattern": pattern})
        want = count * size
        deadline = time.monotonic() + _bound(want)
        got = 0
        short = 0
        while got < want and time.monotonic() < deadline:
            c = peer.rx(timeout=min(1.0, max(0.05, deadline - time.monotonic())))
            if c is None:
                continue
            if size < tk.MIN_FRAME:
                short += len(c) > 0
            else:
                chk.feed(c)
            got += len(c)
        r = host.wait_for_result(lambda r: r.get("test") == test_id and r.get("mode") == "source",
                                 STATE_WAIT_S + 1.0, since=n)
    except (TimeoutError, PeerTimeout, NotImplementedError) as e:
        return Result(name, FAIL, error=str(e))
    rep = chk.report.as_dict()
    ok = got == want and r.get("pass") and (size < tk.MIN_FRAME or rep["pass"])
    return Result(name, PASS if ok else FAIL, got_bytes=got, want_bytes=want, report=rep, app=r)


def suite_size_sweep(host, peer, seed=1, count=3, directions=("to_app", "from_app")):
    out = []
    for i, size in enumerate(tk.SIZES):
        tid, tid_src = _new_tid(), _new_tid()
        if "to_app" in directions:
            exp = ({"zlp": count} if size == 0 else {"short": count} if size < tk.MIN_FRAME
                   else {"frames": count})
            out.append(run_to_app(host, peer, f"size_sweep:to_app:{size}"
                                  f"{':ZLP' if size == 0 else ''}",
                                  _transfers(size, count, seed, tid), tid, exp, seed))
        if "from_app" in directions:
            out.append(run_from_app(host, peer, f"size_sweep:from_app:{size}", size, count,
                                    tid_src, seed))
    return out


def suite_zero_length(host, peer, seed=1, count=3):
    """Frame-level empty payload (24 B AOAT frame) vs USB-level ZLP after exact multiples of
    the bulk max packet. ZLP cases are reported apart: a missing ZLP is the 'transfer never
    ends' failure, a different cause from a bad length field."""
    out = []
    tid = _new_tid()
    out.append(run_to_app(host, peer, "zero_length:frame_empty_payload",
                          _transfers(tk.MIN_FRAME, count, seed, tid), tid, {"frames": count}, seed))
    for i, size in enumerate(tk.zlp_sizes((peer.max_packet,))):
        for term in ("none", "zlp"):
            tid = _new_tid()
            ts = []
            for t in _transfers(size, count, seed, tid):
                ts.append(t)
                if term == "zlp":
                    ts.append(b"")
            exp = {"frames": count}
            if term == "zlp":
                exp["zlp"] = count
            out.append(run_to_app(host, peer, f"zero_length:ZLP:to_app:{size}:terminated_by_{term}",
                                  ts, tid, exp, seed))
        out.append(run_from_app(host, peer, f"zero_length:ZLP:from_app:{size}", size, count,
                                _new_tid(), seed))
    return out


def suite_throughput(host, peer, seed=1, window_s=THROUGHPUT_WINDOW_S):
    out = []
    for i, size in enumerate(tk.THROUGHPUT_SIZES):
        tid, tid_src = _new_tid(), _new_tid()
        name = f"throughput:to_app:{size}"
        try:
            _set_mode(host, m="sink", test=tid, seed=seed)
            t0, seq, sent = time.monotonic(), 0, 0
            while time.monotonic() - t0 < window_s:
                peer.tx(tk.build_frame(size, tk.P_ADDR, seed, seq, tid))
                seq += 1
                sent += size
            el = time.monotonic() - t0
            host.wait_for_state(lambda s: s["mode"].get("bytes", 0) >= sent, _bound(sent))
            r = _poll_result(host, tid, "sink", lambda r: True, STATE_WAIT_S)
            out.append(Result(name, PASS if r.get("pass") else FAIL, bytes_per_s=sent / el,
                              window_s=el, app=r))
        except (TimeoutError, PeerTimeout) as e:
            out.append(Result(name, FAIL, error=str(e)))
        name = f"throughput:from_app:{size}"
        try:
            n = len(host.results())
            host.send_cmd({"cmd": "mode", "m": "source", "test": tid_src, "size": size,
                           "count": 0, "dur_ms": int(window_s * 1000), "seed": seed})
            t0, got = time.monotonic(), 0
            while time.monotonic() - t0 < window_s + 1.0:
                c = peer.rx(timeout=0.2)
                got += len(c or b"")
            r = host.wait_for_result(lambda r: r.get("test") == tid_src and r.get("mode") == "source",
                                     STATE_WAIT_S, since=n)
            out.append(Result(name, PASS if r.get("pass") else FAIL, peer_bytes=got,
                              app_bytes_per_s=r.get("bytes_per_s"), window_s=window_s))
        except (TimeoutError, PeerTimeout, NotImplementedError) as e:
            out.append(Result(name, FAIL, error=str(e)))
    return out


def suite_limits(host, peer, seed=1):
    out = []
    # largest transfer accepted: double from 128 KiB; stop at first failure or 4 MiB
    size, largest = 1 << 17, None
    while size <= 1 << 22:
        tid = _new_tid()
        r = run_to_app(host, peer, f"limits:largest_transfer:{size}",
                       _transfers(size, 1, seed, tid), tid, {"frames": 1}, seed)
        out.append(r)
        if r.status != PASS:
            break
        largest, size = size, size * 2
    out.append(Result("limits:largest_transfer_accepted", PASS if largest else FAIL, bytes=largest))
    tid = _new_tid()
    out.append(run_to_app(host, peer, "limits:many_tiny_back_to_back:10000x24B",
                          _transfers(tk.MIN_FRAME, 10000, seed, tid), tid, {"frames": 10000}, seed))
    # idle then burst: 5 s > Android's 2 s USB autosuspend delay (2.5x)
    try:
        tid = _new_tid()
        _set_mode(host, m="sink", test=tid, seed=seed)
        time.sleep(5.0)
        for t in _transfers(512, 200, seed, tid):
            peer.tx(t)
        r = _finish_sink(host, tid, 200 * 512, lambda s: s["mode"].get("frames", 0) >= 200)
        out.append(Result("limits:idle_5s_then_burst_200x512", PASS if r.get("pass") else FAIL, app=r))
    except (TimeoutError, PeerTimeout) as e:
        out.append(Result("limits:idle_5s_then_burst_200x512", FAIL, error=str(e)))
    return out


def suite_fuzz(host, peer, seed=None, steps=200):
    """to_app fuzz; the oracle is tk.SinkModel run over the same chunks. Seed is logged;
    `--fuzz-seed N` replays the identical plan and bytes."""
    seed = random.SystemRandom().randrange(1, 1 << 31) if seed is None else seed
    log.info("FUZZ seed=%d steps=%d", seed, steps)
    print(f"fuzz seed={seed} (replay with --fuzz-seed {seed})", flush=True)
    tid = _new_tid()
    model = tk.SinkModel(tid)
    plan = tk.fuzz_plan(seed, steps)
    try:
        _set_mode(host, m="sink", test=tid, seed=seed)
        total = 0
        for st in plan:
            wire, _good = tk.fuzz_wire(st, seed, tid)
            model.feed(wire)
            peer.tx(wire)
            total += len(wire)
            if st["gap_ms"]:
                time.sleep(st["gap_ms"] / 1000)
        exp = model.report()
        r = _poll_result(host, tid, "sink", lambda r: r.get("frames") == exp["frames"]
                         and r.get("bad_frames") == exp["bad_frames"]
                         and r.get("resync_bytes") == exp["resync_bytes"]
                         and r.get("zlp") == exp["zlp"] and r.get("short") == exp["short"],
                         _bound(total))
    except (TimeoutError, PeerTimeout) as e:
        return [Result("fuzz", FAIL, seed=seed, error=str(e))]
    keys = ("frames", "bad_frames", "crc_bad", "seq_gaps", "seq_dups", "resync_bytes", "short", "zlp")
    diff = {k: {"app": r.get(k), "model": exp.get(k)} for k in keys if r.get(k) != exp.get(k)}
    return [Result("fuzz", FAIL if diff else PASS, seed=seed, differences=diff, app=r, model=exp)]


def suite_soak(host, peer, seed=1, minutes=1.0, size=512, window_s=10.0):
    """Stream for `minutes`; seq starts 0xFFFFFF00 so the u32 seq wrap happens in the first
    256 frames and must not be counted as a gap. Per-window rate spread flags drift."""
    tid = _new_tid()
    first = 0xFFFFFF00
    rates = []
    try:
        _set_mode(host, m="sink", test=tid, seed=seed)
        t_end = time.monotonic() + minutes * 60
        seq, sent = first, 0
        while time.monotonic() < t_end:
            w0, wb = time.monotonic(), 0
            while time.monotonic() - w0 < window_s and time.monotonic() < t_end:
                peer.tx(tk.build_frame(size, tk.P_ADDR, seed, seq & tk.MASK, tid))
                seq += 1
                wb += size
            rates.append(wb / (time.monotonic() - w0))
            sent += wb
        r = _finish_sink(host, tid, sent, lambda s: s["mode"].get("bytes", 0) >= sent)
    except (TimeoutError, PeerTimeout) as e:
        return [Result("soak", FAIL, error=str(e))]
    med = sorted(rates)[len(rates) // 2]
    # 50%: USB scheduling on a phone is noisy; this flags a stall/collapse, not jitter
    drift = max((abs(x - med) / med for x in rates), default=0)
    ok = r.get("pass") and r.get("seq_gaps") == 0 and r.get("seq_dups") == 0 and drift < 0.5
    return [Result("soak", PASS if ok else FAIL, windows=len(rates), median_bytes_per_s=med,
                   max_drift=drift, app=r)]


SUITES = {"size_sweep": suite_size_sweep, "zero_length": suite_zero_length,
          "throughput": suite_throughput, "limits": suite_limits, "fuzz": suite_fuzz,
          "soak": suite_soak}


def run_suites(host, peer, names, **kw):
    results = []
    for n in names:
        fn = SUITES[n]
        import inspect
        params = inspect.signature(fn).parameters
        results.extend(fn(host, peer, **{k: v for k, v in kw.items() if k in params}))
    for r in results:
        log.info("SUITE %r", r)
    return results


# ---- CLI --------------------------------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--listen", type=int, default=DEFAULT_PORT)
    ap.add_argument("--tail", action="store_true", help="print state changes/logs/results until ^C")
    ap.add_argument("--cmd", help="send one command (ping|stats_reset|disconnect|reconnect|echo-on|"
                    "echo-off|result|mode:<json>|raw JSON) and print the outcome")
    ap.add_argument("--connect-timeout", type=float, default=30.0,
                    help="wait for the app to connect (am start to TCP connect is seconds)")
    ap.add_argument("--suite", action="append", choices=sorted(SUITES) + ["all"])
    ap.add_argument("--peer", choices=["none"], default="none")
    ap.add_argument("--fuzz-seed", type=int)
    ap.add_argument("--fuzz-steps", type=int, default=200)
    ap.add_argument("--soak-minutes", type=float, default=1.0)
    a = ap.parse_args(argv)
    path = _setup_logging(console=False)
    host = BenchHost(a.listen, print_changes=a.tail)
    print(f"bench_host listening on :{host.start()} (log {path})", flush=True)
    try:
        if a.cmd or a.suite:
            host.wait_connected(a.connect_timeout)
        if a.cmd:
            c = a.cmd
            if c == "ping":
                print(f"ping rtt {host.ping():.1f} ms")
            else:
                obj = {"echo-on": {"cmd": "echo", "on": True}, "echo-off": {"cmd": "echo", "on": False}}.get(c)
                if obj is None:
                    obj = json.loads(c[5:]) if c.startswith("mode:") else (
                        json.loads(c) if c.startswith("{") else {"cmd": c})
                    if c.startswith("mode:"):
                        obj = {"cmd": "mode", **obj}
                host.send_cmd(obj)
                st = host.wait_for_state(lambda s: True, 2.0)
                print(compact(st))
        if a.suite:
            names = sorted(SUITES) if "all" in a.suite else a.suite
            res = run_suites(host, NullPeer(), names, seed=a.fuzz_seed, steps=a.fuzz_steps,
                             minutes=a.soak_minutes)
            for r in res:
                print(r)
            return 0 if all(r.status == PASS for r in res) else 1
        if a.tail:
            while True:
                time.sleep(3600)  # the server thread prints; this thread only keeps the process alive
    except KeyboardInterrupt:
        pass
    finally:
        host.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
