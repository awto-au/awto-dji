import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Ground/RC-level control commands - distinct from gimbal/flight commands.
class GroundCommands {
  GroundCommands([this._seq = 0x6f00]);
  int _seq;

  static const _deviceOsd = 0x0e; // the receiver that actually answers on the RC

  /// RestartDevice, General/0x00/0x0b - see docs/ground-upgrade-path.md
  /// ("0x0B Reboot Chip") for hardware confirmation and payload layout
  /// (m1400 handler 0x5124).
  Uint8List restartDevice({int watchdogMs = 1000}) {
    final payload = ByteData(6)
      ..setUint8(0, 0)
      ..setUint8(1, 1)
      ..setUint32(2, watchdogMs, Endian.little);
    return DumlPacket(
      senderType: DeviceType.app,
      receiverType: _deviceOsd,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.general,
      cmdId: 0x0b,
      payload: payload.buffer.asUint8List(),
    ).encode();
  }
}
