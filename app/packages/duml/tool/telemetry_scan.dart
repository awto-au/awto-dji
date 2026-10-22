/// Scan a DUML capture and print a telemetry inventory.
///
/// Usage:
///   dart run tool/telemetry_scan.dart <capture-file>
///   dart run tool/telemetry_scan.dart --hex <file-of-hex-bytes>
///
/// The capture is whatever bytes the DUML travels as off the wire: a `usbmon`
/// payload dump of the ground unit's USB, a tap on the MCU UART, etc. The scanner
/// resynchronises on the SOF and validates CRCs (via DumlFramer), so partial or
/// interleaved data is fine.
///
/// It prints: a table of every message type seen, static/repeated payloads (the
/// Master-ID / metadata candidates), and ASCII strings (serial / name hints), plus
/// decoded OSD General telemetry lines.
library;

import 'dart:io';
import 'dart:typed_data';

import 'package:duml/duml.dart';

void main(List<String> args) {
  final hex = args.contains('--hex');
  final files = args.where((a) => !a.startsWith('--')).toList();
  if (files.isEmpty) {
    stderr.writeln('usage: telemetry_scan [--hex] <capture-file>');
    exitCode = 2;
    return;
  }

  final raw = File(files.first).readAsBytesSync();
  final bytes = hex ? _decodeHex(String.fromCharCodes(raw)) : raw;

  final framer = DumlFramer();
  final packets = framer.add(bytes);

  final inv = StreamInventory.of(packets);
  stdout.write(inv.report());

  // Decoded telemetry (the geometric OSD fields we trust).
  final osd = packets
      .map(OsdGeneral.fromPacket)
      .where((o) => o != null)
      .cast<OsdGeneral>()
      .toList();
  if (osd.isNotEmpty) {
    stdout.writeln('\nDecoded OSD General (${osd.length}):');
    for (final o in osd.take(10)) {
      stdout.writeln('  $o');
    }
    if (osd.length > 10) stdout.writeln('  … ${osd.length - 10} more');
  }
}

Uint8List _decodeHex(String s) {
  final clean = s.replaceAll(RegExp(r'[^0-9a-fA-F]'), '');
  final out = Uint8List(clean.length ~/ 2);
  for (var i = 0; i < out.length; i++) {
    out[i] = int.parse(clean.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return out;
}
