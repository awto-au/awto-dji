import 'dart:typed_data';

import 'package:awto_dji_app/transport/aoa_mux.dart';
import 'package:duml/duml.dart';
import 'package:flutter_test/flutter_test.dart';

Uint8List envelope(int channel, List<int> payload) {
  final header = ByteData(8)
    ..setUint16(0, 0xcc55, Endian.little)
    ..setUint16(2, channel, Endian.little)
    ..setUint32(4, payload.length, Endian.little);
  return Uint8List.fromList([...header.buffer.asUint8List(), ...payload]);
}

Uint8List dumlFrame({int sequence = 0x1234, List<int>? payload}) =>
    DumlPacket(
      senderType: 14,
      receiverType: 2,
      sequence: sequence,
      cmdSet: 9,
      cmdId: 0x16,
      payload: payload == null ? null : Uint8List.fromList(payload),
    ).encode();

void main() {
  test('all chunk sizes preserve headers and payload markers', () {
    final video = Uint8List.fromList([
      0, 0, 0, 1, 0x67, ...'abc'.codeUnits,
      ...envelope(AoaMux.command, 'fake nested packet'.codeUnits),
    ]);
    final wire = Uint8List.fromList([
      ...envelope(AoaMux.cameraVideo, video),
      ...envelope(AoaMux.command, 'commands'.codeUnits),
    ]);
    for (var size = 1; size <= wire.length; size++) {
      final mux = AoaMux();
      final packets = <AoaPacket>[];
      for (var offset = 0; offset < wire.length; offset += size) {
        final end = (offset + size > wire.length) ? wire.length : offset + size;
        packets.addAll(mux.add(Uint8List.sublistView(wire, offset, end)));
      }
      expect(packets.length, 2);
      expect(packets[0].channel, AoaMux.cameraVideo);
      expect(packets[0].payload, video);
      expect(packets[1].channel, AoaMux.command);
      expect(packets[1].payload, 'commands'.codeUnits);
      expect(mux.discarded, 0, reason: 'chunk size $size');
      mux.finish();
      expect(mux.discarded, 0, reason: 'chunk size $size');
    }
  });

  test('noise and oversized header resynchronize', () {
    // Regression: an earlier version of the bare-DUML fallback waited on the
    // declared length alone before checking anything else, so this oversized
    // (for maxPayload), otherwise-random envelope header stalled resync
    // instead of being rejected immediately - see aoa_mux.dart's
    // _bareDumlLength doc comment.
    final mux = AoaMux(maxPayload: 64);
    final bad = Uint8List.fromList([
      ...'noise'.codeUnits,
      0x55, 0xcc,
      ...(ByteData(6)..setUint16(0, AoaMux.cameraVideo, Endian.little)
            ..setUint32(2, 65, Endian.little))
          .buffer.asUint8List(),
    ]);
    final wire = Uint8List.fromList([...bad, ...envelope(AoaMux.cameraVideo, 'good'.codeUnits)]);
    final packets = mux.add(wire);
    expect(packets.length, 1);
    expect(packets[0].channel, AoaMux.cameraVideo);
    expect(packets[0].payload, 'good'.codeUnits);
    expect(mux.discarded, bad.length);
  });

  test('connection boundary discards partial frame', () {
    final mux = AoaMux();
    final full = envelope(AoaMux.command, 'hello'.codeUnits);
    final partial = Uint8List.sublistView(full, 0, full.length - 1);
    expect(mux.add(partial), isEmpty);
    mux.finish();
    expect(mux.discarded, partial.length);
    final packets = mux.add(envelope(AoaMux.cameraVideo, 'next'.codeUnits));
    expect(packets.length, 1);
    expect(packets[0].payload, 'next'.codeUnits);
  });

  test('noise buffer is bounded', () {
    final mux = AoaMux();
    final noise = Uint8List.fromList([...List.filled(100000, 0x78), 0x55]);
    mux.add(noise);
    expect(mux.discarded, 100000);
  });

  test('bare DUML frame with no envelope is recovered as a command packet', () {
    final mux = AoaMux();
    final frame = dumlFrame(payload: [1, 2, 3]);
    final packets = mux.add(frame);
    expect(packets.length, 1);
    expect(packets[0].channel, AoaMux.command);
    expect(packets[0].payload, frame);
    expect(mux.discarded, 0);
  });

  test('bare frames interleaved with enveloped frames are both recovered', () {
    final mux = AoaMux();
    final bare1 = dumlFrame(sequence: 1, payload: [1]);
    final bare2 = dumlFrame(sequence: 2, payload: [2]);
    final wire = Uint8List.fromList([
      ...bare1,
      ...envelope(AoaMux.command, dumlFrame(sequence: 3, payload: [3])),
      ...bare2,
    ]);
    final packets = mux.add(wire);
    expect(packets.length, 3);
    for (final p in packets) {
      expect(p.channel, AoaMux.command);
    }
    expect(mux.discarded, 0);
  });

  test('back-to-back correctly-declared envelopes never leak into each other',
      () {
    // awto-dji#(envelope leak investigation): proves AoaMux's own slicing
    // arithmetic is correct given an honest length field - two full command
    // envelopes, each with no gap, each payload must be exactly its own
    // DUML frame with no trailing bytes from the next envelope's header.
    final mux = AoaMux();
    final first = dumlFrame(sequence: 1, payload: [1, 2, 3]);
    final second = dumlFrame(sequence: 2, payload: [4, 5]);
    final wire = Uint8List.fromList([
      ...envelope(AoaMux.command, first),
      ...envelope(AoaMux.command, second),
    ]);
    final packets = mux.add(wire);
    expect(packets.length, 2);
    expect(packets[0].payload, first);
    expect(packets[1].payload, second);
    expect(mux.discarded, 0);
  });

  test(
      'command envelope with an overstated length is trimmed to the real '
      'DUML frame, recovering the leaked next envelope',
      () {
    // Reproduces the live symptom (docs/aoa-live-test-2026-10-26.md):
    // LinkSession saw literal `55 cc <channel>` envelope-header bytes inside
    // what should have been pure DUML payload. Here the first envelope's
    // declared length is 8 bytes too long - exactly the size of a second
    // envelope's header - so a naive full-length slice would swallow it.
    final mux = AoaMux();
    final realFrame = dumlFrame(sequence: 1, payload: [1, 2, 3]);
    final second = envelope(AoaMux.command, dumlFrame(sequence: 2, payload: [9]));
    final overstated = ByteData(8)
      ..setUint16(0, 0xcc55, Endian.little)
      ..setUint16(2, AoaMux.command, Endian.little)
      ..setUint32(4, realFrame.length + second.length, Endian.little);
    final wire = Uint8List.fromList([
      ...overstated.buffer.asUint8List(),
      ...realFrame,
      ...second,
    ]);
    final packets = mux.add(wire);
    expect(packets.length, 2, reason: 'the leaked envelope must be recovered as its own packet');
    expect(packets[0].payload, realFrame, reason: 'trimmed to the real frame, not the overstated length');
    expect(packets[1].channel, AoaMux.command);
    expect(mux.discarded, 0);
  });

  test('bare frame bytes failing CRC16 are rejected, not falsely emitted', () {
    final mux = AoaMux();
    final frame = dumlFrame(payload: [1, 2, 3]);
    // Corrupt a payload byte (not the first 4 header bytes) - still passes
    // the cheap header CRC8 gate, must fail the full packetCrc16 check.
    final corrupted = Uint8List.fromList(frame);
    corrupted[corrupted.length - 3] ^= 0xFF;
    final packets = mux.add(corrupted);
    expect(packets, isEmpty);
    mux.finish();
    expect(mux.discarded, corrupted.length);
  });
}
