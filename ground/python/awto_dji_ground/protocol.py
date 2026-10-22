"""The MAVLink control contract shared by the Android bridge and the ground clients.

The Android app (DJI Mobile SDK v4) is the *vehicle* side. A ground client is the
*GCS* side. They exchange standard MAVLink v2 ``common`` dialect messages over UDP, so
QGroundControl and any other MAVLink tool also work against the bridge.

Only a small, deliberate subset is used, listed here so the bridge and the clients
cannot drift apart.
"""

from __future__ import annotations

# System / component ids.
VEHICLE_SYSTEM_ID = 1
VEHICLE_COMPONENT_ID = 1  # MAV_COMP_ID_AUTOPILOT1
GCS_SYSTEM_ID = 255
GCS_COMPONENT_ID = 190  # MAV_COMP_ID_MISSIONPLANNER

# Telemetry stream rates the bridge targets, in Hz.
TELEMETRY_HZ = 10
HEARTBEAT_HZ = 1

# Custom flight-mode numbers the bridge reports in HEARTBEAT.custom_mode. DJI's SDK
# does not expose PX4/ArduPilot modes, so we define our own small set.
class FlightMode:
    UNKNOWN = 0
    MANUAL = 1       # sticks on the real RC
    HOLD = 2         # GPS position hold, no virtual-stick input
    GUIDED = 3       # accepting velocity / go-to from the GCS (virtual sticks enabled)
    TAKEOFF = 4
    LANDING = 5
    RTL = 6          # return to home

    _NAMES = {
        UNKNOWN: "UNKNOWN", MANUAL: "MANUAL", HOLD: "HOLD", GUIDED: "GUIDED",
        TAKEOFF: "TAKEOFF", LANDING: "LANDING", RTL: "RTL",
    }

    @classmethod
    def name(cls, mode: int) -> str:
        return cls._NAMES.get(mode, f"MODE_{mode}")


# Velocity command frame. We use MAV_FRAME_BODY_NED so +vx is "forward" relative to the
# aircraft nose, matching how DJI virtual-stick pitch/roll are interpreted.
MAV_FRAME_BODY_NED = 8

# SET_POSITION_TARGET_LOCAL_NED type_mask: ignore everything except the three velocity
# components and yaw_rate. Bits set = field ignored.
#   pos x/y/z (bits 0-2), vel x/y/z (3-5), acc x/y/z (6-8), force (9), yaw (10), yaw_rate (11)
IGNORE_POS = 0b0000000000000111
IGNORE_ACC = 0b0000000111000000
IGNORE_YAW = 0b0000010000000000
VELOCITY_YAWRATE_TYPE_MASK = IGNORE_POS | IGNORE_ACC | IGNORE_YAW | 0  # keep vel + yaw_rate

# Conservative envelope the bridge enforces on velocity commands, independent of the
# client, so a bad client cannot command full speed. metres/second and deg/second.
MAX_HORIZONTAL_MPS = 5.0
MAX_VERTICAL_MPS = 3.0
MAX_YAW_DPS = 90.0
