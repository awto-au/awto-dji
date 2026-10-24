/// Decoder for the Flight Controller "OSD General Data" push
/// (`cmd_set = 0x03`, `cmd_id = 0x43`, "GetPushCommon" per duml_catalog.py), the main
/// telemetry message.
///
/// Field offsets 0-29 (lon/lat/height/vgx/vgy/vgz/pitch/roll/yaw) were originally
/// taken from the public o-gs/dji-firmware-tools Wireshark dissector; offsets 30-52
/// (motor/compass/IMU/gimbal-health flags) are a byte-for-byte port of the real
/// `dji.midware.data.model.P3.DataOsdGetPushCommon` decompile (dji.go.v4, found under
/// `tmp/apk/dynamic/decompiled/sources/...`, gitignored - not in this repo) - **V**,
/// all offsets confirmed against that class's own `get(offset, len, ...)` calls.
///
/// Same class is also registered for cmdset 0x09 ("hdLink"/OSD) id 0x01
/// (`CmdSet.java`: `OSD(9, ...).GetPushCommon(1, false, DataOsdGetPushCommon.class)`,
/// alongside `FLYC(3, ...).GetPushCommon(67, false, DataOsdGetPushCommon.class)`) -
/// the exact same struct answers under two different cmdset/cmdid pairs. [matches]
/// accepts either. **I (inferred), not confirmed live**: this may explain why 0x03/
/// 0x43 alone never appeared in the full session capture (awto-dji#16) - worth
/// re-checking the capture against 0x09/0x01 before assuming this push is absent.
///
/// U (unknown), not V, for the underlying telemetry itself: checked 2026-10-24
/// against the full session capture (~44MB, ~2.5h) via the Python port of this
/// decoder (scripts/re/duml_telemetry.py) - cmdset/cmdid 0x03/0x43 never appears, not
/// once. Treat [matches] returning true as untested in practice until this is
/// resolved - see awto-dji#16.
library;

import 'dart:math' as math;
import 'dart:typed_data';

import 'motor_status.dart';
import 'packet.dart';

class OsdGeneral {
  /// Degrees (converted from the radians DJI sends).
  final double longitude;
  final double latitude;

  /// Metres above the home point.
  final double relativeHeight;

  /// Ground-frame velocity, metres/second.
  final double vgx;
  final double vgy;
  final double vgz;

  /// Degrees.
  final double pitch;
  final double roll;
  final double yaw;

  /// `isMotorUp()` - bit 3 of the flags int32 at offset 32. Only meaningful once
  /// [motorBlocked] is false and [motorFailedCause] is [MotorStartFailedCause.none];
  /// null if the payload was too short to reach offset 32-35.
  final bool? motorUp;

  /// `isMotorBlock()` - bit 27 of the same flags int32: the motor-arming interlock
  /// (props-off / no-arm) is engaged. The companion "why" is [motorFailedCause].
  final bool? motorBlocked;

  /// `getCompassError()` - bit 16 of the flags int32.
  final bool? compassError;

  /// `isImuPreheatd()` - bit 12 of the flags int32 (also true when the payload is
  /// absent, per the real getter - not reproduced here since this type only exists
  /// once a payload has been decoded).
  final bool? imuPreheated;

  /// `getMotorFailedCause()` - why the arming interlock is up, or the live fault if
  /// the motors are already spinning. Also doubles as a coarse gimbal-health flag
  /// (`gimbalDisorder`/`gimbalPitchShock`/etc) - see `motor_status.dart`.
  final MotorStartFailedCause? motorFailedCause;

  /// `getIMUinitFailReason()` - IMU self-check / calibration-in-progress state.
  final ImuInitFailReason? imuInitFailReason;

  /// `getFlycVersion()` - the FC's own protocol/firmware generation number, offset
  /// 47. Needed to pick the right decode path for [motorFailedCause] (ported as-is
  /// from the real getter); also useful on its own as a coarse version readout.
  final int? flycVersion;

