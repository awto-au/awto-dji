"""Command construction for dev.py's phone/bench subcommands.
No phone, no flutter: dev._exec / dev._spawn are replaced by a fake that records argv."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("dev_under_test", REPO / "dev.py")
dev = importlib.util.module_from_spec(_spec)
sys.modules["dev_under_test"] = dev
_spec.loader.exec_module(dev)

DEVICES_ONE_WIFI = ("List of devices attached\n"
                    "192.168.25.50:37123    device product:blueline model:Pixel_3_XL device:blueline transport_id:1\n")
DEVICES_TWO = ("List of devices attached\n"
               "192.168.25.50:37123    device product:b model:Pixel_3_XL device:b transport_id:1\n"
               "ABC123    device usb:1-2 product:s model:SM_G960F device:starlte transport_id:2\n")
DEVICES_SAME_PHONE = ("List of devices attached\n"
                      "192.168.25.50:37123    device product:b model:Pixel_3_XL device:b transport_id:1\n"
                      "8A1X    device usb:1-2 product:b model:Pixel_3_XL device:b transport_id:2\n")
IP_ROUTE = ("192.168.25.50 dev wlp3s0 src 192.168.25.114 uid 1000 \n    cache \n")


class Fake:
    """Records argv; `replies` maps a substring of the joined argv to output."""

    def __init__(self):
        self.calls: list[list[str]] = []
        self.envs: list[dict | None] = []
        self.replies: dict[str, object] = {}
        self.hooks: list = []          # (substring, fn(argv)) run before the reply is chosen

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        self.envs.append(kw.get("env"))
        joined = " ".join(argv)
        for key, fn in self.hooks:
            if key in joined:
                fn(argv)
        for key, val in self.replies.items():
            if key in joined:
                if isinstance(val, dev.ExecResult):
                    return val
                return dev.ExecResult(0, val)
        return dev.ExecResult(0, "")

    def joined(self):
        return [" ".join(c) for c in self.calls]


@pytest.fixture
def fake(monkeypatch, tmp_path):
    f = Fake()
    monkeypatch.setattr(dev, "_exec", f)
    monkeypatch.setattr(dev.shutil, "which", lambda n: f"/usr/bin/{n}")
    monkeypatch.delenv("AWTO_PHONE", raising=False)
    monkeypatch.setattr(dev, "LOGS", tmp_path / "logs")
    monkeypatch.setattr(dev, "LOG", tmp_path / "logs" / "dev.log")
    return f


# ---- serial resolution -------------------------------------------------------------------

def test_parse_devices():
    d = dev.parse_devices(DEVICES_TWO)
    assert [x["serial"] for x in d] == ["192.168.25.50:37123", "ABC123"]
    assert d[0]["wireless"] and not d[1]["wireless"]
    assert d[0]["model"] == "Pixel_3_XL"


def test_explicit_serial_wins_over_env():
    assert dev.pick_serial("S1", "ENV", []) == "S1"


def test_env_serial_when_no_flag():
    assert dev.pick_serial(None, "ENV", dev.parse_devices(DEVICES_TWO)) == "ENV"


def test_single_device():
    assert dev.pick_serial(None, None, dev.parse_devices(DEVICES_ONE_WIFI)) == "192.168.25.50:37123"


def test_same_phone_twice_prefers_wireless():
    assert dev.pick_serial(None, None, dev.parse_devices(DEVICES_SAME_PHONE)) == "192.168.25.50:37123"


def test_several_devices_fails_with_list():
    with pytest.raises(dev.PhoneError) as e:
        dev.pick_serial(None, None, dev.parse_devices(DEVICES_TWO))
    msg = str(e.value)
    assert "ABC123" in msg and "192.168.25.50:37123" in msg and "--serial" in msg


def test_no_device_fails():
    with pytest.raises(dev.PhoneError):
        dev.pick_serial(None, None, [])


def test_unauthorized_device_is_not_usable():
    d = dev.parse_devices("List of devices attached\nXYZ  unauthorized usb:1\n")
    with pytest.raises(dev.PhoneError):
        dev.pick_serial(None, None, d)


def test_phone_connect_several_exits_nonzero(fake):
    fake.replies["devices -l"] = DEVICES_TWO
    assert dev.cmd_phone_connect([]) == 1


def test_phone_connect_reports_packages_and_never_hardcodes_port(fake, capsys):
    fake.replies["devices -l"] = DEVICES_ONE_WIFI
    fake.replies["pm list packages"] = ("package:au.awto.aoabench\npackage:au.awto.dji.awto_dji_app\n"
                                        "package:au.awto.dji.awto_dji_app.aoabench\n")
    assert dev.cmd_phone_connect([]) == 0
    assert capsys.readouterr().out.strip() == "192.168.25.50:37123"
    j = fake.joined()
    assert "adb -s 192.168.25.50:37123 shell pm list packages" in j
    assert not any(":5555" in x for x in j)
    assert dev.installed_packages("s") == {"dji": True, "bench": True, "old-bench": True}


def test_installed_packages_is_exact_match(fake):
    # the old id has the DJI id as a prefix: substring matching would say dji is installed
    fake.replies["pm list packages"] = "package:au.awto.dji.awto_dji_app.aoabench\n"
    assert dev.installed_packages("s") == {"dji": False, "bench": False, "old-bench": True}


def test_connect_flag_runs_adb_connect(fake):
    fake.replies["adb connect"] = "connected to 10.0.0.9:40001\n"
    assert dev.resolve_serial(None, "10.0.0.9:40001") == "10.0.0.9:40001"
    assert fake.calls[0] == ["adb", "connect", "10.0.0.9:40001"]


def test_connect_failure(fake):
    fake.replies["adb connect"] = "failed to connect to '10.0.0.9:1'\n"
    with pytest.raises(dev.PhoneError):
        dev.resolve_serial(None, "10.0.0.9:1")


# ---- load / unload --------------------------------------------------------------------------

@pytest.fixture
def apkenv(fake, monkeypatch, tmp_path):
    out = tmp_path / "out" / "app-debug.apk"
    out.parent.mkdir(parents=True)
    monkeypatch.setattr(dev, "APK_OUT", out)
    monkeypatch.setattr(dev, "APK_DIR", tmp_path / "apk")
    monkeypatch.setattr(dev, "APP_DIR", tmp_path / "app")
    fake.replies["devices -l"] = DEVICES_ONE_WIFI
    fake.replies["install -r"] = "Performing Streamed Install\nSuccess\n"
    fake.replies["pm list packages"] = ("package:au.awto.aoabench\npackage:au.awto.dji.awto_dji_app\n")
    # each build writes a distinguishable APK to the single output path
    fake.hooks.append(("flutter build", lambda argv: out.write_bytes(
        b"BENCH" if "--dart-define=BENCH=true" in argv else b"DJI")))
    return out


def builds(fake):
    return [(c, e) for c, e in zip(fake.calls, fake.envs) if c[:3] == ["flutter", "build", "apk"]]


def test_load_default_is_bench_with_env_and_define(apkenv, fake):
    assert dev.cmd_load([]) == 0
    (argv, env), = builds(fake)
    assert argv == ["flutter", "build", "apk", "--debug", "--dart-define=BENCH=true"]
    assert env == {"AWTO_BENCH": "1"}
    assert any(c[:4] == ["adb", "-s", "192.168.25.50:37123", "install"] and c[4] == "-r"
               and c[5].endswith("bench-debug.apk") for c in fake.calls)


def test_load_dji_has_no_bench_env_or_define(apkenv, fake):
    assert dev.cmd_load(["--dji"]) == 0
    (argv, env), = builds(fake)
    assert argv == ["flutter", "build", "apk", "--debug"]
    assert env == {"AWTO_BENCH": None}      # None = stripped even if the shell exported it


def test_load_both_copies_bench_aside_before_second_build(apkenv, fake):
    assert dev.cmd_load(["--both"]) == 0
    bs = builds(fake)
    assert [e for _, e in bs] == [{"AWTO_BENCH": "1"}, {"AWTO_BENCH": None}]
    assert dev.apk_copy("bench").read_bytes() == b"BENCH"
    assert dev.apk_copy("dji").read_bytes() == b"DJI"
    assert apkenv.read_bytes() == b"DJI"            # the output was overwritten by build 2
    installs = [c[5] for c in fake.calls if "install" in c and "-r" in c]
    assert [Path(i).name for i in installs] == ["bench-debug.apk", "dji-debug.apk"]


def test_load_no_build_installs_existing_copy(apkenv, fake):
    dev.APK_DIR.mkdir()
    dev.apk_copy("bench").write_bytes(b"x")
    assert dev.cmd_load(["--no-build"]) == 0
    assert builds(fake) == []


def test_load_no_build_without_copy_fails(apkenv, fake):
    assert dev.cmd_load(["--no-build"]) == 1


def test_load_fails_fast_without_flutter(apkenv, fake, monkeypatch):
    monkeypatch.setattr(dev.shutil, "which", lambda n: None if n == "flutter" else "/x")
    assert dev.cmd_load([]) == 1
    assert fake.calls == []


def test_load_build_has_stall_rule(apkenv, monkeypatch):
    seen = {}
    real = dev._exec

    def spy(argv, **kw):
        if argv[0] == "flutter":
            seen.update(kw)
        return real_fake(argv, **kw)
    real_fake = dev._exec
    monkeypatch.setattr(dev, "_exec", spy)
    dev.cmd_load([])
    assert seen["stall_s"] == 120 and seen["overall_s"]


def test_install_fails_when_package_missing_after_install(apkenv, fake):
    fake.replies["pm list packages"] = "package:au.awto.dji.awto_dji_app\n"
    assert dev.cmd_load([]) == 1


def test_unload_package_ids(fake):
    fake.replies["devices -l"] = DEVICES_ONE_WIFI
    fake.replies["uninstall"] = "Success\n"
    for flag, pkg in (("--bench", "au.awto.aoabench"), ("--dji", "au.awto.dji.awto_dji_app"),
                      ("--old-bench", "au.awto.dji.awto_dji_app.aoabench")):
        fake.calls.clear()
        assert dev.cmd_unload([flag]) == 0
        assert ["adb", "-s", "192.168.25.50:37123", "uninstall", pkg] in fake.calls


# ---- listen / connect / grant -----------------------------------------------------------------

import socket  # noqa: E402


@pytest.fixture
def busy_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    s.listen(1)
    yield s.getsockname()[1]
    s.close()


def free_port():
    s = socket.socket()
    s.bind(("0.0.0.0", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def test_listen_refuses_busy_port_and_shows_holder(fake, busy_port, capsys):
    fake.replies["ss -ltnp"] = "LISTEN 0 1 0.0.0.0:%d users:((\"python3\",pid=42))\n" % busy_port
    assert dev.cmd_listen(["--port", str(busy_port)]) == 1
    assert fake.calls[0][:2] == ["ss", "-ltnp"]
    assert not any("bench_host.py" in " ".join(c) for c in fake.calls)
    assert "pid=42" in (dev.LOG.read_text())


def test_listen_runs_bench_host_foreground_with_tail(fake):
    p = free_port()
    assert dev.cmd_listen(["--port", str(p)]) == 0
    assert fake.calls == [[sys.executable, "-I", "scripts/re/bench_host.py",
                           "--listen", str(p), "--tail"]]


def test_route_src_from_canned_ip_route(fake):
    fake.replies["ip -4 route get"] = IP_ROUTE
    assert dev.route_src("192.168.25.50") == "192.168.25.114"
    assert fake.calls[0] == ["ip", "-4", "route", "get", "192.168.25.50"]


def test_route_src_unparseable_fails(fake):
    fake.replies["ip -4 route get"] = "RTNETLINK answers: Network is unreachable\n"
    with pytest.raises(dev.PhoneError):
        dev.route_src("10.9.9.9")


@pytest.fixture
def conn(fake, monkeypatch, tmp_path, busy_port):
    monkeypatch.setattr(dev, "BENCH_HOST_LOG", tmp_path / "logs" / "bench_host.log")
    fake.replies["devices -l"] = DEVICES_ONE_WIFI
    fake.replies["ip -4 route get"] = IP_ROUTE
    fake.port = busy_port       # a live listener on this port
    return fake


def test_connect_command_construction_and_first_state(conn):
    log_ = dev.BENCH_HOST_LOG
    log_.parent.mkdir(parents=True, exist_ok=True)
    log_.write_text("old STATE port=idle\n")        # before the offset: must be ignored
    conn.hooks.append(("am start", lambda argv: log_.write_text(
        log_.read_text() + "2026 STATE port=attached usb=det\n")))
    assert dev.cmd_connect(["--port", str(conn.port)]) == 0
    j = conn.joined()
    s = "adb -s 192.168.25.50:37123 shell"
    assert j.index(f"{s} am force-stop au.awto.aoabench") < j.index(
        f"{s} am start -n au.awto.aoabench/au.awto.dji.awto_dji_app.MainActivity "
        f"-a au.awto.dji.action.BENCH --es host 192.168.25.114 --ei port {conn.port}")


def test_connect_explicit_host_skips_route(conn):
    log_ = dev.BENCH_HOST_LOG
    log_.parent.mkdir(parents=True, exist_ok=True)
    conn.hooks.append(("am start", lambda argv: log_.write_text("x STATE port=idle\n")))
    assert dev.cmd_connect(["--host", "10.1.2.3", "--port", str(conn.port), "--pkg", "dji"]) == 0
    assert not any(c[0] == "ip" for c in conn.calls)
    am = next(c for c in conn.calls if "start" in c)
    assert "au.awto.dji.awto_dji_app/au.awto.dji.awto_dji_app.MainActivity" in am
    assert am[am.index("--es") + 2] == "10.1.2.3"


def test_connect_without_state_fails_with_logcat(conn, monkeypatch):
    monkeypatch.setattr(dev, "CONNECT_WAIT_S", 0.3)
    conn.replies["logcat"] = "E/AndroidRuntime: boom\n"
    assert dev.cmd_connect(["--port", str(conn.port)]) == 1
    assert any("logcat" in c for c in conn.calls)
    assert "boom" in dev.LOG.read_text()


def test_connect_without_listener_fails_before_touching_phone(conn):
    assert dev.cmd_connect(["--port", str(free_port())]) == 1
    assert not any("force-stop" in c for c in conn.calls)


def test_phone_ip_from_wireless_serial_and_usb_fallback(fake):
    assert dev.phone_ip("192.168.25.50:37123") == "192.168.25.50"
    fake.replies["route get 1.1.1.1"] = "1.1.1.1 via 10.0.0.1 dev wlan0 src 10.0.0.77 uid 0\n"
    assert dev.phone_ip("8A1X") == "10.0.0.77"


def test_grant_calls_accept_with_resolved_serial(fake, monkeypatch):
    fake.replies["devices -l"] = DEVICES_ONE_WIFI
    got = []

    class Mod:
        @staticmethod
        def accept(serial, log=print):
            got.append(serial)
            return 0
    monkeypatch.setattr(dev, "_usb_dialog", lambda: Mod)
    monkeypatch.chdir(REPO)
    assert dev.cmd_grant([]) == 0
    assert got == ["192.168.25.50:37123"]


# ---- suite / rc / up -----------------------------------------------------------------------------

def test_suite_argv_passthrough_and_values_not_read_as_names(fake):
    p = free_port()
    assert dev.cmd_suite(["fuzz", "size_sweep", "--fuzz-seed", "7", "--port", str(p),
                          "--soak-minutes", "2"]) == 0
    assert fake.calls == [[sys.executable, "-I", "scripts/re/bench_host.py", "--listen", str(p),
                           "--suite", "fuzz", "--suite", "size_sweep",
                           "--fuzz-seed", "7", "--soak-minutes", "2"]]


def test_suite_refuses_busy_port(fake, busy_port):
    assert dev.cmd_suite(["soak", "--port", str(busy_port)]) == 1
    assert not any("bench_host.py" in " ".join(c) for c in fake.calls)


def test_suite_rejects_unknown_name(fake):
    assert dev.cmd_suite(["bogus"]) == 2


def test_suite_overall_grows_with_soak():
    assert dev.suite_overall_s(["--soak-minutes", "10"]) == dev.SUITE_OVERALL_S + 600


def test_rc_front(fake, monkeypatch):
    monkeypatch.setenv("AWTO_PHONE", "SER1")
    assert dev.cmd_rc(["replay", "cap.json", "--vid", "18d1", "--pid", "4ee1"]) == 0
    assert fake.calls == [[sys.executable, "-I", "scripts/re/t600_rc_emulator.py", "replay",
                           "cap.json", "--adb-serial", "SER1", "--vid", "18d1", "--pid", "4ee1"]]


def test_rc_defaults_to_handshake_without_adb_serial(fake):
    assert dev.cmd_rc(["--vid", "1", "--pid", "2", "--accept-dialog"]) == 0
    assert fake.calls[0][3] == "handshake"
    assert "--adb-serial" not in fake.calls[0] and "--accept-dialog" in fake.calls[0]


class FakeProc:
    def __init__(self):
        self.terminated = False

    def poll(self):
        return 0 if self.terminated else None

    def wait(self, t=None):
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.terminated = True


def test_up_order_phone_load_listen_connect(conn, monkeypatch, apkenv):
    spawned = []
    proc = FakeProc()
    monkeypatch.setattr(dev, "_spawn", lambda argv, why: (spawned.append(argv), proc)[1])
    monkeypatch.setattr(dev, "port_in_use", lambda p: bool(spawned))   # free until spawned
    log_ = dev.BENCH_HOST_LOG
    log_.parent.mkdir(parents=True, exist_ok=True)
    conn.hooks.append(("am start", lambda argv: log_.write_text("t STATE port=idle\n")))
    assert dev.cmd_up(["--port", "9911"]) == 0
    j = conn.joined()
    i_devices = next(i for i, x in enumerate(j) if "devices -l" in x)
    i_build = next(i for i, x in enumerate(j) if x.startswith("flutter build"))
    i_install = next(i for i, x in enumerate(j) if " install -r " in x)
    i_start = next(i for i, x in enumerate(j) if " am start " in x)
    assert i_devices < i_build < i_install < i_start
    assert spawned == [[sys.executable, "-I", "scripts/re/bench_host.py", "--listen", "9911", "--tail"]]
    assert proc.terminated      # listener is cleaned up on exit


def test_up_no_build_skips_flutter(conn, monkeypatch, apkenv):
    dev.APK_DIR.mkdir(exist_ok=True)
    dev.apk_copy("bench").write_bytes(b"x")
    monkeypatch.setattr(dev, "_spawn", lambda argv, why: FakeProc())
    monkeypatch.setattr(dev, "port_in_use", lambda p: False)
    assert dev.cmd_up(["--no-build", "--port", "9911"]) == 1       # listener never "binds"
    assert not any(c[0] == "flutter" for c in conn.calls)


def test_up_stops_when_port_busy_before_building_listener(conn, busy_port, apkenv, monkeypatch):
    spawned = []
    monkeypatch.setattr(dev, "_spawn", lambda argv, why: spawned.append(argv))
    assert dev.cmd_up(["--no-build", "--port", str(busy_port)]) == 1
    assert spawned == []


def test_describe_lists_new_commands():
    for name in ("phone-connect", "load", "unload", "listen", "connect", "grant",
                 "suite", "up", "rc", "phone"):
        assert name in dev.COMMANDS and dev.COMMANDS[name]["summary"]
