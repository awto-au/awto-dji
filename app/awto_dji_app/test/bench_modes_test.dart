import 'dart:async';
import 'dart:typed_data';

import 'package:awto_dji_app/bench/aoat.dart';
import 'package:awto_dji_app/bench/bench_model.dart';
import 'package:awto_dji_app/bench/bench_modes.dart';
import 'package:flutter_test/flutter_test.dart';

({ModeEngine e, List<Uint8List> out, List<Map<String, Object?>> res}) make() {
  final out = <Uint8List>[];
  final res = <Map<String, Object?>>[];
  final sw = Stopwatch()..start();
  final e = ModeEngine(
    write: (d) async => out.add(d),
    onResult: res.add,
    nowMs: () => sw.elapsedMilliseconds,
  );
  return (e: e, out: out, res: res);
}

ModeCmd mode(Map<String, Object?> p) => ModeCmd(p);

void main() {
  test('echo returns every chunk, empty included', () {
    final t = make();
    t.e.setMode(mode({'m': 'echo'}));
    t.e.onChunk(Uint8List.fromList([1, 2, 3]));
    t.e.onChunk(Uint8List(0));
    expect(t.out.map((b) => b.length), [3, 0]);
    expect(t.e.result()['frames'], 2);
  });

  test('sink verifies and reports first mismatch offset', () {
    final t = make();
    t.e.setMode(mode({'m': 'sink', 'test': 4}));
    t.e.onChunk(buildFrame(200, pAddr, 1, 0, testId: 4));
    final bad = buildFrame(200, pCounter, 1, 1, testId: 4);
    bad[20 + 50] ^= 1;
    t.e.onChunk(bad);
    final r = t.e.result();
    expect(r['frames'], 2);
    expect(r['pass'], false);
    expect((r['first_mismatch'] as Map)['offset'], 50);
    expect(t.e.grid().firstOffset, 50);
    expect(t.e.grid().pass, false);
  });

  test('sink counts short transfers and ZLPs, expect auto-finishes', () {
    final t = make();
    t.e.setMode(mode({'m': 'sink', 'test': 1, 'expect': 2}));
    t.e.onChunk(Uint8List.fromList([1, 2, 3]));
    t.e.onChunk(Uint8List(0));
    t.e.onChunk(buildFrame(64, pZeros, 1, 0, testId: 1));
    expect(t.res, isEmpty);
    t.e.onChunk(buildFrame(64, pZeros, 1, 1, testId: 1));
    expect(t.res, hasLength(1));
    expect(t.res.single['short'], 1);
    expect(t.res.single['zlp'], 1);
    expect(t.res.single['pass'], true);
    expect(t.res.single['final'], true);
    expect(t.e.mode, BenchMode.passive);
  });

  test('sink spans chunk boundaries', () {
    final t = make();
    t.e.setMode(mode({'m': 'sink'}));
    final f = buildFrame(1000, pRandom, 9, 0);
    t.e.onChunk(f.sublist(0, 512));
    t.e.onChunk(f.sublist(512));
    expect(t.e.result()['pass'], true);
    expect(t.e.result()['frames'], 1);
  });

  test('source emits count frames the sink accepts, then a final result', () async {
    final t = make();
    t.e.setMode(mode({'m': 'source', 'test': 2, 'size': 100, 'count': 5, 'pattern': 'random', 'seed': 7}));
    await Future<void>.delayed(const Duration(milliseconds: 50));
    expect(t.out, hasLength(5));
    final c = AoatChecker(testId: 2);
    for (final f in t.out) {
      c.feed(f);
    }
    expect(c.report.frames, 5);
    expect(c.report.passed, true);
    expect(t.res.single['done'], true);
    expect(t.res.single['frames'], 5);
    expect(t.res.single['bytes'], 500);
  });

  test('source size 0 writes empty transfers; size 7 is headerless', () async {
    final t = make();
    t.e.setMode(mode({'m': 'source', 'size': 0, 'count': 2}));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(t.out.map((b) => b.length), [0, 0]);
    final u = make();
    u.e.setMode(mode({'m': 'source', 'size': 7, 'count': 1}));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(u.out.single.length, 7);
  });

  test('source stops at dur_ms', () async {
    final t = make();
    t.e.setMode(mode({'m': 'source', 'size': 64, 'rate': 100, 'dur_ms': 120}));
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(t.res, hasLength(1));
    expect(t.out.length, inInclusiveRange(8, 14));
  });

  test('source aborts after 3 consecutive write failures', () async {
    final res = <Map<String, Object?>>[];
    final sw = Stopwatch()..start();
    final e = ModeEngine(
      write: (_) async => throw StateError('pipe'),
      onResult: res.add,
      nowMs: () => sw.elapsedMilliseconds,
    );
    e.setMode(mode({'m': 'source', 'size': 64}));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(res.single['pass'], false);
    expect(res.single['write_errors'], 3);
  });

  test('mode switch emits the previous verdict and resets counters', () {
    final t = make();
    t.e.setMode(mode({'m': 'sink', 'test': 1}));
    t.e.onChunk(buildFrame(64, pOnes, 1, 0, testId: 1));
    t.e.setMode(mode({'m': 'echo'}));
    expect(t.res.single['mode'], 'sink');
    expect(t.e.result()['frames'], 0);
  });

  test('duml answer swaps addresses and keeps the sequence; bad CRC not answered', () async {
    final t = make();
    t.e.setMode(mode({'m': 'duml', 'act': 'answer'}));
    final req = dumlTestFrame(sender: 10, receiver: 2, cmdSet: 4, cmdId: 9, seq: 77);
    t.e.onDuml(req, true);
    t.e.onDuml(dumlTestFrame(badCrc: true), false);
    expect(t.out, hasLength(1));
    final env = t.out.single;
    expect(env.sublist(0, 2), [0x55, 0xcc]);
    final f = env.sublist(8);
    expect((f[4], f[5], f[6] | f[7] << 8, f[9], f[10]), (2, 10, 77, 4, 9));
    final r = t.e.result();
    expect((r['duml_ok'], r['duml_bad_crc'], r['answered']), (1, 1, 1));
  });

  test('duml emit uses the configured addresses and bad-CRC variant', () async {
    final t = make();
    t.e.setMode(mode({
      'm': 'duml', 'act': 'emit', 'count': 3, 'sender': 6, 'receiver': 4,
      'cmd_set': 4, 'cmd_id': 0x0a, 'bad': 'crc',
    }));
    await Future<void>.delayed(const Duration(milliseconds: 30));
    expect(t.out, hasLength(3));
    for (final env in t.out) {
      final f = env.sublist(8);
      expect((f[4], f[5], f[9], f[10]), (6, 4, 4, 0x0a));
    }
    expect(t.out[0].last, isNot(dumlTestFrame(sender: 6, receiver: 4, cmdSet: 4, cmdId: 0x0a, seq: 0).last));
    expect(t.res.single['pass'], true); // bad CRC was intended
  });

  test('unknown mode is ignored', () {
    final t = make();
    t.e.setMode(mode({'m': 'bogus'}));
    expect(t.e.mode, BenchMode.passive);
  });
}
