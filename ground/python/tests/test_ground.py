"""End-to-end tests: the ground client against the simulated bridge over a real UDP
socket, on a background thread. No DJI hardware."""

from __future__ import annotations

import threading
import time

import pytest
from pymavlink import mavutil

from awto_dji_ground import Vehicle, CommandError, protocol as P
from awto_dji_ground.sim_bridge import SimBridge, _clamp


def _free_udp_port() -> int:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class BridgeThread:
    """Runs a SimBridge on a UDP port until stopped."""

    def __init__(self, port: int):
        self._master = mavutil.mavlink_connection(
            f"udpin:127.0.0.1:{port}", source_system=P.VEHICLE_SYSTEM_ID,
            source_component=P.VEHICLE_COMPONENT_ID, dialect="common",
        )
        self.bridge = SimBridge(self._master)
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def _run(self):
        last_hb = last_tlm = last_step = time.monotonic()
        while not self._stop.is_set():
            msg = self._master.recv_match(blocking=True, timeout=0.01)
            if msg is not None and msg.get_type() != "BAD_DATA":
                self.bridge.handle(msg)
            now = time.monotonic()
            self.bridge.step(now - last_step)
            last_step = now
            if now - last_hb >= 0.1:
                self.bridge.send_heartbeat()
                last_hb = now
            if now - last_tlm >= 0.05:
                self.bridge.send_telemetry()
                last_tlm = now

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=2)
        self._master.close()


@pytest.fixture
def link():
    port = _free_udp_port()
    bridge = BridgeThread(port)
    bridge.start()
    vehicle = Vehicle.connect(f"udpout:127.0.0.1:{port}")
    try:
        yield vehicle, bridge
    finally:
        vehicle.close()
        bridge.stop()


def test_heartbeat_and_telemetry(link):
    vehicle, _ = link
    tlm = vehicle.wait_ready(timeout=5)
    assert tlm.last_heartbeat > 0
    vehicle.pump(timeout=0.5)
    assert vehicle.telemetry.lat is not None
    assert vehicle.telemetry.satellites == 14
    assert vehicle.telemetry.battery_pct == 78


def test_takeoff_land_cycle(link):
    vehicle, bridge = link
    vehicle.wait_ready(timeout=5)
    vehicle.takeoff(blocking=True, timeout=5)
    assert bridge.bridge.in_air is True
    assert bridge.bridge.alt == pytest.approx(1.2)
    vehicle.land(blocking=True, timeout=5)
    assert bridge.bridge.in_air is False


def test_velocity_moves_vehicle_forward(link):
    vehicle, bridge = link
    vehicle.wait_ready(timeout=5)
    vehicle.takeoff(blocking=True, timeout=5)
    start_north = bridge.bridge.north
    vehicle.set_velocity(forward=2.0, duration=1.0, rate_hz=20)
    assert bridge.bridge.north - start_north > 1.0  # moved ~2 m, allow slack
    # After duration, a hover frame was sent; the vehicle should coast to a stop.
    time.sleep(0.6)
    bridge.bridge.step(0.1)
    settled = bridge.bridge.north
    time.sleep(0.3)
    bridge.bridge.step(0.1)
    assert bridge.bridge.north == pytest.approx(settled, abs=0.05)


def test_velocity_is_clamped_in_bridge(link):
    vehicle, bridge = link
    vehicle.wait_ready(timeout=5)
    vehicle.takeoff(blocking=True, timeout=5)
    # Bypass the client clamp to prove the bridge also clamps.
    vehicle._m.mav.set_position_target_local_ned_send(
        0, P.VEHICLE_SYSTEM_ID, P.VEHICLE_COMPONENT_ID, P.MAV_FRAME_BODY_NED,
        P.VELOCITY_YAWRATE_TYPE_MASK, 0, 0, 0, 99.0, 0, 0, 0, 0, 0, 0, 0,
    )
    time.sleep(0.2)
    assert bridge.bridge.cmd_vel[0] == pytest.approx(P.MAX_HORIZONTAL_MPS)


def test_return_to_home(link):
    vehicle, bridge = link
    vehicle.wait_ready(timeout=5)
    vehicle.takeoff(blocking=True, timeout=5)
    vehicle.set_velocity(forward=3.0, duration=0.5, rate_hz=20)
    assert abs(bridge.bridge.north) > 0.1
    vehicle.return_to_home(blocking=True, timeout=5)
    assert bridge.bridge.north == pytest.approx(0.0)
    assert bridge.bridge.east == pytest.approx(0.0)


def test_unsupported_command_is_rejected(link):
    vehicle, _ = link
    vehicle.wait_ready(timeout=5)
    vehicle._send_command_long(mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM)
    with pytest.raises(CommandError):
        vehicle._await_ack(mavutil.mavlink.MAV_CMD_NAV_LOITER_UNLIM, timeout=3)


def test_no_heartbeat_times_out():
    port = _free_udp_port()
    vehicle = Vehicle.connect(f"udpout:127.0.0.1:{port}")  # nothing listening
    with pytest.raises(CommandError):
        vehicle.wait_ready(timeout=1)
    vehicle.close()


def test_clamp_handles_nan():
    assert _clamp(float("nan"), 5.0) == 0.0
    assert _clamp(10.0, 5.0) == 5.0
    assert _clamp(-10.0, 5.0) == -5.0
