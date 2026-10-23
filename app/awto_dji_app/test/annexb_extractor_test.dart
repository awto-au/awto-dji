import 'dart:typed_data';

import 'package:awto_dji_app/video/annexb_extractor.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List bytes(List<int> b) => Uint8List.fromList(b);

void main() {
  test('finds NAL units bounded by 3-byte start codes', () {
    final ex = AnnexBExtractor();
    // SOF(0x55)-ish DUML noise, then two NALs (type 1 slice, type 9 AUD), matching the shape
    // seen in docs/aoa-live-test-2026-10-23.md's real capture.
    final nals = ex.add(bytes([
      0x55, 0xaa, 0xbb, // unrelated DUML-ish bytes
      0x00, 0x00, 0x01, 0x61, 0xde, 0xad, // NAL type 1 (slice)
      0x00, 0x00, 0x01, 0x09, 0xf0, // NAL type 9 (AUD)
      0x00, 0x00, 0x01, // start of a third NAL, not yet complete
    ]));
    expect(nals.length, 2);
    expect(nals[0][0] & 0x1F, 1);
    expect(nals[0].sublist(1), [0xde, 0xad]);
    expect(nals[1][0] & 0x1F, 9);
  });

  test('handles a NAL split across two chunks', () {
    final ex = AnnexBExtractor();
    expect(ex.add(bytes([0x00, 0x00, 0x01, 0x61, 0xde])), isEmpty);
    final nals = ex.add(bytes([0xad, 0x00, 0x00, 0x01, 0x09]));
    expect(nals.length, 1);
    expect(nals[0], [0x61, 0xde, 0xad]);
  });

  test('tolerates the 4-byte start code form (00 00 00 01)', () {
    final ex = AnnexBExtractor();
    final nals = ex.add(bytes([
      0x00, 0x00, 0x00, 0x01, 0x67, 0x42, // NAL type 7 (SPS), 4-byte start code
      0x00, 0x00, 0x01, 0x68, 0xce, // NAL type 8 (PPS), 3-byte start code
      0x00, 0x00, 0x01,
    ]));
    expect(nals.length, 2);
    // The leading 00 from the 4-byte form is absorbed as "unrelated bytes" before the 3-byte
    // start code the scanner actually matches on - first NAL content starts at the real NAL
    // header byte (0x67), which is what matters for a decoder.
    expect(nals[0].first, 0x67);
    expect(nals[1].first, 0x68);
  });

  test('silent/empty input yields no NALs and does not crash', () {
    final ex = AnnexBExtractor();
    expect(ex.add(Uint8List(0)), isEmpty);
    expect(ex.add(bytes(List.filled(100, 0x55))), isEmpty);
  });
}