  OsdGeneral({
    required this.longitude,
    required this.latitude,
    required this.relativeHeight,
    required this.vgx,
    required this.vgy,
    required this.vgz,
    required this.pitch,
    required this.roll,
    required this.yaw,
    this.motorUp,
    this.motorBlocked,
    this.compassError,
    this.imuPreheated,
    this.motorFailedCause,
    this.imuInitFailReason,
    this.flycVersion,
  });

  static const int cmdSet = CmdSet.flightController;
  static const int cmdId = 0x43;

  /// True if `p` is an OSD General push this decoder understands. Accepts either of
  /// the two cmdset/cmdid pairs the real `DataOsdGetPushCommon` class is registered
  /// under (see the class doc comment) - 0x03/0x43 as a request/response, or the
  /// `hdLink`/OSD alias at 0x09/0x01.
  static bool matches(DumlPacket p) =>
      ((p.cmdSet == cmdSet && p.cmdId == cmdId) ||
          (p.cmdSet == CmdSet.hdLink && p.cmdId == 0x01)) &&
      p.payload.length >= 30;

  /// Decode from a packet, or return null if it is not an OSD General push.
  static OsdGeneral? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return fromPayload(p.payload);
  }

  static OsdGeneral fromPayload(Uint8List payload) {
    final d = ByteData.sublistView(payload);
    const degPerRad = 180.0 / math.pi;

    int? flycVersion;
    bool? motorUp, motorBlocked, compassError, imuPreheated;
    MotorStartFailedCause? motorFailedCause;
    ImuInitFailReason? imuInitFailReason;

    // offset 47: 1 byte -> needs length >= 48.
    if (payload.length >= 48) flycVersion = d.getUint8(47);
    // offset 32: 4-byte flags int -> needs length >= 36.
    if (payload.length >= 36) {
      final flags = d.getUint32(32, Endian.little);
      motorUp = (flags >> 3) & 1 == 1;
      motorBlocked = (flags >> 27) & 1 != 0;
      compassError = flags & 0x10000 != 0;
      imuPreheated = flags & 0x1000 != 0;
    }
    // offset 38 (+ offset 51 for the pre-flycVersion-26 no-start-action case).
    if (payload.length >= 39 && flycVersion != null) {
      final raw38 = d.getUint8(38);
      if (flycVersion >= 26) {
        motorFailedCause = MotorStartFailedCause.find(raw38);
      } else if ((raw38 >> 7) == 0) {
        motorFailedCause = MotorStartFailedCause.none;
      } else if (payload.length <= 51) {
        motorFailedCause = MotorStartFailedCause.find(raw38 & 0x7f);
      } else {
        motorFailedCause = MotorStartFailedCause.find(d.getUint8(51) & 0xff);
      }
    }
    // offset 49: 1 byte -> needs length >= 50.
    if (payload.length >= 50) imuInitFailReason = ImuInitFailReason.find(d.getUint8(49));

    return OsdGeneral(
      longitude: d.getFloat64(0, Endian.little) * degPerRad,
      latitude: d.getFloat64(8, Endian.little) * degPerRad,
      relativeHeight: d.getInt16(16, Endian.little) / 10.0,
      vgx: d.getInt16(18, Endian.little) / 10.0,
      vgy: d.getInt16(20, Endian.little) / 10.0,
      vgz: d.getInt16(22, Endian.little) / 10.0,
      pitch: d.getInt16(24, Endian.little) / 10.0,
      roll: d.getInt16(26, Endian.little) / 10.0,
      yaw: d.getInt16(28, Endian.little) / 10.0,
      motorUp: motorUp,
      motorBlocked: motorBlocked,
      compassError: compassError,
      imuPreheated: imuPreheated,
      motorFailedCause: motorFailedCause,
      imuInitFailReason: imuInitFailReason,
      flycVersion: flycVersion,
    );
  }

  @override
  String toString() => 'OSD(lat=${latitude.toStringAsFixed(6)} '
      'lon=${longitude.toStringAsFixed(6)} h=${relativeHeight}m '
      'v=(${vgx},${vgy},${vgz}) att=(${roll},${pitch},${yaw}) '
      'motor=(up=$motorUp blocked=$motorBlocked cause=${motorFailedCause?.name}))';
}
