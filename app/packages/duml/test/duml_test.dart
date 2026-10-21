import 'dart:math' as math;
import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

void main() {
  group('CRC', () {
    // Verified against o-gs/dji-firmware-tools and a captured DJI RC packet.
    final pkt = Uint8List.fromList([
      0x55, 0x0d, 0x04, 0x33, 0x0a, 0x06, 0xeb, 0x34, 0x40, 0x06, 0x01, 0x74, 0x24
    ]);

    test('header CRC-8 matches captured packet', () {
      expect(headerCrc8(pkt), equals(0x33));
    });

    test('packet CRC-16 matches captured packet', () {
      final crc = packetCrc16(pkt, pkt.length);
      expect(crc & 0xFF, equals(0x74));
      expect((crc >> 8) & 0xFF, equals(0x24));
    });
  });

  group('packet build', () {
    test('reproduces the captured RC stick-request packet byte-for-byte', () {
      final p = DumlPacket(
        version: 1,
        senderType: DeviceType.pc, // 0x0a
        receiverType: DeviceType.remoteController, // 0x06
        sequence: 0x34eb,
        ackType: AckType.afterExec, // byte8 = 0x40 (2 << 5)
        cmdSet: CmdSet.remote, // 0x06
        cmdId: 0x01,
      );
      expect(
        p.encode(),
        equals([0x55, 0x0d, 0x04, 0x33, 0x0a, 0x06, 0xeb, 0x34, 0x40, 0x06, 0x01, 0x74, 0x24]),
      );
    });

    test('round-trips header fields and payload', () {
      final original = DumlPacket(
        senderType: DeviceType.app,
        receiverType: DeviceType.flightController,
        receiverIndex: 2,
        sequence: 12345,
        packetType: PacketType.response,
        ackType: AckType.afterExec,
        cmdSet: CmdSet.flightController,
        cmdId: 0x43,
        payload: Uint8List.fromList(List<int>.generate(20, (i) => i * 3 & 0xFF)),
      );
      final decoded = DumlPacket.decode(original.encode());
      expect(decoded.senderType, DeviceType.app);
      expect(decoded.receiverType, DeviceType.flightController);
      expect(decoded.receiverIndex, 2);
      expect(decoded.sequence, 12345);
      expect(decoded.packetType, PacketType.response);
      expect(decoded.ackType, AckType.afterExec);
      expect(decoded.cmdSet, CmdSet.flightController);
      expect(decoded.cmdId, 0x43);
      expect(decoded.payload, original.payload);
    });

    test('decode rejects a corrupted CRC', () {
      final bytes = DumlPacket(
        senderType: DeviceType.app,
        receiverType: DeviceType.flightController,
        sequence: 1,
        cmdSet: CmdSet.general,
        cmdId: 0x00,
      ).encode();
      bytes[bytes.length - 1] ^= 0xFF;
      expect(() => DumlPacket.decode(bytes), throwsFormatException);
    });
  });

  group('framer', () {
    DumlPacket sample(int seq) => DumlPacket(
          senderType: DeviceType.app,
          receiverType: DeviceType.flightController,
          sequence: seq,
          cmdSet: CmdSet.general,
          cmdId: 0x01,
          payload: Uint8List.fromList([seq & 0xFF]),
        );

    test('extracts packets split across chunks', () {
      final a = sample(1).encode();
      final b = sample(2).encode();
      final stream = Uint8List.fromList([...a, ...b]);
      final framer = DumlFramer();
      // Feed one byte at a time; packets must emerge whole and in order.
      final got = <DumlPacket>[];
      for (final byte in stream) {
        got.addAll(framer.add([byte]));
      }
      expect(got.map((p) => p.sequence), [1, 2]);
    });

    test('resynchronises after leading garbage', () {
      final good = sample(7).encode();
      final framer = DumlFramer();
      final got = framer.add([0x00, 0xFF, 0x12, ...good]);
      expect(got.length, 1);
      expect(got.first.sequence, 7);
    });
  });

  group('telemetry', () {
    test('decodes OSD General geometric fields at the right offsets', () {
      final payload = Uint8List(60);
      final d = ByteData.sublistView(payload);
      const radPerDeg = math.pi / 180.0;
      d.setFloat64(0, 151.2093 * radPerDeg, Endian.little); // longitude
      d.setFloat64(8, -33.8688 * radPerDeg, Endian.little); // latitude
      d.setInt16(16, 1234, Endian.little); // 123.4 m
      d.setInt16(18, 15, Endian.little); // vgx 1.5 m/s
      d.setInt16(20, -20, Endian.little); // vgy -2.0
      d.setInt16(22, 5, Endian.little); // vgz 0.5
      d.setInt16(24, 100, Endian.little); // pitch 10.0 deg
      d.setInt16(26, -45, Endian.little); // roll -4.5
      d.setInt16(28, 1800, Endian.little); // yaw 180.0

      final osd = OsdGeneral.fromPacket(DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        packetType: PacketType.response,
        sequence: 1,
        cmdSet: OsdGeneral.cmdSet,
        cmdId: OsdGeneral.cmdId,
        payload: payload,
      ))!;

      expect(osd.longitude, closeTo(151.2093, 1e-4));
      expect(osd.latitude, closeTo(-33.8688, 1e-4));
      expect(osd.relativeHeight, closeTo(123.4, 1e-6));
      expect(osd.vgx, closeTo(1.5, 1e-6));
      expect(osd.vgy, closeTo(-2.0, 1e-6));
      expect(osd.vgz, closeTo(0.5, 1e-6));
      expect(osd.pitch, closeTo(10.0, 1e-6));
      expect(osd.roll, closeTo(-4.5, 1e-6));
      expect(osd.yaw, closeTo(180.0, 1e-6));
    });

    test('non-OSD packet is not decoded as telemetry', () {
      final p = DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        sequence: 1,
        cmdSet: CmdSet.general,
        cmdId: 0x01,
      );
      expect(OsdGeneral.fromPacket(p), isNull);
    });
  });
}
