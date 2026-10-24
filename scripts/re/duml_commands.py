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
    """CmdSet.GIMBAL/0x04 id=0x0a (AngleControl). Source: DataGimbalAngleControl.java,
    confirmed 2026-10-24 against real dji.pilot decompile (dynamic/memscan unpack, not
    just the earlier dji.go.v4 static pass).
    flags byte: doPack() bit-packs permission/mode flags via a shift chain where each step
    re-casts to byte and shifts left again, so most of the earlier bits are destroyed by
    the later shifts - verified by hand-tracing doPack() with all-class-defaults
    (permission=False, the three APK-default-True flags), which gives exactly 0x24,
    confirming this isn't a decode gap - the byte genuinely only carries ~1 surviving bit
    of information. Treated as opaque; 0x24 is what we've tested with.
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


class GimbalAbsAngleControl(C.LittleEndianStructure):
    """CmdSet.GIMBAL/0x04 id=0x14 (AbsAngleControl). Source:
    DataGimbalAbsAngleControl.java - a distinct, separately-documented command from
    AngleControl (0x0a) above, not a variant of it: no duration field, and the flags
    byte is explicit here (not opaque): bit0 controlMode, bit1 yawInvalid,
    bit2 rollInvalid, bit3 pitchInvalid ("invalid" = ignore this axis, hold current
    position). Field layout confirmed byte-for-byte 2026-10-24 against real dji.pilot
    decompile. Defaults below (yaw/roll invalid, pitch only) match a real-hardware
    test (2026-10-24, Codex session) and the class's own overtime default (10); the
    app's own un-set default is flags=0 (all axes valid) - not yet confirmed our
    pitch-only default is required for this to work, only that it's what was tested.
    """
    _pack_ = 1
    _fields_ = [
        ("yaw", C.c_int16),      # degrees * 10
        ("roll", C.c_int16),     # degrees * 10
        ("pitch", C.c_int16),    # degrees * 10
        ("flags", C.c_uint8),
        ("overtime", C.c_uint8),
    ]


ABS_ANGLE_FLAGS = {"controlMode": 1, "yawInvalid": 2, "rollInvalid": 4, "pitchInvalid": 8}


class GimbalControl(C.LittleEndianStructure):
    """CmdSet.GIMBAL/0x04 id=0x01 (Control) - simpler mode-based control.
    Source: DataGimbalControl.java, field order (pitch/roll/yaw/mode_byte) and
    mode_byte=(mode<<6)|(isReset<<5) confirmed byte-for-byte 2026-10-24 against real
    dji.pilot decompile. mode: 0=YawNoFollow 1=FPV 2=YawFollow (enum also has
    OTHER=100, not used)."""
    _pack_ = 1
    _fields_ = [
        ("pitch", C.c_int16),
        ("roll", C.c_int16),
        ("yaw", C.c_int16),
        ("mode_byte", C.c_uint8),  # (mode << 6) | (isReset << 5)
    ]


class GimbalSpeedControl(C.LittleEndianStructure):
    """CmdSet.GIMBAL/0x04 id=0x0c (SpeedControl). Source: DataGimbalSpeedControl.java.

    THIS is the command the real app actually uses for interactive single-pilot gimbal
    control - confirmed 2026-10-24 against dji.pilot's real FPV gimbal UI
    (DJIFpvGimbalPitchView.java): sent continuously on a 40ms Timer while a control
    button is held (setPermission(true) + speed), then one final
    setPermission(false)+zero-speed send on release. An exhaustive call-site search of
    the whole decompiled app found AngleControl/AbsAngleControl/Control/
    RequestGimbalCtrPermission used only for RC master/slave handoff and the third-party
    Mobile SDK layer - NOT this app's own gimbal control path. This likely explains the
    whole session's gimbal-move failures: wrong command family entirely, not a payload
    or permission-sequencing bug in the ones tried.

    Permission is embedded as bit7 of byte 6 in THIS SAME packet - there is no separate
    request/ack handshake for interactive control (gimbal.requestCtrPermission appears
    to be for the master/slave scenario above, not this flow - matches it never getting
    a reply all session).

    Speed scale: I (inferred) - deg/s*10 by analogy with this project's existing *10
    convention; the UI's own speed constant is 270 (DJIFpvGimbalPitchView$2/$3.java),
    not independently confirmed as a unit.
    """
    _pack_ = 1
    _fields_ = [
        ("yaw", C.c_int16),
        ("roll", C.c_int16),
        ("pitch", C.c_int16),
        ("flags", C.c_uint8),  # bit7 = permission (1=take control, 0=release)
    ]


GIMBAL_SPEED_PERMISSION_BIT = 0x80


class CameraRequestIFrame(C.LittleEndianStructure):
    """CmdSet.CAMERA/0x02 id=0xb3 - no payload. Forces an SPS/PPS/IDR resend
    (docs/aoa-live-test-2026-10-23.md)."""
    _pack_ = 1
    _fields_: list = []


class RcRequestGimbalCtrPermission(C.LittleEndianStructure):
    """CmdSet.RC/0x06 id=0x22 - empty payload. Receiver is DeviceType.osd (14), not RC -
    DJI's own class targets that device type despite the cmdset being named RC.

    UPDATE 2026-10-24: this does NOT appear to be a prerequisite for interactive gimbal
    control - an exhaustive call-site search of the real dji.pilot app found this class
    used only for the RC master/slave handoff scenario and the third-party Mobile SDK
    layer, never in the app's own single-pilot FPV gimbal UI (which uses
    GimbalSpeedControl instead, with permission embedded in that packet - see its
    docstring). Consistent with this command never getting a reply all session despite
    being sent before every AngleControl/AbsAngleControl attempt. Kept for the
    master/slave scenario; don't assume it's needed for GimbalSpeedControl.
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
    "gimbal.speedControl": (
        0x04, 0x0C, DeviceType.app, DeviceType.gimbal, GimbalSpeedControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        # flags default to the permission bit set (take control) - the real app sends
        # this continuously while a button is held; for a one-shot test, send this a
        # few times in a row (no separate permission request needed, see docstring).
        {"flags": GIMBAL_SPEED_PERMISSION_BIT},
    ),
    "gimbal.absAngle": (
        0x04, 0x14, DeviceType.app, DeviceType.gimbal, GimbalAbsAngleControl,
        {"yaw": 10, "roll": 10, "pitch": 10},
        # flags=6: yawInvalid|rollInvalid (pitch-only) - the one config with real-
        # hardware precedent so far; override with --flags for other axis combos.
        {"flags": 6, "overtime": 10},
    ),
    "camera.requestIFrame": (
        0x02, 0xB3, DeviceType.app, DeviceType.camera, CameraRequestIFrame, {}, {},
    ),
    "gimbal.requestCtrPermission": (
        0x06, 0x22, DeviceType.app, DeviceType.osd, RcRequestGimbalCtrPermission, {}, {},
    ),
}
