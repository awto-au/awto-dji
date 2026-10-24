"""Regression test for duml_telemetry.parse_line - specifically against log-line shapes
that have broken this parser before (the protection= field). Run:
python3 -I scripts/re/test_duml_telemetry.py
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_telemetry import PUSH_DECODERS, format_frame, parse_line  # noqa: E402

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


# Pre-protection-field format (what this parser was first written against).
check("no protection field",
      parse_line("ts sender=0x04 receiver=0x02 seq=1 type=0x03 set=0x04 id=0x05 payload=aabb"),
      (0x04, 0x02, 0x04, 0x05, b"\xaa\xbb"))

# Current format, the field that broke it: real line from captures/sessions/2026-10-24.
check("with protection field",
      parse_line("2026-10-24T14:00:54 sender=0x04 receiver=0x02 seq=20200 type=0x03 "
                  "set=0x04 id=0x05 protection=3 payload=8efe0100e50080ff00002001"),
      (0x04, 0x02, 0x04, 0x05, bytes.fromhex("8efe0100e50080ff00002001")))

# Any future extra key=value field should also not break this (forward-compat, not
# just the one field seen so far).
check("hypothetical extra field",
      parse_line("ts sender=0x0e receiver=0x02 seq=5 type=0x03 set=0x06 id=0x05 "
                  "protection=0 extra=xyz payload=00"),
      (0x0e, 0x02, 0x06, 0x05, b"\x00"))

check("non-matching line", parse_line("not a frame line at all"), None)

cset, cid, decode = PUSH_DECODERS["gimbal"]
check("gimbal decoder cmdset/cmdid", (cset, cid), (0x04, 0x05))
check("gimbal decode -37.0/0.1/22.9 mode/err from byte6=0x80",
      decode(bytes.fromhex("8efe0100e50080ff00002001")),
      {"pitch": -37.0, "roll": 0.1, "yaw": 22.9, "err": 0, "mode": "YawFollow"})

check("format_frame names device+cmd, decodes gimbal push instead of hex",
      format_frame(0x04, 0x02, 0x04, 0x05, bytes.fromhex("8efe0100e50080ff00002001")),
      "gimbal->app GIMBAL/GetPushParams pitch=-37.0 roll=0.1 yaw=22.9 err=0 mode=YawFollow")

check("format_frame falls back to hex for an unstructured command",
      format_frame(0x02, 0x0e, 0x06, 0x22, b""),
      "app->osd RC/RequestGimbalCtrPermission payload=")

cset, cid, decode = PUSH_DECODERS["osd"]
check("osd decoder cmdset/cmdid", (cset, cid), (0x03, 0x43))
_osd_payload = bytearray(30)
struct.pack_into("<dd", _osd_payload, 0, 0.0, 0.0)
struct.pack_into("<7h", _osd_payload, 16, 100, 10, 0, 0, 50, 0, 900)
check("osd decode lat/lon/height/velocity/attitude",
      decode(bytes(_osd_payload)),
      {"latitude": 0.0, "longitude": 0.0, "relative_height": 10.0, "vgx": 1.0,
       "vgy": 0.0, "vgz": 0.0, "pitch": 5.0, "roll": 0.0, "yaw": 90.0})

cset, cid, decode = PUSH_DECODERS["rc_signal"]
check("rc_signal decoder cmdset/cmdid", (cset, cid), (0x09, 0x08))
check("rc_signal decode byte0=0x35 (quality 53/127, downlink) matches app's 'weak' report",
      decode(bytes.fromhex("35e1e1")),
      {"aggregate_quality": 53, "is_uplink": False, "antenna1_dbm": -31, "antenna2_dbm": -31})

if FAILURES:
    print(f"{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(" ", f)
    sys.exit(1)
print("all checks passed")
