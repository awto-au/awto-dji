"""Ground-station client for the awto-dji Android bridge.

Talks MAVLink to the bridge app (which runs the DJI Mobile SDK v4 on the phone or the
remote controller). Blocking, single-threaded; fine for scripts and a REPL. For a UI,
run :meth:`Vehicle.pump` on its own thread.

Example::

    from awto_dji_ground import Vehicle
    v = Vehicle.connect("udpout:192.168.1.50:14550")
    v.wait_ready()
    v.takeoff(blocking=True)
    v.set_velocity(forward=2.0, duration=3.0)   # 2 m/s forward for 3 s, then hover
    v.return_to_home()
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Optional

from pymavlink import mavutil

from . import protocol as P


@dataclass
class Telemetry:
    """Latest vehicle state, updated as messages arrive."""
    time_boot_ms: int = 0
    lat: Optional[float] = None          # degrees
    lon: Optional[float] = None          # degrees
    relative_alt_m: float = 0.0          # above home
    vx: float = 0.0                      # m/s, north
    vy: float = 0.0                      # m/s, east
    vz: float = 0.0                      # m/s, down
    heading_deg: float = 0.0
    roll_deg: float = 0.0
    pitch_deg: float = 0.0
    yaw_deg: float = 0.0
    battery_pct: float = -1.0
    satellites: int = 0
    mode: int = P.FlightMode.UNKNOWN
    armed: bool = False
    in_air: bool = False
    last_heartbeat: float = 0.0

    @property
    def mode_name(self) -> str:
        return P.FlightMode.name(self.mode)


class CommandError(RuntimeError):
    """A command was rejected by the bridge, or no acknowledgement arrived."""


# MAV_RESULT values we care about.
_MAV_RESULT_ACCEPTED = 0
_MAV_RESULT_IN_PROGRESS = 5


class Vehicle:
    def __init__(self, master: "mavutil.mavfile"):
        self._m = master
        self.telemetry = Telemetry()
        self._last_gcs_hb = 0.0

    # -- lifecycle ---------------------------------------------------------

    @classmethod
    def connect(cls, device: str, *, source_system: int = P.GCS_SYSTEM_ID,
                source_component: int = P.GCS_COMPONENT_ID) -> "Vehicle":
        """Open a MAVLink connection. ``device`` is any pymavlink string, e.g.
        ``"udpout:HOST:14550"`` to reach the bridge, or ``"udpin:0.0.0.0:14550"`` to
        listen for it."""
        master = mavutil.mavlink_connection(
            device, source_system=source_system, source_component=source_component,
            dialect="common", autoreconnect=True,
        )
        return cls(master)

    def close(self) -> None:
        self._m.close()

    def __enter__(self) -> "Vehicle":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- receive -----------------------------------------------------------

    def send_gcs_heartbeat(self) -> None:
        """Emit a GCS heartbeat. A real GCS does this once a second; it also tells a
        UDP ``udpin`` bridge our address so it can reach us."""
        self._m.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0,
            mavutil.mavlink.MAV_STATE_ACTIVE,
        )
        self._last_gcs_hb = time.monotonic()

    def pump(self, timeout: float = 0.05) -> int:
        """Drain pending messages into :attr:`telemetry`. Returns how many were read."""
        if time.monotonic() - self._last_gcs_hb >= 1.0:
            self.send_gcs_heartbeat()
        count = 0
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            msg = self._m.recv_match(blocking=True, timeout=remaining)
            if msg is None:
                break
            self._ingest(msg)
            count += 1
        return count

    def _ingest(self, msg) -> None:
        t = self.telemetry
        kind = msg.get_type()
        if kind == "HEARTBEAT":
            t.last_heartbeat = time.monotonic()
            t.mode = msg.custom_mode
            base = msg.base_mode
            t.armed = bool(base & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
        elif kind == "GLOBAL_POSITION_INT":
            t.time_boot_ms = msg.time_boot_ms
            t.lat = msg.lat / 1e7
            t.lon = msg.lon / 1e7
            t.relative_alt_m = msg.relative_alt / 1000.0
            t.vx = msg.vx / 100.0
            t.vy = msg.vy / 100.0
            t.vz = msg.vz / 100.0
            t.heading_deg = (msg.hdg / 100.0) if msg.hdg != 65535 else t.heading_deg
        elif kind == "ATTITUDE":
            t.roll_deg = math.degrees(msg.roll)
            t.pitch_deg = math.degrees(msg.pitch)
            t.yaw_deg = math.degrees(msg.yaw)
        elif kind == "GPS_RAW_INT":
            t.satellites = msg.satellites_visible
        elif kind == "BATTERY_STATUS":
            t.battery_pct = float(msg.battery_remaining)
        elif kind == "EXTENDED_SYS_STATE":
            # MAV_LANDED_STATE: 1 on ground, 2 in air, 3 takeoff, 4 landing
            t.in_air = msg.landed_state in (2, 3, 4)

    def wait_ready(self, timeout: float = 15.0) -> Telemetry:
        """Block until the bridge is sending heartbeats. Raises on timeout."""
        deadline = time.monotonic() + timeout
        self.send_gcs_heartbeat()  # announce our address to a udpin bridge at once
        while time.monotonic() < deadline:
            self.pump(timeout=0.2)
            if self.telemetry.last_heartbeat and (
                time.monotonic() - self.telemetry.last_heartbeat < 3.0
            ):
                return self.telemetry
        raise CommandError("no heartbeat from bridge; is the Android app running and reachable?")

    # -- commands ----------------------------------------------------------

    def _send_command_long(self, command: int, *params: float) -> None:
        params = list(params) + [0.0] * (7 - len(params))
        self._m.mav.command_long_send(
            P.VEHICLE_SYSTEM_ID, P.VEHICLE_COMPONENT_ID, command, 0, *params[:7]
        )

    def _await_ack(self, command: int, timeout: float) -> int:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self._m.recv_match(type="COMMAND_ACK", blocking=True,
                                     timeout=deadline - time.monotonic())
            if msg is None:
                continue
            if msg.command != command:
                continue
            if msg.result in (_MAV_RESULT_ACCEPTED, _MAV_RESULT_IN_PROGRESS):
                return msg.result
            raise CommandError(
                f"command {command} rejected: MAV_RESULT={msg.result}"
            )
        raise CommandError(f"no COMMAND_ACK for command {command} within {timeout}s")

    def takeoff(self, altitude_m: float = 1.2, *, blocking: bool = False,
                timeout: float = 10.0) -> None:
        """Automatic takeoff. DJI's auto-takeoff climbs to a fixed low altitude; the
        aircraft then holds. ``altitude_m`` is advisory and passed through for bridges
        that honour it."""
        self._send_command_long(
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0, 0, 0, float("nan"), 0, 0, altitude_m
        )
        if blocking:
            self._await_ack(mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, timeout)

    def land(self, *, blocking: bool = False, timeout: float = 10.0) -> None:
        self._send_command_long(mavutil.mavlink.MAV_CMD_NAV_LAND)
        if blocking:
            self._await_ack(mavutil.mavlink.MAV_CMD_NAV_LAND, timeout)

    def return_to_home(self, *, blocking: bool = False, timeout: float = 10.0) -> None:
        self._send_command_long(mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH)
        if blocking:
            self._await_ack(mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH, timeout)

    def arm(self, arm: bool = True, *, blocking: bool = True, timeout: float = 5.0) -> None:
        """Start or stop the motors. DJI arms implicitly on takeoff, so this is mainly
        for an explicit stop on the ground."""
        self._send_command_long(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1.0 if arm else 0.0
        )
        if blocking:
            self._await_ack(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, timeout)

    def set_velocity(self, forward: float = 0.0, right: float = 0.0, down: float = 0.0,
                     yaw_rate_dps: float = 0.0, *, duration: Optional[float] = None,
                     rate_hz: float = 10.0) -> None:
        """Command a body-frame velocity (metres/second) and yaw rate (deg/s).

        The bridge enables DJI virtual sticks on the first such command. Values are
        clamped to the protocol envelope on both sides. With ``duration`` set, the
        velocity is streamed at ``rate_hz`` for that long and then zeroed to hover;
        otherwise a single frame is sent and the caller must keep sending (the bridge's
        dead-man timer zeroes the sticks if frames stop)."""
        f = _clamp(forward, P.MAX_HORIZONTAL_MPS)
        r = _clamp(right, P.MAX_HORIZONTAL_MPS)
        d = _clamp(down, P.MAX_VERTICAL_MPS)
        yr = math.radians(_clamp(yaw_rate_dps, P.MAX_YAW_DPS))

        def send_once(fx, ry, dz, yrr):
            self._m.mav.set_position_target_local_ned_send(
                0, P.VEHICLE_SYSTEM_ID, P.VEHICLE_COMPONENT_ID,
                P.MAV_FRAME_BODY_NED, P.VELOCITY_YAWRATE_TYPE_MASK,
                0, 0, 0,          # position (ignored)
                fx, ry, dz,       # velocity x(forward)/y(right)/z(down)
                0, 0, 0,          # acceleration (ignored)
                0, yrr,           # yaw (ignored), yaw_rate
            )

        if duration is None:
            send_once(f, r, d, yr)
            return
        period = 1.0 / max(1.0, rate_hz)
        end = time.monotonic() + duration
        while time.monotonic() < end:
            send_once(f, r, d, yr)
            self.pump(timeout=period)
        send_once(0.0, 0.0, 0.0, 0.0)  # hover


def _clamp(value: float, limit: float) -> float:
    if value != value:  # NaN
        return 0.0
    return max(-limit, min(limit, value))
