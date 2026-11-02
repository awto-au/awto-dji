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
