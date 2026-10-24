import 'dart:typed_data';

import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/transport/capture_loader.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:awto_dji_app/transport/replay_transport.dart';
import 'package:awto_dji_app/transport/simulated_transport.dart';
import 'package:duml/duml.dart';
import 'package:flutter_test/flutter_test.dart';

// Byte-exact RC packet captured from the real controller (duml tests).
final captured = Uint8List.fromList([
  0x55,
  0x0d,
  0x04,
  0x33,
  0x0a,
  0x06,
  0xeb,
  0x34,
  0x40,
  0x06,
  0x01,
  0x74,
  0x24,
]);

Future<void> settle() => Future<void>.delayed(Duration.zero);

void main() {
  group('LinkSession with simulated source', () {
    test('decodes OSD telemetry and counts packets', () async {
      final sim = SimulatedAircraftTransport(tickInterval: null);
      final s = LinkSession(sim);
      final osds = <OsdGeneral>[];
      s.telemetry.listen(osds.add);
      await s.start();
      expect(s.linkState, LinkState.connected);
      for (var i = 0; i < 5; i++) {
        sim.emitTick();
      }
      await settle();
      expect(osds.length, 5);
      expect(s.latestOsd!.latitude, closeTo(-33.8688, 0.01));
      expect(s.latestOsd!.relativeHeight, inInclusiveRange(29, 51));
      expect(s.packetCount, 6); // 5 OSD + 1 version reply on tick 0
      expect(s.crcErrorCount, 0);
      expect(s.messageCounts[0x0343], 5);
      expect(s.log.every((e) => e.crcOk), isTrue);
      await s.stop();
      s.dispose();
    });

    test('counts CRC errors and logs the bad frame', () async {
      final sim = SimulatedAircraftTransport(
        tickInterval: null,
        corruptEvery: 3,
      );
      final s = LinkSession(sim);
      await s.start();
      for (var i = 0; i < 6; i++) {
        sim.emitTick();
      }
      await settle();
      expect(s.crcErrorCount, greaterThanOrEqualTo(2));
      expect(s.log.where((e) => !e.crcOk), isNotEmpty);
      await s.stop();
      s.dispose();
    });

    test('health: noData -> ok -> stale with injected clock', () async {
      var now = DateTime(2026, 1, 1);
      final sim = SimulatedAircraftTransport(tickInterval: null);
      final s = LinkSession(sim, clock: () => now);
      await s.start();
      expect(s.health, LinkHealth.noData);
      sim.emitTick();
      await settle();
      expect(s.health, LinkHealth.ok);
      expect(s.lastTelemetryAt, now);
      now = now.add(const Duration(seconds: 2));
      expect(s.health, LinkHealth.stale);
      await s.stop();
      s.dispose();
    });
  });

  group('byte-exact captured packet', () {
    test(
      'SIMPLE replies expose decoded fields and retain protected wire logging',
      () async {
        final original = DumlPacket(
          senderType: DeviceType.gimbal,
          receiverType: DeviceType.app,
          sequence: 0x1234,
          packetType: PacketType.response,
          encryptType: EncryptType.simple,
          cmdSet: CmdSet.gimbal,
          cmdId: 0x0a,
          payload: Uint8List.fromList([0x55, 0xcc, 1, 2, 3]),
        );
        final wire = original.encode();
        final s = LinkSession(ReplayTransport(wire, speed: 0));
        await s.start();
        await settle();
        expect(s.packetCount, 1);
        expect(s.crcErrorCount, 0);
        expect(s.log.single.packet!.cmdSet, original.cmdSet);
        expect(s.log.single.packet!.cmdId, original.cmdId);
        expect(s.log.single.packet!.payload, original.payload);
        expect(s.log.single.raw, wire);
        await s.stop();
        s.dispose();
      },
    );

    test('framer path decodes it, split across chunks', () async {
      final t = ReplayTransport(captured, speed: 0);
      final s = LinkSession(t);
      await s.start();
      await settle();
      expect(s.packetCount, 1);
      final p = s.log.single.packet!;
      expect(p.cmdSet, CmdSet.remote);
      expect(p.cmdId, 0x01);
      expect(p.sequence, 0x34eb);
      expect(s.log.single.raw, captured);
      await s.stop();
      s.dispose();
    });
  });

  group('ReplayTransport', () {
    test('plays frames in order, junk preserved, then ends', () async {
      final data = Uint8List.fromList([0x00, 0xFF, ...captured, ...captured]);
      final t = ReplayTransport(data, speed: 0);
      final chunks = <Uint8List>[];
      t.bytes.listen(chunks.add);
      final states = <LinkState>[];
      t.state.listen(states.add);
      await t.connect();
      await Future<void>.delayed(const Duration(milliseconds: 10));
      expect(chunks.length, 3); // junk + 2 frames
      expect(chunks[1], captured);
      expect(states.last, LinkState.disconnected);
    });

    test('write is rejected on transports with no device', () {
      expect(
        ReplayTransport(captured).write(Uint8List(1)),
        throwsA(isA<UnsupportedError>()),
      );
      expect(
        SimulatedAircraftTransport().write(Uint8List(1)),
        throwsA(isA<UnsupportedError>()),
      );
    });

    test('rolling gap and byte-rate stats follow the injected clock', () async {
      var now = DateTime(2026, 1, 1);
      final sim = SimulatedAircraftTransport(tickInterval: null);
      final s = LinkSession(sim, clock: () => now);
      await s.start();
      for (var i = 0; i < 6; i++) {
        sim.emitTick();
        await settle();
        now = now.add(const Duration(milliseconds: 100));
      }
      final g = s.gapStats(const Duration(seconds: 1), now);
      // Tick 0 sends two chunks at the same instant (version reply + OSD): one 0 ms gap, then
      // five 100 ms gaps.
      expect(g.count, 6);
      expect(g.maxMs, closeTo(100, 1));
      expect(g.meanMs, closeTo(500 / 6, 0.5));
      expect(g.jitterMs, closeTo(37.3, 0.5));
      final r = s.byteRates(const Duration(seconds: 1), now);
      expect(r.duml, greaterThan(0));
      expect(r.video, 0);
      // Three seconds after the last packet the 1 s window has decayed to zero.
      final later = now.add(const Duration(seconds: 3));
      expect(s.byteRates(const Duration(seconds: 1), later).duml, 0);
      await s.stop();
      s.dispose();
    });

    test('hex text captures load like telemetry_scan --hex', () {
      const hex = '55 0d 04 33 0a 06 eb 34 40 06 01 74 24\n';
      expect(parseCapture(Uint8List.fromList(hex.codeUnits)), captured);
      expect(parseCapture(captured), captured);
    });
  });

  group('SimulatedAircraftTransport', () {
    test('frames are valid DUML OSD General with changing position', () async {
      final sim = SimulatedAircraftTransport(tickInterval: null);
      final got = <Uint8List>[];
      sim.bytes.listen(got.add);
      await sim.connect();
      sim.emitTick();
      sim.emitTick();
      await settle();
      final osd = DumlPacket.decode(got.first);
      expect(osd.cmdSet, 0x03);
      expect(osd.cmdId, 0x43);
      final a = OsdGeneral.fromPacket(osd)!;
      final b = OsdGeneral.fromPacket(DumlPacket.decode(got[2]))!;
      expect(a.latitude, isNot(b.latitude));
    });
  });
}
