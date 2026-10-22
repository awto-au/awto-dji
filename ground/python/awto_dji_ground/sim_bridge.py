"""A simulated bridge: the vehicle side of the protocol, with no DJI hardware.

It stands in for the Android app so the ground clients (and QGroundControl) can be
exercised end to end. It is also the executable reference for what the real Android
bridge must do with each MAVLink message, mirrored in the Kotlin ``DjiController``.

It models a trivial point-mass "aircraft": takeoff climbs to 1.2 m, velocity commands
move a body-frame point mass, RTL flies home and lands. Run it standalone::

    python -m awto_dji_ground.sim_bridge --listen udpin:0.0.0.0:14550
"""

from __future__ import annotations

import argparse
import math
import time

from pymavlink import mavutil

from . import protocol as P

_HOME_LAT = -33.8688
_HOME_LON = 151.2093


class SimBridge:
    def __init__(self, master: "mavutil.mavfile"):
        self._m = master
        self.mode = P.FlightMode.HOLD
        self.armed = False
        self.in_air = False
        self.alt = 0.0                 # relative altitude, m
        self.north = 0.0               # m from home
        self.east = 0.0
        self.yaw = 0.0                 # rad
        self.cmd_vel = (0.0, 0.0, 0.0, 0.0)  # forward, right, down, yaw_rate (rad/s)
        self._cmd_at = 0.0
        self._boot = time.monotonic()

    # -- outgoing ----------------------------------------------------------

    def _ms(self) -> int:
        return int((time.monotonic() - self._boot) * 1000)

    def send_heartbeat(self) -> None:
        base = mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED
        if self.armed:
            base |= mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED
        self._m.mav.heartbeat_send(
            mavutil.mavlink.MAV_TYPE_QUADROTOR, mavutil.mavlink.MAV_AUTOPILOT_GENERIC,
            base, self.mode, mavutil.mavlink.MAV_STATE_ACTIVE,
        )

    def send_telemetry(self) -> None:
        lat, lon = _offset_to_global(self.north, self.east)
        vx, vy, vz, _ = self._world_velocity()
        self._m.mav.global_position_int_send(
            self._ms(), int(lat * 1e7), int(lon * 1e7), int(self.alt * 1000),
            int(self.alt * 1000), int(vx * 100), int(vy * 100), int(vz * 100),
            int(math.degrees(self.yaw) % 360 * 100),
        )
        self._m.mav.attitude_send(self._ms(), 0.0, 0.0, self.yaw, 0.0, 0.0, 0.0)
        self._m.mav.gps_raw_int_send(
            self._ms() * 1000, 3, int(lat * 1e7), int(lon * 1e7), int(self.alt * 1000),
            65535, 65535, 65535, 65535, 14,
        )
        self._m.mav.battery_status_send(
            0, 0, 0, 25, [12000] + [65535] * 9, -1, -1, -1, 78, 0,
        )
        landed = 2 if self.in_air else 1
        self._m.mav.extended_sys_state_send(mavutil.mavlink.MAV_VTOL_STATE_UNDEFINED, landed)

    # -- incoming ----------------------------------------------------------

    def handle(self, msg) -> None:
        kind = msg.get_type()
        if kind == "COMMAND_LONG":
            self._handle_command(msg)
        elif kind == "SET_POSITION_TARGET_LOCAL_NED":
            self._handle_velocity(msg)

    def _ack(self, command: int, result: int = 0) -> None:
        self._m.mav.command_ack_send(command, result)

    def _handle_command(self, msg) -> None:
        c = msg.command
        M = mavutil.mavlink
        if c == M.MAV_CMD_NAV_TAKEOFF:
            self.armed = True
            self.in_air = True
            self.mode = P.FlightMode.TAKEOFF
            self.alt = 1.2
            self.mode = P.FlightMode.HOLD
            self._ack(c)
        elif c == M.MAV_CMD_NAV_LAND:
            self.mode = P.FlightMode.LANDING
            self.alt = 0.0
            self.in_air = False
            self.armed = False
            self.mode = P.FlightMode.HOLD
            self._ack(c)
        elif c == M.MAV_CMD_NAV_RETURN_TO_LAUNCH:
            self.mode = P.FlightMode.RTL
            self.north = self.east = 0.0
            self.alt = 0.0
            self.in_air = False
            self.armed = False
            self.mode = P.FlightMode.HOLD
            self._ack(c)
        elif c == M.MAV_CMD_COMPONENT_ARM_DISARM:
            self.armed = bool(msg.param1 >= 0.5)
            self._ack(c)
        else:
            self._ack(c, 3)  # MAV_RESULT_UNSUPPORTED

    def _handle_velocity(self, msg) -> None:
        if msg.coordinate_frame != P.MAV_FRAME_BODY_NED:
            return
        self.mode = P.FlightMode.GUIDED
        self.cmd_vel = (
            _clamp(msg.vx, P.MAX_HORIZONTAL_MPS),
            _clamp(msg.vy, P.MAX_HORIZONTAL_MPS),
            _clamp(msg.vz, P.MAX_VERTICAL_MPS),
            _clamp(msg.yaw_rate, math.radians(P.MAX_YAW_DPS)),
        )
        self._cmd_at = time.monotonic()

    # -- integration -------------------------------------------------------

    def _world_velocity(self):
        fwd, right, down, yr = self.cmd_vel
        # Dead-man: stale command => hover.
        if time.monotonic() - self._cmd_at > 0.5:
            fwd = right = down = yr = 0.0
        vx = fwd * math.cos(self.yaw) - right * math.sin(self.yaw)
        vy = fwd * math.sin(self.yaw) + right * math.cos(self.yaw)
        return vx, vy, down, yr

    def step(self, dt: float) -> None:
        if not self.in_air:
            return
        vx, vy, vz, yr = self._world_velocity()
        self.north += vx * dt
        self.east += vy * dt
        self.alt = max(0.0, self.alt - vz * dt)
        self.yaw = (self.yaw + yr * dt) % (2 * math.pi)


