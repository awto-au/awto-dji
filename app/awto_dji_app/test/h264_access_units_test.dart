import 'dart:typed_data';

import 'package:awto_dji_app/video/h264_access_units.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List nal(List<int> bytes) => Uint8List.fromList(bytes);
List<int> annex(List<List<int>> nals) => [
  for (final n in nals) ...[0, 0, 0, 1, ...n],
];

void main() {
  test(
    'one picture contains every slice and keeps SPS/PPS at stream start',
    () {
      final parser = H264AccessUnits();
      final picture = [
        [0x67, 1],
        [0x68, 2],
        [9, 0x10],
        [0x61, 0x80, 3],
        [0x61, 0x40, 4],
      ];
      for (final n in picture) {
        expect(parser.add(nal(n)), isEmpty);
      }
      expect(parser.add(nal([9, 0x10])), [annex(picture)]);
      expect(parser.add(nal([0x61, 0x80, 5])), isEmpty);
      expect(parser.add(nal([9, 0x10])), [
        annex([
          [9, 0x10],
          [0x61, 0x80, 5],
        ]),
      ]);
    },
  );

  test(
    'streams without AUD split on first slice; reconnect drops partial picture',
    () {
      final parser = H264AccessUnits();
      parser.add(nal([0x65, 0x80, 1]));
      parser.add(nal([0x65, 0x40, 2]));
      expect(parser.add(nal([0x61, 0x80, 3])), [
        annex([
          [0x65, 0x80, 1],
          [0x65, 0x40, 2],
        ]),
      ]);
      parser.reset();
      expect(parser.add(nal([0x65, 0x80, 4])), isEmpty);
      expect(parser.add(nal([9, 0x10])), [
        annex([
          [0x65, 0x80, 4],
        ]),
      ]);
    },
  );
}
