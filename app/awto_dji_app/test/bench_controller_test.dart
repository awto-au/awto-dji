import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:awto_dji_app/bench/aoat.dart';
import 'package:awto_dji_app/bench/bench_controller.dart';
import 'package:awto_dji_app/bench/bench_model.dart';
import 'package:flutter/services.dart';
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

  group('accessory generations', () {
    const aoaCh = MethodChannel('au.awto.dji/aoa');
    const benchCh = MethodChannel('au.awto.dji/bench');
    const evCh = EventChannel('au.awto.dji/aoa/bytes');
    final sinks = <MockStreamHandlerEventSink>[];
    final calls = <String>[];
    Completer<void>? connectGate;
    late BenchController c;
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

    setUp(() {
      sinks.clear();
      calls.clear();
      connectGate = null;
      messenger.setMockMethodCallHandler(benchCh, (call) async {
        if (call.method == 'usbInfo') return {'attached': true, 'permission': true};
        return null;
      });
      messenger.setMockMethodCallHandler(aoaCh, (call) async {
        calls.add(call.method);
        if (call.method == 'connect') {
          await connectGate?.future;
          return 7;
        }
        return null;
      });
      messenger.setMockStreamHandler(
        evCh,
        MockStreamHandler.inline(onListen: (args, sink) => sinks.add(sink)),
      );
      c = BenchController(tick: const Duration(milliseconds: 50), controlPort: null);
    });

    tearDown(() {
      c.dispose();
      messenger.setMockMethodCallHandler(aoaCh, null);
      messenger.setMockMethodCallHandler(benchCh, null);
      messenger.setMockStreamHandler(evCh, null);
    });

    // 20 ms steps, bound 3 s: mocks answer in ms; the longest wait is the 1 s retry backoff.
    Future<void> until(bool Function() ok, String what) async {
      for (var i = 0; i < 150 && !ok(); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(ok(), true, reason: what);
    }

    test('bytes_in counts per session and restarts on the next attach', () async {
      await c.start();
      await until(() => c.snapshot.port == PortState.connected, 'open');
      final g1 = c.accessoryGen;
      sinks.single.success(Uint8List.fromList([1, 2, 3, 4]));
      await until(() => c.bytesIn == 4, 'bytes counted');
      sinks.single.error(code: 'io', message: 'read failed EIO');
      await until(() => c.accessoryGen > g1 && c.snapshot.port == PortState.connected && sinks.length == 2, 'reopened');
      expect(c.bytesIn, 0);
      sinks.last.success(Uint8List.fromList([9, 9]));
      await until(() => c.bytesIn == 2, 'new session reads');
    });

    test('stream end during connect is not reported as an open accessory', () async {
      connectGate = Completer<void>();
      await c.start();
      await until(() => sinks.length == 1, 'listening');
      sinks.single.error(code: 'io', message: 'read failed EIO'); // old session dies while the native connect is pending
      await until(() => calls.contains('disconnect'), 'closed');
      connectGate!.complete();
      connectGate = null;
      await until(() => c.lines.any((l) => l.contains('closed during connect')), 'connect noticed the close');
      // the retry opens a fresh session that actually delivers bytes
      await until(() => c.snapshot.port == PortState.connected && sinks.length >= 2, 'retry opened');
      sinks.last.success(Uint8List.fromList([5, 6, 7]));
      await until(() => c.bytesIn == 3, 'retry session reads');
    });

    test('attach intent replaces an open session with a new generation', () async {
      await c.start();
      await until(() => c.snapshot.port == PortState.connected, 'open');
      final g = c.accessoryGen;
      c.handleIntent('android.hardware.usb.action.USB_ACCESSORY_ATTACHED', {});
      await until(() => sinks.length == 2 && c.accessoryGen > g && c.snapshot.port == PortState.connected, 'replaced');
      sinks.last.success(Uint8List.fromList([1, 2]));
      await until(() => c.bytesIn == 2, 'new session reads');
    });

    test('stale-generation error and end are ignored', () async {
      await c.start();
      await until(() => c.snapshot.port == PortState.connected, 'open');
      final g = c.accessoryGen;
      // an event handler of generation g-1 must not close generation g
      c.debugStaleEvent(g - 1);
      expect(c.accessoryGen, g);
      expect(c.snapshot.port, PortState.connected);
    });
  });

  group('control port', () {
    late BenchController c;
    late Socket sock;
    final lines = <Map<String, Object?>>[];

    Future<void> up() async {
      lines.clear();
      c = BenchController(tick: const Duration(milliseconds: 100), controlPort: 0);
      await c.start();
      expect(c.boundControlPort, isNotNull);
      sock = await Socket.connect('127.0.0.1', c.boundControlPort!, timeout: const Duration(seconds: 2));
      sock.cast<List<int>>().transform(utf8.decoder).transform(const LineSplitter()).listen(
        (l) => lines.add(jsonDecode(l) as Map<String, Object?>),
        onError: (Object _) {},
      );
    }

    // 20 ms steps, bound 3 s: loopback answers in ms.
    Future<Map<String, Object?>> reply(String cmd, Map<String, Object?> req) async {
      final n = lines.length;
      sock.write('${jsonEncode(req)}\n');
      for (var i = 0; i < 150; i++) {
        final m = lines.skip(n).where((l) => l['t'] == 'reply' && l['cmd'] == cmd).firstOrNull;
        if (m != null) return m;
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      throw TimeoutException('no reply to $cmd');
    }

    tearDown(() async {
      sock.destroy();
      c.dispose();
    });

    test('starts in no mode; ping, mode, get, reset, bad input', () async {
      await up();
      expect((await reply('get', {'cmd': 'get'}))['result'], containsPair('mode', 'passive'));
      sock.write('{"cmd":"ping","id":3}\n');
      for (var i = 0; i < 150 && !lines.any((l) => l['t'] == 'pong'); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(lines.any((l) => l['t'] == 'pong' && l['id'] == 3), true);

      final m = await reply('mode', {'cmd': 'mode', 'm': 'sink', 'test': 9, 'seed': 5});
      expect(m['ok'], true);
      expect(m['m'], 'sink');
      expect(m['switch_us'], isA<int>());
      final g = await reply('get', {'cmd': 'get'});
      expect((g['state'] as Map)['mode'], containsPair('m', 'sink'));

      c.ingest(buildFrame(64, pOnes, 5, 0, testId: 9));
      expect(((await reply('get', {'cmd': 'get'}))['result'] as Map)['frames'], 1);
      await reply('stats_reset', {'cmd': 'reset'});
      expect(((await reply('get', {'cmd': 'get'}))['result'] as Map)['frames'], 0);

      final bad = await reply('mode', {'cmd': 'mode', 'm': 'nope'});
      expect(bad['ok'], false);
      expect(bad['error'], contains('unknown mode'));
      sock.write('garbage\n');
      for (var i = 0; i < 150 && !lines.any((l) => l['cmd'] == '?'); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
      expect(lines.any((l) => l['cmd'] == '?' && l['ok'] == false), true);
    });

    test('mode switch broadcasts the previous verdict and keeps going', () async {
      await up();
      await reply('mode', {'cmd': 'mode', 'm': 'sink', 'test': 2});
      c.ingest(buildFrame(64, pOnes, 1, 0, testId: 2));
      await reply('mode', {'cmd': 'mode', 'm': 'echo'});
      expect(lines.any((l) => l['t'] == 'result' && l['mode'] == 'sink' && l['final'] == true), true);
      c.ingest(Uint8List.fromList([1, 2, 3]));
      expect(c.written.last, [1, 2, 3]);
    });
  });
}
