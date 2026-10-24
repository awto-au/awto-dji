import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

Uint8List hex(String value) => Uint8List.fromList([
      for (var i = 0; i < value.length; i += 2)
        int.parse(value.substring(i, i + 2), radix: 16),
    ]);

DumlPacket sample(
        {int protection = EncryptType.simple, int sequence = 0x1234}) =>
    DumlPacket(
      senderType: DeviceType.app,
      senderIndex: 2,
      receiverType: DeviceType.gimbal,
      receiverIndex: 3,
      sequence: sequence,
      packetType: PacketType.response,
      ackType: AckType.afterExec,
      encryptType: protection,
      cmdSet: CmdSet.gimbal,
      cmdId: 0x0a,
      payload: Uint8List.fromList(List.generate(128, (i) => i)),
    );

void main() {
  test('decodes a real protected AOA capture and preserves its wire bytes', () {
    final captured = jsonDecode(
      File('test/fixtures/captured_simple_frame.json').readAsStringSync(),
    );
    final wire = hex(captured['wire'] as String);
    final decoded = DumlPacket.decode(wire);
    expect(decoded.encryptType, EncryptType.simple);
    expect(decoded.sequence, captured['sequence']);
    expect(decoded.cmdSet, captured['cmd_set']);
    expect(decoded.cmdId, captured['cmd_id']);
    expect(decoded.payload, hex(captured['payload'] as String));
    expect(decoded.encode(), wire);
  });

  final fixture =
      jsonDecode(File('test/fixtures/simple_vectors.json').readAsStringSync());
  for (final vector in fixture['vectors'] as List) {
    test(
        'matches reference transform: seq=${vector['sequence']}, bytes=${(vector['plain'] as String).length ~/ 2}',
        () {
      final plain = hex(vector['plain'] as String);
      final data = Uint8List.fromList(plain);
      applySimple(data, vector['sequence'] as int);
      expect(data, hex(vector['protected'] as String));
      applySimple(data, vector['sequence'] as int);
      expect(data, plain);
    });
  }

  test('protects only command body and calculates CRC on wire bytes', () {
    final packet = sample();
    final wire = packet.encode();
    final clear = packet.withEncryptType(EncryptType.none).encode();
    expect(wire.sublist(0, 8), clear.sublist(0, 8));
    expect(wire[8], 0xc3);
    expect(wire.sublist(9, wire.length - 2),
        isNot(clear.sublist(9, clear.length - 2)));
    expect(
        packetCrc16(wire, wire.length), wire[wire.length - 2] | wire.last << 8);
    expect(packet.payload, List.generate(128, (i) => i));
  });

  test('decodes protected command IDs/payload without mutating input', () {
    final packet = sample();
    final wire = packet.encode();
    final before = Uint8List.fromList(wire);
    final decoded = DumlPacket.decode(Uint8List.fromList([0xff, ...wire]), 1);
    expect(decoded.cmdSet, packet.cmdSet);
    expect(decoded.cmdId, packet.cmdId);
    expect(decoded.payload, packet.payload);
    expect(decoded.senderIndex, 2);
    expect(decoded.receiverIndex, 3);
    expect(decoded.encryptType, EncryptType.simple);
    expect(decoded.encode(), before);
    expect(wire, before);
  });

  test('checks wire CRC before attempting deprotection', () {
    final wire = sample().encode();
    wire[11] ^= 1;
    expect(() => DumlPacket.decode(wire), throwsFormatException);
  });

  test('GO-style header validation does not wait on a corrupt long length', () {
    final badHeader = Uint8List.fromList([0x55, 0xff, 0x07, 0]);
    badHeader[3] = headerCrc8(badHeader) ^ 0xff;
    final good = sample().encode();
    final framer = DumlFramer();
    expect(framer.add([...badHeader, ...good]).single.encode(), good);
    expect(framer.badFrames, 1);
  });

  test('maximum SIMPLE body fits the 10-bit length without truncation', () {
    final packet = DumlPacket(
      senderType: 2,
      receiverType: 4,
      sequence: 0xffff,
      encryptType: EncryptType.simple,
      cmdSet: 4,
      cmdId: 10,
      payload: Uint8List(1010),
    );
    expect(packet.encode(), hasLength(1023));
    expect(DumlPacket.decode(packet.encode()).payload, packet.payload);
    expect(
      () => DumlPacket(
        senderType: 2,
        receiverType: 4,
        sequence: 1,
        cmdSet: 4,
        cmdId: 10,
        payload: Uint8List(1011),
      ).encode(),
      throwsArgumentError,
    );
  });

  test('fragmented mixed clear and SIMPLE frames decode in order', () {
    final a = sample(protection: EncryptType.none, sequence: 1);
    final b = sample(sequence: 2);
    final framer = DumlFramer();
    final packets = <DumlPacket>[];
    for (final byte in [...a.encode(), ...b.encode()]) {
      packets.addAll(framer.add([byte]));
    }
    expect(packets.map((p) => p.sequence), [1, 2]);
    expect(packets.map((p) => p.encryptType), [0, 3]);
    expect(packets.last.payload, b.payload);
  });

  test('rejects unsupported protection and acknowledgement values safely', () {
    expect(() => sample(protection: 1).encode(), throwsUnsupportedError);
    for (final flags in [0x41, 0x60]) {
      final wire = sample(protection: EncryptType.none).encode();
      wire[8] = flags;
      final crc = packetCrc16(wire, wire.length);
      wire[wire.length - 2] = crc & 0xff;
      wire[wire.length - 1] = crc >> 8;
      expect(() => DumlPacket.decode(wire), throwsFormatException);
      expect(DumlFramer().add([...wire, ...sample().encode()]), hasLength(1));
    }
  });
}
