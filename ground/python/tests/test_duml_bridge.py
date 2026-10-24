"""The real-data bridge (duml_bridge.py) against a synthetic relay-log file - no DJI
hardware, no simulated point-mass, just the actual log-line format and decoders."""

from __future__ import annotations

import tempfile
import threading
import time

import pytest
from pymavlink import mavutil

from awto_dji_ground import protocol as P
from awto_dji_ground.duml_bridge import run


def _free_udp_port() -> int:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture
def bridge_link():
    # Real line shape from captures/sessions/2026-10-24/aoa_relay_frames.log - one
    # signal-quality push (OSD General never actually appears in real captures yet,
    # see docs/known-telemetry-and-commands.md, so this is the one real decoder path
    # this test can exercise against actual wire-shaped data).
    log = tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False)
    log.write("2026-10-24T15:00:00 sender=0x0e receiver=0x02 seq=1 type=0x03 "
               "set=0x09 id=0x08 protection=3 payload=35e1e1\n")
    log.flush()
    port = _free_udp_port()
    ready = threading.Event()
    thread = threading.Thread(
        target=run, args=(log.name, f"udpin:127.0.0.1:{port}", True, 2.0),
        kwargs={"ready": ready}, daemon=True,
    )
    thread.start()
    assert ready.wait(timeout=3), "bridge socket never bound"
    client = mavutil.mavlink_connection(
        f"udpout:127.0.0.1:{port}", source_system=P.GCS_SYSTEM_ID,
        source_component=P.GCS_COMPONENT_ID, dialect="common",
    )
    try:
        yield client
    finally:
        client.close()
        thread.join(timeout=3)


def _announce(client) -> None:
    # UDP is connectionless: the bridge (a "udpin" server) only learns the client's
    # address once it has received something FROM it - matching how Vehicle in
    # client.py sends its own heartbeat on connect for the same reason.
    client.mav.heartbeat_send(
        mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0,
    )


def test_heartbeat_arrives(bridge_link):
    _announce(bridge_link)
    msg = bridge_link.recv_match(type="HEARTBEAT", blocking=True, timeout=3)
    assert msg is not None


def test_real_signal_quality_becomes_radio_status(bridge_link):
    _announce(bridge_link)
    msg = bridge_link.recv_match(type="RADIO_STATUS", blocking=True, timeout=3)
    assert msg is not None
    # aggregate_quality=53 (0x35 & 0x7f) * 2 = 106, matching duml_bridge.py's scaling.
    assert msg.rssi == 106
