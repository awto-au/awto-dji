import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:awto_dji_app/debug/relay_record.dart';
import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/transport/aoa_mux.dart';
import 'package:awto_dji_app/transport/aoa_transport.dart';
import 'package:awto_dji_app/video/annexb_extractor.dart';
import 'package:awto_dji_app/video/video_decoder.dart';
import 'package:duml/duml.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

class TestEvents extends EventChannel {
  const TestEvents(this.stream) : super('test/aoa/events');
  final Stream<Uint8List> stream;
  @override
  Stream<dynamic> receiveBroadcastStream([dynamic arguments]) => stream;
}

class TestDecoder extends VideoDecoder {
  final nals = <List<int>>[];
  @override
  Future<bool> start() async => true;
  @override
  void feedNal(Uint8List nal) => nals.add(nal.toList());
  @override
  Future<void> stop() async {}
}

Uint8List frame(int protection) => DumlPacket(
  senderType: 4,
  receiverType: 2,
  sequence: 0x1234,
  cmdSet: 4,
  cmdId: 10,
  encryptType: protection,
  payload: Uint8List.fromList([1, 2, 3]),
).encode();

List<(int, int, Uint8List)> records(Uint8List bytes) {
  final result = <(int, int, Uint8List)>[];
  var offset = 0;
  while (offset < bytes.length) {
    final header = ByteData.sublistView(bytes, offset, offset + 12);
    expect(header.getUint32(0, Endian.little), 0x4f545741);
    expect(header.getUint8(4), 1);
    final size = header.getUint32(8, Endian.little);
    result.add((
      header.getUint8(5),
      header.getUint16(6, Endian.little),
      Uint8List.sublistView(bytes, offset + 12, offset + 12 + size),
    ));
    offset += 12 + size;
  }
  return result;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const method = MethodChannel('test/aoa/method');
  final writes = <Uint8List>[];
  setUp(() {
    writes.clear();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(method, (call) async {
          if (call.method == 'write') writes.add(call.arguments as Uint8List);
          return null;
        });
  });
  tearDown(
    () => TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(method, null),
  );

  test('all split sizes preserve AOA spans and ordered discarded bytes', () {
    final original = Uint8List.fromList([
      9,
      0x55,
      2,
      ...AoaPacket(AoaMux.cameraVideo, frame(3)).encode(),
      7,
      ...AoaPacket(AoaMux.command, frame(0)).encode(),
      0x55,
    ]);
    for (var size = 1; size <= original.length; size++) {
      final rebuilt = BytesBuilder();
      final mux = AoaMux();
      mux.onPacket = (packet) => rebuilt.add(packet.encode());
      mux.onDiscard = rebuilt.add;
      for (var offset = 0; offset < original.length; offset += size) {
        mux.add(
          Uint8List.sublistView(
            original,
            offset,
            (offset + size).clamp(0, original.length),
          ),
        );
      }
      mux.finish();
      expect(rebuilt.takeBytes(), original, reason: 'chunk size $size');
      expect(mux.discarded, 5);
    }
  });

  test(
    'Annex-B boundaries exclude 3/4-byte prefixes and reset partial NALs',
    () {
      final wire = Uint8List.fromList([
        0,
        0,
        0,
        1,
        0x67,
        4,
        0,
        0,
        1,
        0x68,
        5,
        0,
        0,
        0,
        1,
        0x65,
        6,
      ]);
      for (var size = 1; size <= wire.length; size++) {
        final parser = AnnexBExtractor();
        final nals = <List<int>>[];
        for (var offset = 0; offset < wire.length; offset += size) {
          nals.addAll(
            parser.add(
              Uint8List.sublistView(
                wire,
                offset,
                (offset + size).clamp(0, wire.length),
              ),
            ),
          );
        }
        expect(nals, [
          [0x67, 4],
          [0x68, 5],
        ]);
        parser.reset();
        expect(parser.add(Uint8List.fromList([0, 0, 1, 0x61, 7, 0, 0, 1, 9])), [
          [0x61, 7],
        ]);
      }
    },
  );

  test(
    'reconnect clears partial envelopes, NALs and learned protection',
    () async {
      final events = StreamController<Uint8List>.broadcast();
      final decoder = TestDecoder();
      final transport = AoaTransport(
        method: method,
        events: TestEvents(events.stream),
        videoDecoder: decoder,
      );
      final chunks = <Uint8List>[];
      final sub = transport.bytes.listen(chunks.add);
      addTearDown(() async {
        await sub.cancel();
        await transport.disconnect();
        await events.close();
      });
      await transport.connect();
      events.add(AoaPacket(AoaMux.command, frame(3)).encode());
      events.add(
        AoaPacket(
          AoaMux.cameraVideo,
          Uint8List.fromList([0, 0, 1, 0x67, 8]),
        ).encode(),
      );
      final pending = AoaPacket(
        AoaMux.cameraVideo,
        Uint8List.fromList([0, 0, 1, 0x68, 9]),
      ).encode();
      events.add(Uint8List.sublistView(pending, 0, 7));
      await Future<void>.delayed(Duration.zero);
      await transport.write(frame(0));
      expect(writes.last[8] & 7, 3);
      await transport.disconnect();
      chunks.clear();
      await transport.connect();
      await transport.write(frame(0));
      expect(writes.last[8] & 7, 0);
      events.add(AoaPacket(AoaMux.command, frame(0)).encode());
      events.add(
        AoaPacket(
          AoaMux.cameraVideo,
          Uint8List.fromList([0, 0, 1, 0x65, 1, 0, 0, 1, 9]),
        ).encode(),
      );
      await Future<void>.delayed(Duration.zero);
      expect(chunks, [frame(0)]);
      expect(decoder.nals, [
        [0x65, 1],
      ]);
      expect(transport.videoBytes, 9);
    },
  );

  for (final forwardVideo in [true, false]) {
    test('phone routing + TCP records with relayVideo=$forwardVideo', () async {
      final server = await ServerSocket.bind(InternetAddress.loopbackIPv4, 0);
      final accepted = server.first;
      final events = StreamController<Uint8List>();
      final decoder = TestDecoder();
      final transport = AoaTransport(
        method: method,
        events: TestEvents(events.stream),
        relayHost: '127.0.0.1',
        relayPort: server.port,
        relayVideo: forwardVideo,
        videoDecoder: decoder,
      );
      final session = LinkSession(transport);
      await session.start();
      final peer = await accepted;
      final received = BytesBuilder();
      final peerDone = Completer<void>();
      peer.listen(received.add, onDone: peerDone.complete);
      addTearDown(() async {
        await events.close();
        session.dispose();
        peer.destroy();
        await server.close();
      });
      final protected = frame(3);
      // A complete DUML packet inside video must neither appear as telemetry
      // nor select SIMPLE. Start codes themselves span camera envelopes.
      events.add(AoaPacket(AoaMux.cameraVideo, protected).encode());
      await Future<void>.delayed(Duration.zero);
      await transport.write(frame(0));
      expect(writes.last[8] & 7, 0);
      final video = Uint8List.fromList([
        0,
        0,
        0,
        1,
        0x67,
        4,
        0,
        0,
        1,
        0x68,
        5,
        0,
        0,
        0,
        1,
        0x65,
        6,
      ]);
      final cameraA = AoaPacket(
        AoaMux.cameraVideo,
        Uint8List.sublistView(video, 0, 2),
      );
      final cameraB = AoaPacket(
        AoaMux.cameraVideo,
        Uint8List.sublistView(video, 2),
      );
      final packets = [
        cameraA,
        AoaPacket(AoaMux.command, Uint8List.sublistView(protected, 0, 5)),
        AoaPacket(AoaMux.fpvVideo, Uint8List.fromList([9, 8])),
        cameraB,
        AoaPacket(AoaMux.unknown574c, Uint8List.fromList([5, 6])),
        AoaPacket(AoaMux.unknown574d, Uint8List(0)),
        AoaPacket(AoaMux.command, Uint8List.sublistView(protected, 5)),
      ];
      final wire = Uint8List.fromList([
        8,
        7,
        ...packets.expand((p) => p.encode()),
        0x55,
      ]);
      final gotPacket = session.packets.first;
      for (final byte in wire) {
        events.add(Uint8List.fromList([byte]));
      }
      expect((await gotPacket.timeout(const Duration(seconds: 3))).cmdSet, 4);
      expect(session.packetCount, 1);
      expect(session.crcErrorCount, 0);
      expect(session.bytesReceived, protected.length);
      expect(decoder.nals, [
        [0x67, 4],
        [0x68, 5],
      ]);
      expect(transport.videoBytes, protected.length + video.length);
      await transport.write(frame(0));
      expect(writes.last[8] & 7, 3);
      await session.stop();
      await peerDone.future.timeout(const Duration(seconds: 3));
      final parsed = records(received.takeBytes());
      final envelopes = parsed
          .where((r) => r.$1 == RelayRecord.envelope)
          .toList();
      expect(
        envelopes.map((r) => r.$2),
        forwardVideo
            ? [AoaMux.cameraVideo, ...packets.map((p) => p.channel)]
            : [
                AoaMux.command,
                AoaMux.unknown574c,
                AoaMux.unknown574d,
                AoaMux.command,
              ],
      );
      for (final record in envelopes) {
        expect(AoaMux().add(record.$3).single.channel, record.$2);
      }
      final discarded = parsed
          .where((r) => r.$1 == RelayRecord.discarded)
          .expand((r) => r.$3)
          .toList();
      expect(discarded, [8, 7, 0x55]);
      // Disconnect resets learned protection mode.
      await transport.write(frame(0));
      expect(writes.last[8] & 7, 0);
    });
  }
}
