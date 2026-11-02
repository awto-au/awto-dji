"""bench_host: API + suites against an in-process fake app (no phone, no hardware)."""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoa_testkit as tk
import bench_host as bh
from bench_fake_app import FakeApp, LoopPeer


@pytest.fixture
def rig(tmp_path):
    host = bh.BenchHost(port=0, bind="127.0.0.1", log_path=str(tmp_path / "bench_host.log"))
    port = host.start()
    app = FakeApp(port)
    host.wait_connected(3)
    host.wait_for_state(lambda s: True, 3)
    yield host, app, LoopPeer(app)
    app.close()
    host.stop()


def test_hello_state_log_rx(rig):
    host, app, _ = rig
    assert host.hello()["app"] == "fake-bench"
    assert host.latest_state()["port"]["state"] == "connected"
    app.log("hello world", "W")
    app._send({"t": "rx", "ch": 0x5749, "len": 21, "crc_ok": False})
    host._wait(lambda: host.log_lines() and host.rx_stats()["count"], 2, "log+rx")
    assert host.log_lines()[-1].endswith("W hello world")
    assert host.rx_stats() == {"count": 1, "bad": 1, "bytes": 21}


def test_ping_roundtrip(rig):
    host, *_ = rig
    rtt = host.ping(2)
    assert 0 <= rtt < 1000


def test_app_initiated_ping_is_answered(rig):
    host, app, _ = rig
    app._send({"t": "ping", "id": 42})
    t0 = time.monotonic()
    while time.monotonic() - t0 < 2 and not any(c.get("cmd") == "pong" for c in app.cmds):
        time.sleep(0.01)
    assert {"cmd": "pong", "id": 42} in app.cmds


def test_cmd_delivery(rig):
    host, app, _ = rig
    host.send_cmd({"cmd": "send", "hex": "55cc"})
    host.send_cmd({"cmd": "echo", "on": True})
    t0 = time.monotonic()
    while time.monotonic() - t0 < 2 and len(app.cmds) < 2:
        time.sleep(0.01)
    assert app.cmds[:2] == [{"cmd": "send", "hex": "55cc"}, {"cmd": "echo", "on": True}]


def test_wait_for_state_predicate_and_timeout(rig):
    host, app, _ = rig
    host.send_cmd({"cmd": "mode", "m": "sink", "test": 7})
    s = host.wait_for_state(lambda s: s["mode"]["m"] == "sink" and s["mode"]["test"] == 7, 2)
    assert s["mode"]["m"] == "sink"
    t0 = time.monotonic()
    with pytest.raises(TimeoutError):
        host.wait_for_state(lambda s: s["port"]["state"] == "streaming", 0.3)
    assert 0.25 < time.monotonic() - t0 < 1.0


def test_send_without_app_raises():
    host = bh.BenchHost(port=0, bind="127.0.0.1")
    host.start()
    try:
        with pytest.raises(ConnectionError):
            host.send_cmd({"cmd": "ping", "id": 1})
        with pytest.raises(TimeoutError):
            host.wait_connected(0.1)
    finally:
        host.stop()


def test_wait_for_result_and_disconnect(rig):
    host, app, _ = rig
    host.send_cmd({"cmd": "mode", "m": "sink", "test": 3})
    host.wait_for_state(lambda s: s["mode"]["m"] == "sink", 2)
    host.send_cmd({"cmd": "result"})
    r = host.wait_for_result(lambda r: r["test"] == 3, 2)
    assert r["mode"] == "sink" and r["pass"] is True
    app.close()
    host._wait(lambda: not host._connected, 2, "disconnect")


def test_compact_line():
    assert "port=connected" in bh.compact({"port": {"state": "connected"}, "msgs": {}})


# ---- suites ------------------------------------------------------------------------------------

def test_size_sweep_passes_both_directions(rig):
    host, app, peer = rig
    res = bh.suite_size_sweep(host, peer, count=2)
    assert len(res) == 2 * len(tk.SIZES)
    assert [r for r in res if r.status != bh.PASS] == []


