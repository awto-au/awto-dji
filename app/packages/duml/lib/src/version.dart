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
  /// 16 raw bytes at payload offset 2 - ASCII hardware-revision string, NUL-padded.
  /// Offset fixed awto-dji#32: the APK-derived `get(1, 16)` this was ported from is
  /// one byte early (missing a second leading "unknown" byte before hw_version) -
  /// confirmed against o-gs/dji-firmware-tools' independently-RE'd
  /// `general_version_inquiry_dissector` (dji-dumlv1-general.lua:120-160) and two
  /// real captured GetVersion replies (docs/identity-queries.md:18;
  /// captures/sessions/2026-10-24/duml_probe.log): the old offset decoded a real
  /// RC reply's hw field as garbled "\x10GL300C"; this offset gives clean "GL300C",
  /// and decodes a second real (unprogrammed) device's loader+firmware fields to
  /// "255.255.255.254" - byte-for-byte the same placeholder independently seen in
  /// the SD-card upgrade log's "[19 00]" lines (firmware-upgrade-log-review.md:62-64).
  final String hardwareVersion;

  /// `"%02d.%02d.%02d.%02d"` from payload bytes 25,24,23,22 (firmware).
  final String firmwareVersion;

  /// Same format from bytes 21,20,19,18 (bootloader).
  final String loaderVersion;

  /// Bit 31 of the little-endian int32 at offset 26 (`getInfo().isProduction`).
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

  /// Needs offsets 0..29 (the info int32 ends at 29), so 30 bytes minimum. Does not
  /// check [DumlPacket.packetType]: the real class reads this from whichever packet
  /// carries the matching cmdSet/cmdId, request or response.
  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.length >= 30;

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
    final hwBytes = payload.sublist(2, 18);
    final nul = hwBytes.indexOf(0);
    final hw =
        String.fromCharCodes(nul >= 0 ? hwBytes.sublist(0, nul) : hwBytes);
    final info = d.getUint32(26, Endian.little);
    return CommonVersion(
      hardwareVersion: hw,
      firmwareVersion: _dotted(payload, 25, 22),
      loaderVersion: _dotted(payload, 21, 18),
      isProduction: (info >> 31) & 1 == 1,
      isSupportSafeUpgrade: (info >> 30) & 1 == 1,
    );
  }

  @override
  String toString() => 'Version(hw=$hardwareVersion fw=$firmwareVersion '
      'loader=$loaderVersion production=$isProduction safeUpgrade=$isSupportSafeUpgrade)';
}
