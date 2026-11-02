import 'dart:convert';

import 'package:awto_dji_app/bench/bench_model.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('RateWindow', () {
    test('1 s and 10 s windows', () {
      final w = RateWindow();
      for (var i = 0; i < 10; i++) {
        w.record((i + 1) * 100, 10); // 10 msgs in the first second
      }
      expect(w.msgsPerSec(1000, 1000), 10);
      expect(w.bytesPerSec(1000, 1000), 100);
      expect(w.msgsPerSec(1000, 10000), 1);
      // 1.5 s later nothing is in the 1 s window, all still in the 10 s one.
      expect(w.msgsPerSec(2500, 1000), 0);
      expect(w.msgsPerSec(2500, 10000), 1);
      expect(w.total, 10);
      expect(w.totalBytes, 100);
    });
    test('events older than the max window are dropped, totals kept', () {
      final w = RateWindow()..record(0, 5);
      expect(w.msgsPerSec(20000, 10000), 0);
      expect(w.total, 1);
    });
    test('secondsSinceLast', () {
      final w = RateWindow();
      expect(w.secondsSinceLast(100), isNull);
      w.record(1000, 1);
      expect(w.secondsSinceLast(3500), 2.5);
    });
    test('reset', () {
      final w = RateWindow()..record(0, 5);
      w.reset();
      expect(w.total, 0);
      expect(w.lastAtMs, isNull);
    });
  });

  group('inferSpeed', () {
    test('512 high, 64 full', () {
      expect(inferSpeed(512), contains('high-speed'));
      expect(inferSpeed(64), contains('full-speed'));
      expect(inferSpeed(512), contains('inferred'));
    });
    test('unknown', () {
      expect(inferSpeed(null), startsWith('unknown'));
      expect(inferSpeed(8), contains('8'));
    });
  });

  group('json', () {
    AppMsg rt(AppMsg m) => AppMsg.decode(m.encode())!;
    test('hello', () {
      final m = rt(const HelloMsg('awto-dji-bench', '1.0.0+1')) as HelloMsg;
      expect((m.app, m.build), ('awto-dji-bench', '1.0.0+1'));
    });
    test('log', () {
      final m = rt(const LogMsg('2026-11-02T10:00:00+11:00', 'W', 'x')) as LogMsg;
      expect((m.ts, m.lvl, m.msg), ('2026-11-02T10:00:00+11:00', 'W', 'x'));
    });
    test('rx', () {
      final m = rt(const RxMsg(0x5749, 21, false)) as RxMsg;
      expect((m.ch, m.len, m.crcOk), (0x5749, 21, false));
    });
    test('pong and app ping', () {
      expect((rt(const PongMsg(7)) as PongMsg).id, 7);
      expect((rt(const AppPingMsg(9)) as AppPingMsg).id, 9);
    });
    test('state round trip, every field', () {
      const s = BenchSnapshot(
        usbAttached: true,
        manufacturer: 'DJI',
        model: 'T600',
        description: 'DJI',
        version: 'v1.2.3.4',
        uri: 'www.dji.com',
        serial: '12345678',
        permission: true,
        maxPacket: 512,
        udcSpeed: 'high-speed',
        plugged: 'usb',
        charging: 'charging',
        voltageMv: 4200,
        currentUa: -350000,
        msgsPerSec1: 12.5,
        msgsPerSec10: 11,
        bytesPerSec1: 900,
        bytesPerSec10: 800.5,
        totalMsgs: 100,
        totalBytes: 5000,
        secSinceLast: 0.25,
        crcBad: 2,
        discardedBytes: 13,
        port: PortState.streaming,
        lastError: 'boom',
        hostConnected: true,
        hostRttMs: 14,
        echo: true,
      );
      final m = rt(StateMsg(s)) as StateMsg;
      expect(jsonEncode(m.snapshot.toJson()), jsonEncode(s.toJson()));
      expect(m.snapshot.port, PortState.streaming);
      expect(m.snapshot.speed, contains('high-speed'));
      expect(s.toJson()['t'], 'state');
    });
    test('state defaults when fields are missing', () {
      final m = AppMsg.decode('{"t":"state"}') as StateMsg;
      expect(m.snapshot.port, PortState.idle);
      expect(m.snapshot.usbAttached, false);
    });
    test('garbage decodes to null', () {
      expect(AppMsg.decode('not json'), isNull);
      expect(AppMsg.decode('[1]'), isNull);
      expect(AppMsg.decode('{"t":"zzz"}'), isNull);
      expect(HostCmd.decode('{"cmd":"zzz"}'), isNull);
      expect(HostCmd.decode('{"cmd":"send","hex":"abc"}'), isNull);
    });
  });

  group('host commands', () {
    HostCmd rt(HostCmd c) => HostCmd.decode(c.encode())!;
    test('ping/pong', () {
      expect((rt(const PingCmd(3)) as PingCmd).id, 3);
      expect((rt(const PongCmd(4)) as PongCmd).id, 4);
    });
    test('send hex', () {
      final c = HostCmd.decode('{"cmd":"send","hex":"55 cc 49 57"}') as SendCmd;
      expect(c.bytes, [0x55, 0xcc, 0x49, 0x57]);
      expect((rt(c) as SendCmd).bytes, c.bytes);
    });
    test('echo on/off', () {
      expect((rt(const EchoCmd(true)) as EchoCmd).on, true);
      expect((rt(const EchoCmd(false)) as EchoCmd).on, false);
    });
    test('stats_reset/disconnect/reconnect', () {
      expect(rt(const StatsResetCmd()), isA<StatsResetCmd>());
      expect(rt(const DisconnectCmd()), isA<DisconnectCmd>());
      expect(rt(const ReconnectCmd()), isA<ReconnectCmd>());
    });
  });

  test('sameDiscrete ignores rates but not port state', () {
    const a = BenchSnapshot();
    expect(a.sameDiscrete(const BenchSnapshot(msgsPerSec1: 5, totalMsgs: 3)), true);
    expect(a.sameDiscrete(const BenchSnapshot(port: PortState.connected)), false);
  });
}