def _offset_to_global(north_m: float, east_m: float):
    dlat = north_m / 111_320.0
    dlon = east_m / (111_320.0 * math.cos(math.radians(_HOME_LAT)))
    return _HOME_LAT + dlat, _HOME_LON + dlon


def _clamp(v: float, limit: float) -> float:
    if v != v:
        return 0.0
    return max(-limit, min(limit, v))


def run(device: str, duration: float | None = None) -> None:
    master = mavutil.mavlink_connection(
        device, source_system=P.VEHICLE_SYSTEM_ID, source_component=P.VEHICLE_COMPONENT_ID,
        dialect="common",
    )
    bridge = SimBridge(master)
    last_hb = last_tlm = last_step = time.monotonic()
    start = time.monotonic()
    while duration is None or time.monotonic() - start < duration:
        msg = master.recv_match(blocking=True, timeout=0.02)
        if msg is not None and msg.get_type() != "BAD_DATA":
            bridge.handle(msg)
        now = time.monotonic()
        bridge.step(now - last_step)
        last_step = now
        if now - last_hb >= 1.0 / P.HEARTBEAT_HZ:
            bridge.send_heartbeat()
            last_hb = now
        if now - last_tlm >= 1.0 / P.TELEMETRY_HZ:
            bridge.send_telemetry()
            last_tlm = now


def main() -> None:
    ap = argparse.ArgumentParser(description="Simulated awto-dji bridge (no hardware).")
    ap.add_argument("--listen", default="udpin:0.0.0.0:14550",
                    help="pymavlink connection string to serve on")
    ap.add_argument("--duration", type=float, default=None, help="seconds to run, then exit")
    args = ap.parse_args()
    print(f"sim bridge serving MAVLink on {args.listen}")
    run(args.listen, args.duration)


if __name__ == "__main__":
    main()
