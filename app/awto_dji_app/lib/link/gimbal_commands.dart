import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Gimbal control frames, packed as the vendor app packs them (DataGimbalAngleControl.doPack):
/// yaw, roll, pitch (int16, 0.1 deg), duration (uint16, ms), flags (uint8), overtime (uint8).
/// Sender is the app device type, as in the vendor app.
class GimbalCommands {
  GimbalCommands([this._seq = 0x7500]);
  int _seq;

  static const _deviceOsd = 0x0e;
  static const _defaultFlags = 0x24; // all class defaults, see scripts/re/duml_commands.py

  /// RC cmdset 0x06 / 0x22, receiver OSD: asks for gimbal control before angle commands.
  Uint8List permissionRequest() => DumlPacket(
        senderType: DeviceType.app,
        receiverType: _deviceOsd,
        sequence: _seq++,
        ackType: AckType.afterExec,
        cmdSet: CmdSet.remote,
        cmdId: 0x22,
        payload: Uint8List(0),
      ).encode();

  /// Gimbal cmdset 0x04 / 0x0c (SpeedControl) - confirmed 2026-10-24 against real
  /// dji.pilot decompile (DJIFpvGimbalPitchView.java) as the command the app's own FPV
  /// gimbal UI actually sends, continuously on a 40ms timer while a control button is
  /// held. Permission is embedded in this same packet (byte6 bit7), not a separate
  /// request/ack handshake - [permissionRequest]/[angle] above are for a different
  /// scenario (RC master/slave handoff, third-party SDK), not this control path.
  /// speedDegPerSec: I (inferred) - deg/s, not independently confirmed as a unit; the
  /// real UI's own speed constant is a raw 270.
  Uint8List speedControl({
    double pitchDegPerSec = 0,
    double rollDegPerSec = 0,
    double yawDegPerSec = 0,
    bool takeControl = true,
  }) {
    final payload = ByteData(7)
      ..setInt16(0, (yawDegPerSec * 10).round(), Endian.little)
      ..setInt16(2, (rollDegPerSec * 10).round(), Endian.little)
      ..setInt16(4, (pitchDegPerSec * 10).round(), Endian.little)
      ..setUint8(6, takeControl ? 0x80 : 0x00);
    return DumlPacket(
      senderType: DeviceType.app,
      receiverType: DeviceType.gimbal,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.gimbal,
      cmdId: 0x0c,
      payload: payload.buffer.asUint8List(),
    ).encode();
  }

  /// Gimbal cmdset 0x04 / 0x08 (AutoCalibration) - the gimbal self-test/calibration
  /// trigger. Real class `DataGimbalAutoCalibration.start()` (dji.go.v4 decompile,
  /// `dji/midware/data/model/P3/DataGimbalAutoCalibration.java`) sends APP->GIMBAL,
  /// `NEEDACK.YES`, `EncryptType.NO`, 1-byte payload from `getSendData()`.
  ///
  /// V, confirmed 2026-10-24 against a real wire capture of this exact command
  /// working (real pitch movement + mode change observed, see awto-dji#16):
  /// `550e046602040074200408008c2f` -> sender=APP, receiver=GIMBAL, ackType=
  /// beforeExec (byte8 bits5-6 = 1), cmdSet=0x04, cmdId=0x08, payload=[0x00].
  Uint8List autoCalibration() => DumlPacket(
        senderType: DeviceType.app,
        receiverType: DeviceType.gimbal,
        sequence: _seq++,
        ackType: AckType.beforeExec,
        cmdSet: CmdSet.gimbal,
        cmdId: 0x08,
        payload: Uint8List.fromList([0]),
      ).encode();

  /// Gimbal cmdset 0x04 / 0x0a, angles in degrees.
  Uint8List angle({
    double pitch = 0,
    double roll = 0,
    double yaw = 0,
    int durationMs = 300,
    int overtime = 10,
  }) {
    final payload = ByteData(10)
      ..setInt16(0, (yaw * 10).round(), Endian.little)
      ..setInt16(2, (roll * 10).round(), Endian.little)
      ..setInt16(4, (pitch * 10).round(), Endian.little)
      ..setUint16(6, durationMs, Endian.little)
      ..setUint8(8, _defaultFlags)
      ..setUint8(9, overtime);
    return DumlPacket(
      senderType: DeviceType.app,
      receiverType: DeviceType.gimbal,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.gimbal,
      cmdId: 0x0a,
      payload: payload.buffer.asUint8List(),
    ).encode();
  }
}
