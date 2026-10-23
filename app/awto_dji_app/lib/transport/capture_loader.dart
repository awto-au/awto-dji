import 'dart:io';
import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Hex text ("55 0d 04 ...") -> bytes, as telemetry_scan.dart --hex accepts.
Uint8List decodeHexText(String s) {
  final clean = s.replaceAll(RegExp(r'[^0-9a-fA-F]'), '');
  final out = Uint8List(clean.length ~/ 2);
  for (var i = 0; i < out.length; i++) {
    out[i] = int.parse(clean.substring(i * 2, i * 2 + 2), radix: 16);
  }
  return out;
}

/// Raw capture bytes, or hex text if the whole file is hex digits/whitespace.
/// Raw DUML starts with 0x55 ('U'), which is not a hex digit.
Uint8List parseCapture(Uint8List raw) {
  final isHex = raw.isNotEmpty &&
      raw.every((b) =>
          (b >= 0x30 && b <= 0x39) ||
          (b >= 0x41 && b <= 0x46) ||
          (b >= 0x61 && b <= 0x66) ||
          b == 0x20 ||
          b == 0x0a ||
          b == 0x0d ||
          b == 0x09);
  return isHex ? decodeHexText(String.fromCharCodes(raw)) : raw;
}

Future<Uint8List> loadCaptureFile(String path) async =>
    parseCapture(await File(path).readAsBytes());

/// Splits a byte stream into whole-frame chunks (CRC not checked, so corrupt
/// frames survive for the packet log); non-frame bytes become junk chunks.
List<Uint8List> splitFrames(Uint8List d) {
  final out = <Uint8List>[];
  var junkStart = -1;
  void flushJunk(int end) {
    if (junkStart >= 0) out.add(Uint8List.sublistView(d, junkStart, end));
    junkStart = -1;
  }

  var i = 0;
  while (i < d.length) {
    var len = 0;
    if (d[i] == sof && i + 3 <= d.length) {
      len = (d[i + 1] | (d[i + 2] << 8)) & 0x3FF;
    }
    if (len >= 13 && i + len <= d.length) {
      flushJunk(i);
      out.add(Uint8List.sublistView(d, i, i + len));
      i += len;
    } else {
      if (junkStart < 0) junkStart = i;
      i++;
    }
  }
  flushJunk(d.length);
  return out;
}
