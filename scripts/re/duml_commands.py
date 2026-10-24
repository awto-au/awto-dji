"""Declarative DUML command payloads: one ctypes.LittleEndianStructure per command,
byte-for-byte matching the real doPack() layout found in the dynamically-unpacked APK
(dji.midware.data.model.P3.*) - not the generic public dissector, which is wrong for
several P3 commands (see docs/apk-vs-dissector-gap-report-2026-10-23.md).

Add a new command by adding one Structure + one REGISTRY entry - duml_cli.py drives any
of them generically, no per-command CLI code needed.
"""
import ctypes as C

from duml_proto import DeviceType

ACK_NONE, ACK_BEFORE, ACK_AFTER = 0, 1, 2
DEFAULT_FLAGS = 0x24  # see GimbalAngleControl docstring


class GimbalAngleControl(C.LittleEndianStructure):
    """CmdSet.GIMBAL/0x04 id=0x0a (AngleControl). Source: DataGimbalAngleControl.java.
    flags byte: the real doPack() bit-packs permission/mode flags here via a shift chain
    that (by direct calculation) discards everything except one bit from byte truncation -
    treated as an opaque byte, not decoded further; 0x24 is the all-class-defaults value
    (permission=False, the three APK-default-True flags) and is what we've tested with.
    """
    _pack_ = 1
    _fields_ = [
        ("yaw", C.c_int16),      # degrees * 10
        ("roll", C.c_int16),     # degrees * 10
        ("pitch", C.c_int16),    # degrees * 10
        ("duration", C.c_uint16),  # ms, APK default 300
        ("flags", C.c_uint8),
        ("overtime", C.c_uint8),
    ]


class GimbalControl(C.LittleEndianStructure):
    """CmdSet.GIMBAL/0x04 id=0x01 (Control) - simpler mode-based control.
    Source: DataGimbalControl.java. mode: 0=YawNoFollow 1=FPV 2=YawFollow."""
    _pack_ = 1
    _fields_ = [
        ("pitch", C.c_int16),
        ("roll", C.c_int16),
        ("yaw", C.c_int16),
        ("mode_byte", C.c_uint8),  # (mode << 6) | (isReset << 5)
    ]


class CameraRequestIFrame(C.LittleEndianStructure):
    """CmdSet.CAMERA/0x02 id=0xb3 - no payload. Forces an SPS/PPS/IDR resend
    (docs/aoa-live-test-2026-10-23.md)."""
    _pack_ = 1
    _fields_: list = []


class RcRequestGimbalCtrPermission(C.LittleEndianStructure):
    """CmdSet.RC/0x06 id=0x22 - empty payload. Receiver is DeviceType.osd (14), not RC -
    DJI's own class targets that device type despite the cmdset being named RC. Must be
    sent (and presumably acked) before AngleControl/Control commands are honored - this
    was the missing step the first two gimbal-move attempts silently failed on.
    Source: DataRcRequestGimbalCtrPermission.java."""
    _pack_ = 1
    _fields_: list = []


# name -> (cmd_set, cmd_id, sender, receiver, PayloadStruct, {field: scale}, {field: default})
# scale: CLI value is multiplied by this before being stored in the field (e.g. degrees
# -> degrees*10). defaults: used for any field not given on the command line - matches
# the APK's own class field defaults (see each Structure's docstring for the source).
REGISTRY = {
    "gimbal.angle": (
        0x04, 0x0A, DeviceType.app, DeviceType.gimbal, GimbalAngleControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        {"duration": 300, "flags": DEFAULT_FLAGS, "overtime": 0},
    ),
    "gimbal.control": (
        0x04, 0x01, DeviceType.app, DeviceType.gimbal, GimbalControl, {}, {},
    ),
    "camera.requestIFrame": (
        0x02, 0xB3, DeviceType.pc, DeviceType.camera, CameraRequestIFrame, {}, {},
    ),
    "gimbal.requestCtrPermission": (
        0x06, 0x22, DeviceType.app, DeviceType.osd, RcRequestGimbalCtrPermission, {}, {},
    ),
}
