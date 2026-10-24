/// Decoder for the Flight Controller "OSD General Data" push
/// (`cmd_set = 0x03`, `cmd_id = 0x43`, "GetPushCommon" per duml_catalog.py), the main
/// telemetry message.
///
/// Field offsets are taken from the public o-gs/dji-firmware-tools Wireshark
/// dissector. Only the leading, unambiguous geometric fields are decoded here; the
/// deeper bitfield block (flight-state flags, GPS count) varies by platform and must
/// be confirmed against a capture from your own aircraft before it is trusted.
///
/// U (unknown), not V: checked 2026-10-24 against the full session capture (~44MB,
/// ~2.5h) via the Python port of this decoder (scripts/re/duml_telemetry.py) - this
/// cmdset/cmdid never appears, not once. cmdset/cmdid matches our own APK-extracted
/// catalog name exactly, so it's not a wrong-id guess; not yet root-caused (no gating/
/// subscribe command found for it in the catalog). Treat matches() returning true as
/// untested until this is resolved - see awto-dji#16.
library;

import 'dart:math' as math;
import 'dart:typed_data';

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
  });

  static const int cmdSet = CmdSet.flightController;
  static const int cmdId = 0x43;

  /// True if `p` is an OSD General push this decoder understands.
  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.length >= 30;

  /// Decode from a packet, or return null if it is not an OSD General push.
  static OsdGeneral? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return fromPayload(p.payload);
  }

  static OsdGeneral fromPayload(Uint8List payload) {
    final d = ByteData.sublistView(payload);
    const degPerRad = 180.0 / math.pi;
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
    );
  }

  @override
  String toString() => 'OSD(lat=${latitude.toStringAsFixed(6)} '
      'lon=${longitude.toStringAsFixed(6)} h=${relativeHeight}m '
      'v=(${vgx},${vgy},${vgz}) att=(${roll},${pitch},${yaw}))';
}
