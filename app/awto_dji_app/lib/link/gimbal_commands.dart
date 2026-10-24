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
