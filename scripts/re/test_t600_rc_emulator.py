"""t600_rc_emulator: fake Backend, no hardware."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import t600_rc_emulator as e
from aoa_mux import COMMAND, FPV_VIDEO
from duml_proto import build_frame


class Fake(e.Backend):
    def __init__(self, rx=b""):
        self.calls, self.rx, self.tx = [], rx, []

    def open(self): self.calls.append("open")
    def switch_to_accessory(self, s): self.calls.append(("switch", s))
    def read_bulk(self, size, timeout_ms):
        d, self.rx = self.rx, b""
        return d
    def write_bulk(self, data, timeout_ms): self.tx.append(data)
    def close(self): self.calls.append("close")


def frame(sender, receiver, seq=1):
    return build_frame(sender, receiver, seq, 2, 0x02, 0x10, b"\x01")


def test_identity_parsed_from_dart():
    assert e.parse_identity() == {"manufacturer": "DJI", "model": "T600"}


def test_identity_shape_change_fails(tmp_path):
    p = tmp_path / "x.dart"
    p.write_text("class AoaIdentity { static const manufacturer = \"DJI\"; }")
    with pytest.raises(ValueError):
        e.parse_identity(str(p))


def test_handshake_order_and_strings():
    be = Fake()
    obs = e.AdbObserver("S", run=lambda *a: (
        "current_functions=ACCESSORY\ncurrent_accessory={manufacturer=DJI, model=T600, "
        "description=DJI, version=v1.2.3.4, uri=www.dji.com, serial=12345678}"))
    assert e.handshake(be, obs) is True
    assert be.calls[0] == "open"
    assert be.calls[1] == ("switch", ["DJI", "T600", "DJI", "v1.2.3.4", "www.dji.com", "12345678"])


def test_handshake_fails_when_phone_not_accessory():
    obs = e.AdbObserver("S", run=lambda *a: "current_functions=mtp\ncurrent_accessory=null")
    assert e.handshake(Fake(), obs) is False


def test_observer_parses_logcat():
    t = "x\n[transport:android-accessory] state=connected\nnoise\n[link] up"
    assert e.AdbObserver.parse_logcat(t) == [
        "[transport:android-accessory] state=connected", "[link] up"]


def test_replay_filter():
    assert e.replay_filter(frame(6, 2))[0]
    assert not e.replay_filter(frame(6, 3))[0]      # FC receiver: flight control path
    assert not e.replay_filter(frame(2, 2))[0]      # app-sent
    assert not e.replay_filter(frame(2, 6))[0]
    assert not e.replay_filter(b"\x55garbage")[0]


def test_replay_sends_only_app_bound():
    good, fc, fromapp = frame(6, 2, 1), frame(6, 3, 2), frame(2, 2, 3)
    data = b"".join(e.envelope(f) for f in (good, fc, fromapp)) + e.envelope(b"x", FPV_VIDEO)
    be = Fake()
    assert e.replay(be, data) == (1, 2)
    assert be.tx == [e.envelope(good)]


def test_listen_decodes_synthetic_envelope():
    f = frame(6, 2)
    out = []
    n = e.listen(Fake(rx=e.envelope(f)), 0.05, out=out.append)
    assert n == 1 and "duml_crc_ok=True" in out[0] and "receiver=0x02" in out[0]


def test_cynthion_stub():
    with pytest.raises(NotImplementedError):
        e.CynthionBackend()
