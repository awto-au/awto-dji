import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Device-diagnostic query commands - General/0x00 cmdset, request-only (no
/// confirmed payload besides the empty query itself; reply struct is
/// `duml`'s `CommonVersion`).
class DiagnosticsCommands {
  DiagnosticsCommands([this._seq = 0x7a00]);
  int _seq;

  /// General/0x00/0x01 (`GetVersion` per duml_catalog.py). Real class
  /// `DataCommonGetVersion.start()`/`startForce()` (dji.go.v4 decompile) sends this
  /// with an empty payload to whichever device should answer - [receiverType]
  /// selects it (e.g. `DeviceType.flightController`, `DeviceType.gimbal`,
  /// `DeviceType.camera`). The reply is decoded by `duml`'s `CommonVersion`, matched
  /// on cmdSet/cmdId alone (not keyed back to this specific request).
  Uint8List getVersion({required int receiverType}) => DumlPacket(
        senderType: DeviceType.app,
        receiverType: receiverType,
        sequence: _seq++,
        ackType: AckType.afterExec,
        cmdSet: CmdSet.general,
        cmdId: 0x01,
        payload: Uint8List(0),
      ).encode();
}
