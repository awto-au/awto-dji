import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Ground/RC-level control commands - distinct from gimbal/flight commands.
class GroundCommands {
  GroundCommands([this._seq = 0x6f00]);
  int _seq;

  static const _deviceOsd = 0x0e; // the receiver that actually answers on the RC

  /// RestartDevice, General/0x00/0x0b - confirmed against real hardware 2026-10-24
  /// (see docs/rc-restart-device-confirmed.md): RC's own USB-serial device
  /// re-enumerated and its DUML sequence counter reset to 0 right when this was sent.
  /// Payload (docs/ground-upgrade-path.md, m1400 handler 0x5124): byte0 reserved
  /// (send 0), byte1 must be 0 or 1 (else error 0xE3), bytes2-5 = u32 LE watchdog
  /// timeout ms - after the ack it stops feeding the watchdog, which resets the chip
  /// after this many ms. 1000ms is untried-elsewhere-but-conservative, not measured
  /// as a minimum.
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
