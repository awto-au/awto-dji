/// Decoder for the RC/OSD link signal-quality push (`cmd_set = 0x09` "hdLink",
/// `cmd_id = 0x08`), sent by the OSD device (sender type 14) at ~a few Hz.
///
/// I (inferred, not confirmed against decompiled source): byte 0 is a constant
/// tag (0x35 in every capture so far); bytes 1-2 are signed int8 dBm readings,
/// one per antenna/diversity path. Basis: live capture 2026-10-24 with RC and
/// aircraft ~1m apart showed a stable, narrow range (-33 to -27 dBm as signed
/// bytes) for ~2.5 hours - consistent with two strong dBm readings, not with a
/// 0-255 percentage (which this range would read as a flatly maxed-out ~87-90%,
/// an odd thing for a push to bother sending continuously). DJI GO's own UI
/// called this link "weak" at the same time, which this decode contradicts -
/// see awto-dji#16. Re-check against decompiled dji.pilot/dji.go.v4 source if
/// that class is ever found, and update this docstring, not just the code.
library;

import 'dart:typed_data';

import 'packet.dart';

class RcSignalQuality {
  final int antenna1Dbm;
  final int antenna2Dbm;

  const RcSignalQuality({required this.antenna1Dbm, required this.antenna2Dbm});

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
    return RcSignalQuality(
      antenna1Dbm: signed8(payload[1]),
      antenna2Dbm: signed8(payload[2]),
    );
  }

  /// The stronger (less negative) of the two antenna readings.
  int get bestDbm => antenna1Dbm > antenna2Dbm ? antenna1Dbm : antenna2Dbm;

  @override
  String toString() => 'RcSignal(ant1=${antenna1Dbm}dBm ant2=${antenna2Dbm}dBm)';
}
