import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:awto_dji_app/bench/aoat.dart';
import 'package:flutter_test/flutter_test.dart';

String hex(List<int> b) => b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();

void main() {
  test('byte-identical to the Python golden vectors', () {
    final f = File('../../scripts/re/aoat_vectors.json');
    final vecs = jsonDecode(f.readAsStringSync()) as List<dynamic>;
    expect(vecs, isNotEmpty);
    for (final v in vecs.cast<Map<String, dynamic>>()) {
      final got = buildFrame(v['total'] as int, v['pattern'] as int, v['seed'] as int,
          v['seq'] as int, testId: v['test'] as int);
      expect(hex(got), v['hex'], reason: 'pattern ${v['pattern']} total ${v['total']}');
    }
  });

  test('round trip all patterns and chunkings', () {
    final c = AoatChecker();
    final stream = BytesBuilder();
    for (var i = 0; i < 12; i++) {
      stream.add(buildFrame(30 + i * 17, i % 6, 5, i, testId: 2));
    }
    final b = stream.toBytes();
    for (var i = 0; i < b.length; i += 13) {
      c.feed(b.sublist(i, i + 13 > b.length ? b.length : i + 13));
    }
    expect(c.report.frames, 12);
    expect(c.report.passed, true);
  });

  test('address pattern localises a misplaced word', () {
    final f = buildFrame(24 + 64, pAddr, 55, 3);
    f.setRange(20 + 24, 20 + 28, f.sublist(20 + 8, 20 + 12));
    final c = AoatChecker()..feed(f);
    final mm = c.report.firstMismatch!;
    expect((mm.seq, mm.offset), (3, 24));
    expect(mm.hint, contains('carries address 8'));
    expect(c.report.crcBad, 1);
  });

  test('seq gap, dup, resync, zlp, min size', () {
    final c = AoatChecker();
    for (final s in [0, 1, 3, 3]) {
      c.feed(buildFrame(30, 0, 1, s));
    }
    expect((c.report.seqGaps, c.report.seqDups), (1, 1));
    c.feed(Uint8List(0));
    expect(c.report.zlp, 1);
    final d = AoatChecker()
      ..feed(buildFrame(60, 0, 1, 0))
      ..feed(Uint8List.fromList([0, 1, 2]))
      ..feed(buildFrame(60, 0, 1, 1));
    expect(d.report.frames, 2);
    expect(d.report.resyncBytes, greaterThan(0));
    expect(() => buildFrame(23, 0, 1, 0), throwsArgumentError);
  });

  test('duml generator addresses and CRC variants', () {
    final f = dumlTestFrame(sender: 6, receiver: 4, cmdSet: 4, cmdId: 0x0a, seq: 0x1234);
    expect((f[4], f[5], f[9], f[10], f[6] | f[7] << 8), (6, 4, 4, 0x0a, 0x1234));
    expect(dumlTestFrame(badCrc: true)[3], dumlTestFrame()[3]);
    expect(dumlTestFrame(badCrc: true).last, isNot(dumlTestFrame().last));
    expect(dumlTestFrame(badHdrCrc: true)[3], isNot(dumlTestFrame()[3]));
  });
}
