/// Decoder for the `GetVersion` reply (`cmd_set = 0x00` "COMMON"/general,
/// `cmd_id = 0x01`), one of the few `Get*` commands in the APK catalog whose reply
/// struct we actually have source for.
///
/// V (byte-for-byte port of `dji.midware.data.model.P3.DataCommonGetVersion`'s
/// `getHardwareVer`/`getFirmVer`/`getLoader`/`getInfo` getters, found in the
/// decompiled dji.go.v4 under `tmp/apk/dynamic/decompiled/sources/...`, gitignored -
/// not in this repo): any device (flight controller, gimbal, camera, RC...) answers
/// its own `GetVersion` request with this same 29-byte-minimum layout, identified on
/// the wire only by which device sent the reply (`DumlPacket.senderType`), not by
/// payload content. Not yet cross-checked against a live capture - see awto-dji#16.
library;

import 'dart:typed_data';

import 'packet.dart';

class CommonVersion {
  /// 16 raw bytes at payload offset 1 (`get(1, 16)` in the real class) - ASCII
  /// hardware-revision string, NUL-padded.
  final String hardwareVersion;

  /// `"%02d.%02d.%02d.%02d"` from payload bytes 24,23,22,21 (firmware).
  final String firmwareVersion;

  /// Same format from bytes 20,19,18,17 (bootloader).
  final String loaderVersion;

  /// Bit 31 of the little-endian int32 at offset 25 (`getInfo().isProduction`).
  final bool isProduction;

  /// Bit 30 of the same int32 (`getInfo().isSupportSafeUpgrade`).
  final bool isSupportSafeUpgrade;

  const CommonVersion({
    required this.hardwareVersion,
    required this.firmwareVersion,
    required this.loaderVersion,
    required this.isProduction,
    required this.isSupportSafeUpgrade,
  });

  static const int cmdSet = CmdSet.general;
  static const int cmdId = 0x01;

  /// Needs offsets 0..28 (the info int32 ends at 28), so 29 bytes minimum. Does not
  /// check [DumlPacket.packetType]: the real class reads this from whichever packet
  /// carries the matching cmdSet/cmdId, request or response.
  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.length >= 29;

  static CommonVersion? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return fromPayload(p.payload);
  }

  static String _dotted(Uint8List payload, int hi, int lo) {
    // Real getter formats high-to-low byte order: get(hi)..get(lo).
    final parts = [for (var i = hi; i >= lo; i--) payload[i]];
    return parts.map((b) => b.toString().padLeft(2, '0')).join('.');
  }

  static CommonVersion fromPayload(Uint8List payload) {
    final d = ByteData.sublistView(payload);
    final hwBytes = payload.sublist(1, 17);
    final nul = hwBytes.indexOf(0);
    final hw = String.fromCharCodes(nul >= 0 ? hwBytes.sublist(0, nul) : hwBytes);
    final info = d.getUint32(25, Endian.little);
    return CommonVersion(
      hardwareVersion: hw,
      firmwareVersion: _dotted(payload, 24, 21),
      loaderVersion: _dotted(payload, 20, 17),
      isProduction: (info >> 31) & 1 == 1,
      isSupportSafeUpgrade: (info >> 30) & 1 == 1,
    );
  }

  @override
  String toString() => 'Version(hw=$hardwareVersion fw=$firmwareVersion '
      'loader=$loaderVersion production=$isProduction safeUpgrade=$isSupportSafeUpgrade)';
}
