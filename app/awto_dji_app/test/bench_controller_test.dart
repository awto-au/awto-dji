import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:awto_dji_app/bench/aoat.dart';
import 'package:awto_dji_app/bench/bench_controller.dart';
import 'package:awto_dji_app/bench/bench_model.dart';
import 'package:flutter_test/flutter_test.dart';

/// Fake host: a loopback TCP server collecting app lines, able to send commands.
class FakeHost {
  late ServerSocket server;
  Socket? sock;
  final msgs = <AppMsg>[];
  final _conn = Completer<void>();

  Future<void> start() async {
    server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    server.listen((s) {
      sock = s;
      s.done.catchError((Object _) {});
      if (!_conn.isCompleted) _conn.complete();
      s.cast<List<int>>().transform(utf8.decoder).transform(const LineSplitter()).listen((l) {
        final m = AppMsg.decode(l);
        if (m != null) msgs.add(m);
      }, onError: (Object _) {});
    }, onError: (Object _) {});
  }

  Future<void> connected() => _conn.future.timeout(const Duration(seconds: 3));
  void cmd(HostCmd c) => sock!.write('${c.encode()}\n');

  /// Poll (in 20 ms steps, bound 3 s: loopback RTT is <1 ms) for a matching message.
  Future<T> next<T extends AppMsg>([bool Function(T)? where]) async {
    for (var i = 0; i < 150; i++) {
      final m = msgs.whereType<T>().where(where ?? (_) => true).firstOrNull;
      if (m != null) return m;
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    throw TimeoutException('no matching $T; got ${msgs.map((m) => m.runtimeType).toSet()}');
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('host link: hello, state, ping/pong, mode+sink result, send, intents', () async {
    final h = FakeHost();
    await h.start();
    final c = BenchController(tick: const Duration(milliseconds: 100));
    await c.start();
    c.handleIntent('au.awto.dji.action.BENCH', {'host': '127.0.0.1', 'port': '${h.server.port}'});
    await h.connected();

    expect((await h.next<HelloMsg>()).app, 'awto-dji-bench');
    expect((await h.next<StateMsg>()).snapshot.hostConnected, true);
    await h.next<LogMsg>((l) => l.msg.contains('host target'));

    h.cmd(const PingCmd(5));
    expect((await h.next<PongMsg>()).id, 5);

    // app-initiated ping gets an RTT once the host answers
    final ping = await h.next<AppPingMsg>();
    h.cmd(PongCmd(ping.id));
    final withRtt = await h.next<StateMsg>((s) => s.snapshot.hostRttMs != null);
    expect(withRtt.snapshot.hostRttMs, lessThan(1000));

    // sink mode: verify a good frame then a corrupt one, ask for the result
    h.cmd(const ModeCmd({'m': 'sink', 'test': 9}));
    await h.next<StateMsg>((s) => s.snapshot.mode == 'sink');
    c.ingest(buildFrame(128, pAddr, 3, 0, testId: 9));
    final bad = buildFrame(128, pAddr, 3, 1, testId: 9);
    bad[20 + 60] ^= 0x01;
    c.ingest(bad);
    h.cmd(const ResultCmd());
    final r = await h.next<ResultMsg>();
    expect(r.body['frames'], 2);
    expect(r.body['pass'], false);
    expect((r.body['first_mismatch'] as Map)['offset'], 60);
    final st = await h.next<StateMsg>((s) => s.snapshot.firstMismatchOffset == 60);
    expect(st.snapshot.testPass, false);

    // send writes raw bytes (no platform channel here: still recorded)
    h.cmd(const SendCmd([1, 2, 3]));
    for (var i = 0; i < 100 && c.written.isEmpty; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    expect(c.written.single, Uint8List.fromList([1, 2, 3]));

    // passive envelope path: rx messages carry channel/len/crc_ok
    h.cmd(const ModeCmd({'m': 'passive'}));
    for (var i = 0; i < 100 && c.engine.mode.name != 'passive'; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 20));
    }
    c.ingest(Uint8List.fromList([0x55, 0xcc, 0x4a, 0x57, 3, 0, 0, 0, 9, 8, 7]));
    final rx = await h.next<RxMsg>();
    expect((rx.ch, rx.len, rx.crcOk), (0x574a, 3, true));

    h.cmd(const StatsResetCmd());
    await h.next<StateMsg>((s) => s.snapshot.totalMsgs == 0 && s.snapshot.mode == 'passive');

    expect(c.lines.length, lessThanOrEqualTo(BenchController.logRing));
    c.dispose();
    await h.server.close();
  });

  test('client retries with backoff until the host appears', () async {
    final probe = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
    final port = probe.port;
    await probe.close(); // port now refuses connections
    final c = BenchController(tick: const Duration(milliseconds: 100));
    await c.start();
    c.handleIntent('au.awto.dji.action.CONNECT', {'host': '127.0.0.1', 'port': '$port'});
    await Future<void>.delayed(const Duration(milliseconds: 300));
    expect(c.snapshot.hostConnected, false);
    expect(c.lines.any((l) => l.contains('connect failed')), true);
    final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, port);
    final got = Completer<void>();
    server.listen((s) {
      s.listen((_) {}, onError: (Object _) {});
      if (!got.isCompleted) got.complete();
    });
    // first backoff is 1 s: bound 3 s = connect after 1 s + margin
    await got.future.timeout(const Duration(seconds: 3));
    c.dispose();
    await server.close();
  });
}