def test_size_sweep_detects_loss(rig):
    host, app, peer = rig
    app.drop_next = 1
    res = bh.suite_size_sweep(host, peer, count=2, directions=("to_app",))
    # the first size (0, ZLP) loses a chunk and must not pass
    assert res[0].status == bh.FAIL


def test_corruption_localised_to_offset(rig):
    host, app, peer = rig
    app.corrupt_next = 20 + 100  # payload offset 100 of the first frame
    r = bh.run_to_app(host, peer, "corrupt", [tk.build_frame(512, tk.P_ADDR, 1, 0, 9)], 9,
                      {"frames": 1}, 1)
    assert r.status == bh.FAIL
    assert r.detail["result"]["first_mismatch"]["offset"] == 100


def test_zero_length_suite(rig):
    host, app, peer = rig
    res = bh.suite_zero_length(host, peer, count=2)
    assert [r for r in res if r.status != bh.PASS] == []
    names = [r.name for r in res]
    assert "zero_length:frame_empty_payload" in names
    assert any(n.startswith("zero_length:ZLP:to_app:512:terminated_by_zlp") for n in names)
    assert any("ZLP:to_app:64:" in n for n in names) is False  # max_packet 512 only


def test_zero_length_uses_peer_max_packet(rig):
    host, app, _ = rig
    peer = LoopPeer(app, max_packet=64)
    res = bh.suite_zero_length(host, peer, count=1)
    assert any("ZLP:to_app:64:" in r.name for r in res)
    assert [r for r in res if r.status != bh.PASS] == []


def test_throughput_suite(rig):
    host, app, peer = rig
    res = bh.suite_throughput(host, peer, window_s=0.2)
    assert [r for r in res if r.status != bh.PASS] == []
    to_app = [r for r in res if "to_app" in r.name]
    assert all(r.detail["bytes_per_s"] > 0 for r in to_app)


def test_limits_suite(rig, monkeypatch):
    host, app, peer = rig
    monkeypatch.setattr(bh.time, "sleep", lambda s: None)
    res = bh.suite_limits(host, peer)
    assert [r for r in res if r.status != bh.PASS] == []
    big = [r for r in res if r.name == "limits:largest_transfer_accepted"][0]
    assert big.detail["bytes"] == 1 << 22


def test_fuzz_replays_from_seed(rig):
    host, app, peer = rig
    a = bh.suite_fuzz(host, peer, seed=1234, steps=60)[0]
    sent_a = list(peer.sent)
    peer.sent.clear()
    b = bh.suite_fuzz(host, peer, seed=1234, steps=60)[0]
    assert a.status == b.status == bh.PASS, (a, b)
    assert a.detail["seed"] == 1234 and peer.sent == sent_a


def test_fuzz_flags_app_disagreement(rig):
    host, app, peer = rig
    app.drop_next = 1  # app loses a chunk the oracle counts
    r = bh.suite_fuzz(host, peer, seed=5, steps=40)[0]
    assert r.status == bh.FAIL and r.detail["differences"]


def test_soak_short_run_and_seq_wraps(rig):
    host, app, peer = rig
    r = bh.suite_soak(host, peer, minutes=0.05, window_s=0.5, size=512)[0]
    assert r.status == bh.PASS, r
    assert r.detail["app"]["seq_gaps"] == 0  # u32 wrap at 0xFFFFFFFF -> 0 is not a gap


def test_missing_peer_op_fails_not_hangs(rig):
    host, app, _ = rig
    r = bh.run_from_app(host, bh.NullPeer(), "x", 100, 1, 1, 1)
    assert r.status == bh.FAIL


def test_cli_cmd_ping(tmp_path, capsys, monkeypatch):
    import socket
    import threading
    monkeypatch.setenv("AWTO_DJI_REPO", str(tmp_path))
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    rc = []
    t = threading.Thread(target=lambda: rc.append(bh.main(["--listen", str(port), "--cmd", "ping",
                                                           "--connect-timeout", "5"])))
    t.start()
    app = None
    for _ in range(100):  # server binds within ms; bound 2 s
        try:
            app = FakeApp(port)
            break
        except OSError:
            time.sleep(0.02)
    t.join(10)
    if app:
        app.close()
    assert rc == [0]
    assert "ping rtt" in capsys.readouterr().out
