import 'dart:typed_data' show Endian;

import 'package:awto_dji_app/link/duml_protection.dart';
import 'package:awto_dji_app/transport/aoa_transport.dart';
import 'package:awto_dji_app/transport/aoa_mux.dart';
import 'package:duml/duml.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

DumlPacket sample({int set = 4, int id = 10, int protection = 0}) => DumlPacket(
  senderType: DeviceType.app,
  receiverType: DeviceType.gimbal,
  sequence: 0x1234,
  ackType: AckType.afterExec,
  encryptType: protection,
  cmdSet: set,
  cmdId: id,
  payload: Uint8List.fromList([1, 2, 3]),
);

Uint8List envelope(int channel, Uint8List payload) {
  final bytes = ByteData(8)
    ..setUint16(0, 0xcc55, Endian.little)
    ..setUint16(2, channel, Endian.little)
    ..setUint32(4, payload.length, Endian.little);
  return Uint8List.fromList([...bytes.buffer.asUint8List(), ...payload]);
}

void refreshCrc(Uint8List wire) {
  final crc = packetCrc16(wire, wire.length);
  wire[wire.length - 2] = crc & 255;
  wire[wire.length - 1] = crc >> 8;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('GO eligibility covers every command-set/id combination', () {
    for (var set = 0; set <= 255; set++) {
      for (var id = 0; id <= 255; id++) {
        final expected =
            set != 0 &&
            (set != 2 || (id != 16 && id != 17 && id != 112 && id != 113));
        expect(DumlProtection.eligible(sample(set: set, id: id)), expected);
      }
    }
  });

  test('GO mode transitions ignore excluded camera packets', () {
    final policy = DumlProtection();
    final wire = sample().encode();
    policy.observe(sample(protection: 3).encode());
    for (final id in [16, 17, 112, 113]) {
      policy.observe(sample(set: 2, id: id).encode());
      expect(policy.prepare(wire)[8] & 7, 3);
    }
    policy.observe(sample(set: 2, id: 18).encode());
    expect(policy.prepare(wire), wire);
  });

  test('AOA mode detection ignores even valid DUML hidden in video', () {
    final protected = sample(protection: 3).encode();
    final clear = sample().encode();
    for (var chunkSize = 1; chunkSize < 24; chunkSize++) {
      final policy = DumlProtection();
      final parser = AoaMux();
      void receive(Uint8List bytes) {
        for (final packet in parser.add(bytes)) {
          if (packet.channel == AoaMux.command) policy.observe(packet.payload);
        }
      }

      receive(envelope(0x574a, protected));
      expect(policy.prepare(clear), clear);
      final mux = envelope(AoaMux.command, protected);
      for (var offset = 0; offset < mux.length; offset += chunkSize) {
        final end = (offset + chunkSize).clamp(0, mux.length);
        receive(Uint8List.sublistView(mux, offset, end));
      }
      expect(policy.prepare(clear)[8] & 7, 3);
      receive(envelope(0x574a, clear));
      expect(policy.prepare(clear)[8] & 7, 3);
      receive(envelope(AoaMux.command, clear));
      expect(policy.prepare(clear), clear);
    }
  });

  test('GO-style outgoing mutation preserves every original header bit', () {
    final policy = DumlProtection(mode: DumlProtectionMode.simple);
    final wire = sample().encode();
    wire[8] |= 0x18;
    refreshCrc(wire);
    final before = Uint8List.fromList(wire);
    final protected = policy.prepare(wire);
    expect(protected.sublist(0, 8), wire.sublist(0, 8));
    expect(protected[8], wire[8] | 3);
    expect(DumlPacket.decode(protected).payload, sample().payload);
    expect(wire, before);
    expect(policy.prepare(protected), protected);
  });

  test(
    'TCP proxy handles fragmented/coalesced frames without altering headers',
    () {
      final policy = DumlProtection(mode: DumlProtectionMode.simple);
      final a = sample().encode();
      a[8] |= 0x18;
      refreshCrc(a);
      final b = sample(set: 0).encode();
      expect(policy.prepareProxyBytes(Uint8List.sublistView(a, 0, 5)), isEmpty);
      final frames = policy.prepareProxyBytes(
        Uint8List.fromList([...a.sublist(5), ...b]),
      );
      expect(frames, hasLength(2));
      expect(frames[0][8], a[8] | 3);
      expect(frames[1], b);
      final c = sample().encode();
      policy.prepareProxyBytes(Uint8List.sublistView(c, 0, 6));
      policy.reset();
      expect(policy.prepareProxyBytes(c), hasLength(1));
    },
  );

  test(
    'AOA parser recovers from noise, invalid sizes and stale connections',
    () {
      final mux = AoaMux(maxPayload: 64);
      final tooLarge = envelope(AoaMux.command, Uint8List(65));
      final good = envelope(AoaMux.command, Uint8List.fromList([1, 2]));
      final packets = mux.add(
        Uint8List.fromList([1, 0x55, 0, ...tooLarge, ...good]),
      );
      expect(packets, hasLength(1));
      expect(packets.single.payload, [1, 2]);
      mux.add(Uint8List.sublistView(good, 0, 7));
      mux.reset();
      expect(mux.add(good).single.payload, [1, 2]);
    },
  );

  test('auto learns only valid packets and resets between connections', () {
    final policy = DumlProtection();
    final wire = sample().encode();
    expect(policy.prepare(wire), wire);
    final corrupt = sample(protection: 3).encode()..[11] ^= 1;
    policy.observe(corrupt);
    expect(policy.prepare(wire), wire);
    for (final byte in sample(protection: 3).encode()) {
      policy.observe(Uint8List.fromList([byte]));
    }
    expect(DumlPacket.decode(policy.prepare(wire)).encryptType, 3);
    policy.observe(sample(set: 0).encode());
    expect(DumlPacket.decode(policy.prepare(wire)).encryptType, 3);
    policy.observe(sample().encode());
    expect(policy.prepare(wire), wire);
    policy.observe(sample(protection: 3).encode());
    policy.reset();
    expect(policy.prepare(wire), wire);
  });

  test(
    'SIMPLE follows APK exclusions and preserves explicit protected packets',
    () {
      final policy = DumlProtection(mode: DumlProtectionMode.simple);
      final wire = sample().encode();
      final protected = policy.prepare(wire);
      expect(DumlPacket.decode(protected).payload, sample().payload);
      expect(policy.prepare(protected), protected);
      for (final packet in [
        sample(set: 0),
        for (final id in [0x10, 0x11, 0x70, 0x71]) sample(set: 2, id: id),
      ]) {
        expect(policy.prepare(packet.encode()), packet.encode());
      }
      expect(
        DumlPacket.decode(policy.prepare(sample(set: 2, id: 0xb3).encode()))
            .encryptType,
        3,
      );
    },
  );

  test('none mode never automatically transforms commands', () {
    final policy = DumlProtection(mode: DumlProtectionMode.none);
    policy.observe(sample(protection: 3).encode());
    final wire = sample().encode();
    expect(policy.prepare(wire), wire);
  });

  test('AOA writes apply the selected mode on the platform channel', () async {
    final sent = <Uint8List>[];
    const method = MethodChannel('test/simple-aoa');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(method, (call) async {
          if (call.method == 'write') sent.add(call.arguments as Uint8List);
          return null;
        });
    addTearDown(
      () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
          .setMockMethodCallHandler(method, null),
    );
    final transport = AoaTransport(
      method: method,
      protectionMode: DumlProtectionMode.simple,
    );
    await transport.write(sample().encode());
    expect(sent.single[8] & 7, 3);
    expect(DumlPacket.decode(sent.single).payload, sample().payload);
    await transport.requestIFrame();
    final keyframe = DumlPacket.decode(sent.last);
    expect(keyframe.senderType, DeviceType.app);
    expect(keyframe.receiverType, DeviceType.camera);
    expect(keyframe.cmdSet, CmdSet.camera);
    expect(keyframe.cmdId, 0xb3);
  });
}
