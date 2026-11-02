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

    def __call__(self, argv, **kw):
        self.calls.append(list(argv))
        self.envs.append(kw.get("env"))
        joined = " ".join(argv)
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
