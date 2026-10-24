/// Decoder for the RC/OSD link signal-quality push (`cmd_set = 0x09` "hdLink",
/// `cmd_id = 0x08`), sent by the OSD device (sender type 14) at ~a few Hz.
///
/// V (confirmed 2026-10-24 against decompiled `DataOsdGetPushSignalQuality.java`,
/// dji.go.v4 - dji.pilot's own copy could not be recovered, see awto-dji#16, but this
/// struct is aircraft/OSD-side protocol, not app-specific):
/// - byte 0 bit 7: direction (set = Up/uplink, clear = Down/downlink).
/// - byte 0 bits 0-6 (`& 0x7F`): the aggregate link quality, 0-127 - this is what
///   `getDownSignalQuality()`/`getUpSignalQuality()` return, almost certainly what
///   drives the app's own "weak"/"strong" UI label.
/// - bytes 1-2: per-antenna signed dBm readings (secondary breakdown, not the
///   headline metric - a prior version of this file wrongly treated these two as
///   the primary signal and concluded the link was strong while byte 0 - the real
///   quality field - was reporting a mediocre ~42% the whole time).
library;

import 'dart:typed_data';

import 'packet.dart';

class RcSignalQuality {
  /// 0-127.
  final int aggregateQuality;
  final bool isUplink;
  final int antenna1Dbm;
  final int antenna2Dbm;

  const RcSignalQuality({
    required this.aggregateQuality,
    required this.isUplink,
    required this.antenna1Dbm,
    required this.antenna2Dbm,
  });

  static const int cmdSet = CmdSet.hdLink;
  static const int cmdId = 0x08;

  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.length >= 3;

  static RcSignalQuality? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return fromPayload(p.payload);
  }

  static RcSignalQuality fromPayload(Uint8List payload) {
    int signed8(int byte) => byte >= 128 ? byte - 256 : byte;
    final byte0 = payload[0];
    return RcSignalQuality(
      aggregateQuality: byte0 & 0x7F,
      isUplink: (byte0 & 0x80) != 0,
      antenna1Dbm: signed8(payload[1]),
      antenna2Dbm: signed8(payload[2]),
    );
  }

  /// 0-100, matching the scale a UI percentage/bar would use.
  double get qualityPercent => aggregateQuality / 127 * 100;

  @override
  String toString() => 'RcSignal(${isUplink ? "up" : "down"} '
      'quality=$aggregateQuality/127 ant1=${antenna1Dbm}dBm ant2=${antenna2Dbm}dBm)';
}
