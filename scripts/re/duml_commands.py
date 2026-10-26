"""Declarative DUML command payloads - REGISTRY maps a friendly name to the generic
CLI metadata (cmdset/cmdid/sender/receiver/struct/scale/defaults) that duml_cli.py
drives generically.

All payload structs are now schema-generated (docs/schema/duml/commands.yaml,
awto-dji#33) - do not hand-write a new ctypes.Structure here. Add a new command by
adding an entry to that YAML, regenerating (`python3 -I scripts/re/gen_duml_schema.py`),
then one REGISTRY line below pointing at the generated class.
"""
from duml_generated.camera_request_i_frame import CameraRequestIFrame
from duml_generated.gimbal_abs_angle_control import GimbalAbsAngleControl
from duml_generated.gimbal_angle_control import GimbalAngleControl
from duml_generated.gimbal_auto_calibration import GimbalAutoCalibration
from duml_generated.gimbal_control import GimbalControl
from duml_generated.gimbal_speed_control import GimbalSpeedControl
from duml_generated.rc_request_gimbal_ctr_permission import RcRequestGimbalCtrPermission
from duml_generated.restart_device import RestartDevice
from duml_proto import DeviceType

ACK_NONE, ACK_BEFORE, ACK_AFTER = 0, 1, 2

# name -> (cmd_set, cmd_id, sender, receiver, PayloadStruct, {field: scale}, {field: default})
# scale/defaults operate on the struct's raw ctypes _fields_ (wire-level names, e.g.
# "mode_byte"/"flags" for the packed-bit commands below) - duml_cli.py sets those
# directly, it does not call the generated class's friendly __init__. Calling the
# class directly in Python (or from Dart) uses the friendly constructor instead
# (e.g. GimbalControl(mode=1, isReset=True)) - see docs/schema/duml/generated/*.md.
REGISTRY = {
    "gimbal.angle": (
        0x04, 0x0A, DeviceType.app, DeviceType.gimbal, GimbalAngleControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        {"duration": 300, "flags": 0x24, "overtime": 0},
    ),
    "gimbal.control": (
        0x04, 0x01, DeviceType.app, DeviceType.gimbal, GimbalControl, {}, {},
    ),
    "gimbal.speedControl": (
        0x04, 0x0C, DeviceType.app, DeviceType.gimbal, GimbalSpeedControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        # flags default to the permission bit set (take control) - the real app sends
        # this continuously while a button is held; for a one-shot test, send this a
        # few times in a row (no separate permission request needed, see the schema doc).
        {"flags": 0x80},
    ),
    "gimbal.absAngle": (
        0x04, 0x14, DeviceType.app, DeviceType.gimbal, GimbalAbsAngleControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        # flags=6: yawInvalid|rollInvalid (pitch-only) - the one config with real-
        # hardware precedent so far; override with --flags for other axis combos.
        {"flags": 6, "overtime": 10},
    ),
    "gimbal.autoCalibration": (
        0x04, 0x08, DeviceType.app, DeviceType.gimbal, GimbalAutoCalibration, {}, {},
    ),
    "camera.requestIFrame": (
        0x02, 0xB3, DeviceType.app, DeviceType.camera, CameraRequestIFrame, {}, {},
    ),
    "gimbal.requestCtrPermission": (
        0x06, 0x22, DeviceType.app, DeviceType.osd, RcRequestGimbalCtrPermission, {}, {},
    ),
    # COMMON/RestartDevice - generic, not RC-specific (docs/schema/duml/commands.yaml,
    # awto-dji#33). DeviceType.osd here is only the real-hardware-tested default; override
    # with --receiver for the FC/gimbal/camera/etc.
    "restartDevice": (
        0x00, 0x0B, DeviceType.app, DeviceType.osd, RestartDevice,
        {}, {"mode": 1, "watchdog_ms": 1000},
    ),
}
