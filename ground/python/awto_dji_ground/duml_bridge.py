"""The real vehicle-side MAVLink bridge, driven by this project's own DUML telemetry
instead of DJI's Mobile SDK or the simulated point-mass model in sim_bridge.py.

Telemetry only in this first version - no command injection (arm/takeoff/velocity).
Sending real flight-control commands is a separate, deliberately later step; this one
is read-only with respect to the aircraft, so it is safe to run and test against a
replayed or live capture with no new risk to the aircraft.

Source of telemetry: scripts/re/aoa_relay_server.py's aoa_relay_frames.log (tailed via
scripts/re/duml_telemetry.py's shared parser/decoders - same ones the Dart app and the
gimbal verify tooling use, so this does not maintain its own separate decode).

Usage:
    python3 -I -m awto_dji_ground.duml_bridge --log <path/to/aoa_relay_frames.log> \
        --listen udpin:0.0.0.0:14550 [--replay]

--replay reads the whole log from the start and exits instead of tailing live - for
testing against a recorded session with no hardware connected at all.
"""
from __future__ import annotations

import argparse
import math
import os
import sys
import time

from pymavlink import mavutil

from . import protocol as P

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "..", "..", "..", "scripts", "re"))
from duml_telemetry import PUSH_DECODERS, parse_line  # noqa: E402


class DumlBridge:
    """Holds the latest decoded telemetry and emits it as MAVLink. No DUML is sent."""

    def __init__(self, master: "mavutil.mavfile"):
        self._m = master
        self._boot = time.monotonic()
        self.osd: dict | None = None
        self.signal: dict | None = None
        self.last_osd_at = 0.0

    def _ms(self) -> int:
        return int((time.monotonic() - self._boot) * 1000)

    def observe(self, cset: int, cid: int, payload: bytes) -> None:
        for name, (dcset, dcid, decode) in PUSH_DECODERS.items():
            if (cset, cid) != (dcset, dcid):
                continue
            decoded = decode(payload)
            if not decoded:
                continue
            if name == "osd":
                self.osd = decoded
                self.last_osd_at = time.monotonic()
            elif name == "rc_signal":
                self.signal = decoded

    def send_heartbeat(self) -> None:
        # armed/disarmed is NOT reported here - no decoded motor-state source exists
        # yet (see docs/known-telemetry-and-commands.md), and this bridge does not
        # fabricate safety-relevant state it hasn't actually verified from the wire.
        self._m.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_AUTOPILOT_GENERIC,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, P.FlightMode.UNKNOWN,
            mavutil.mavlink.MAV_STATE_ACTIVE,
        )

    def send_telemetry(self) -> None:
        if self.osd is not None:
            o = self.osd
            self._m.mav.global_position_int_send(
                self._ms(), int(o["latitude"] * 1e7), int(o["longitude"] * 1e7),
                int(o["relative_height"] * 1000), int(o["relative_height"] * 1000),
                int(o["vgx"] * 100), int(o["vgy"] * 100), int(o["vgz"] * 100),
                int(o["yaw"] % 360 * 100),
            )
            self._m.mav.attitude_send(
                self._ms(), math.radians(o["roll"]), math.radians(o["pitch"]),
                math.radians(o["yaw"]), 0.0, 0.0, 0.0,
            )
            # satellites_visible=255 ("unknown" per MAVLink convention) - no decoded
            # satellite-count source yet; fix_type=3 only because we do have real
            # lat/lon/alt flowing, not because a fix-quality field was read.
            self._m.mav.gps_raw_int_send(
                self._ms() * 1000, 3, int(o["latitude"] * 1e7), int(o["longitude"] * 1e7),
                int(o["relative_height"] * 1000), 65535, 65535, 65535, 65535, 255,
            )
        if self.signal is not None:
            s = self.signal
            # RADIO_STATUS: rssi/remrssi are 0-255 "better is higher" by MAVLink
            # convention; aggregate_quality is already 0-127, matching the app's own
            # "weak"/"strong" metric (see rc_signal.dart) - scaled to the 0-255 range.
            self._m.mav.radio_status_send(
                min(255, s["aggregate_quality"] * 2), 255, 255, 255, 255, 0, 0,
            )

    def is_osd_stale(self, max_age_s: float = 2.0) -> bool:
        return self.osd is None or (time.monotonic() - self.last_osd_at) > max_age_s


def run(log_path: str, device: str, replay: bool, duration: float | None = None,
        ready: "object | None" = None) -> None:
    """`ready` (a threading.Event), if given, is set once the UDP socket is bound -
    for tests: starting this in a background thread races the socket bind against a
    client immediately sending to it over UDP (no retry, so a too-early send is just
    lost), unlike the sim_bridge/test_ground.py pattern where the bind happens
    synchronously in the test thread before the processing thread starts."""
    master = mavutil.mavlink_connection(
        device, source_system=P.VEHICLE_SYSTEM_ID, source_component=P.VEHICLE_COMPONENT_ID,
        dialect="common",
    )
    if ready is not None:
        ready.set()
    bridge = DumlBridge(master)
    f = open(log_path)
    if not replay:
        f.seek(0, os.SEEK_END)  # tail: only new telemetry from here, live mode

    last_hb = last_tlm = time.monotonic()
    start = time.monotonic()
    replay_exhausted = False
    while duration is None or time.monotonic() - start < duration:
        # Drains any incoming GCS packets (there's nothing to act on yet - telemetry-
        # only bridge) but this call is NOT optional: pymavlink's UDP transport only
        # learns the peer address to send to from a received packet, so without this
        # the bridge has nowhere to send its own heartbeat/telemetry at all.
        master.recv_match(blocking=False)
        line = None if replay_exhausted else f.readline()
        if line:
            parsed = parse_line(line)
            if parsed:
                _sender, _receiver, cset, cid, payload = parsed
                bridge.observe(cset, cid, payload)
        elif replay and not replay_exhausted:
            replay_exhausted = True
            if duration is None:
                break  # CLI one-shot use: replay the whole file, then exit
            time.sleep(0.05)  # test/long-duration use: keep timers ticking after EOF
        else:
            time.sleep(0.05)  # live tail: matches duml_telemetry.tail_* poll rate

        now = time.monotonic()
        if now - last_hb >= 1.0 / P.HEARTBEAT_HZ:
            bridge.send_heartbeat()
            last_hb = now
        if now - last_tlm >= 1.0 / P.TELEMETRY_HZ:
            bridge.send_telemetry()
            last_tlm = now
    f.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--log", required=True, help="path to aoa_relay_frames.log")
    ap.add_argument("--listen", default="udpin:0.0.0.0:14550",
                    help="pymavlink connection string to serve on")
    ap.add_argument("--replay", action="store_true",
                     help="read the whole log from the start then exit, instead of "
                          "tailing live - for testing with no hardware connected")
    ap.add_argument("--duration", type=float, default=None, help="seconds to run, then exit")
    args = ap.parse_args()
    print(f"duml bridge: reading {args.log} ({'replay' if args.replay else 'live tail'}), "
          f"serving MAVLink on {args.listen}")
    run(args.log, args.listen, args.replay, args.duration)


if __name__ == "__main__":
    main()
