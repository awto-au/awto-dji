import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

/// Build a packet with the given payload (encode() fills in CRCs).
Uint8List pkt(int set, int id, List<int> payload,
    {int sender = DeviceType.flightController, int receiver = DeviceType.app, int seq = 0}) {
  return DumlPacket(
    senderType: sender,
    receiverType: receiver,
    sequence: seq,
    cmdSet: set,
    cmdId: id,
    payload: Uint8List.fromList(payload),
  ).encode();
}

void main() {
  test('inventory counts message types and routes', () {
    final cap = <int>[];
    for (var i = 0; i < 5; i++) {
      cap.addAll(pkt(0x03, 0x43, List.filled(30, i), seq: i)); // OSD-ish, varying
    }
    cap.addAll(pkt(0x06, 0x20, [1, 2, 3, 4]));
    final inv = StreamInventory.of(DumlFramer().add(cap));
    expect(inv.total, 6);
    expect(inv.messages.length, 2);
    expect(inv.messages.first.cmdSet, 0x03); // most frequent first
    expect(inv.messages.first.count, 5);
  });

  test('static repeated payload is flagged as an identifier candidate', () {
    final cap = <int>[];
    final id = [0xde, 0xad, 0xbe, 0xef, 0x01, 0x02]; // constant "Master-ID"
    for (var i = 0; i < 4; i++) {
      cap.addAll(pkt(0x06, 0x30, id, seq: i));
    }
    final inv = StreamInventory.of(DumlFramer().add(cap));
    final m = inv.messages.firstWhere((m) => m.cmdSet == 0x06 && m.cmdId == 0x30);
    expect(m.looksLikeStaticId, isTrue);
    expect(m.samplePayload, equals(Uint8List.fromList(id)));
  });

  test('varying payload is NOT flagged as static', () {
    final cap = <int>[];
    for (var i = 0; i < 4; i++) {
      cap.addAll(pkt(0x03, 0x43, List.filled(30, i), seq: i));
    }
    final inv = StreamInventory.of(DumlFramer().add(cap));
    final m = inv.messages.firstWhere((m) => m.cmdSet == 0x03 && m.cmdId == 0x43);
    expect(m.looksLikeStaticId, isFalse);
  });

  test('ascii runs surface a serial-number string', () {
    final sn = 'P330ABCD1234567'.codeUnits;
    final payload = <int>[0x00, 0x01, ...sn, 0x00, 0xff];
    final runs = asciiRuns(Uint8List.fromList(payload));
    expect(runs, contains('P330ABCD1234567'));
  });

  test('report mentions static-id candidate and ascii hint', () {
    final cap = <int>[];
    final payload = <int>[...'SN123456'.codeUnits, 0, 0];
    for (var i = 0; i < 3; i++) {
      cap.addAll(pkt(0x00, 0x01, payload, seq: i));
    }
    final inv = StreamInventory.of(DumlFramer().add(cap));
    final r = inv.report();
    expect(r, contains('Get Version'));
    expect(r, contains('SN123456'));
    expect(r, contains('identifier'));
  });

  // Verified against DJI GO 4 v4.3.64's own CmdSet enum (docs/apk-analysis.md,
  // docs/data/apk-cmdset-devicetype.tsv) - guards against the names silently
  // drifting back to the pre-verification guesses (0x0b/0x0c/0x0d were wrong).
  test('cmdSetName matches the app-confirmed CmdSet values', () {
    expect(cmdSetName(0x00), 'general');
    expect(cmdSetName(0x03), 'flight-controller');
    expect(cmdSetName(0x06), 'remote-controller');
    expect(cmdSetName(0x09), 'osd');
    expect(cmdSetName(0x0a), 'eye');
    expect(cmdSetName(0x0b), 'simulator');
    expect(cmdSetName(0x0c), 'battery');
    expect(cmdSetName(0x0d), 'smart-battery');
    expect(cmdSetName(0x0f), 'rtk');
  });

  test('knownMessageName covers the doubly-confirmed RC/OSD commands', () {
    expect(knownMessageName(0x06, 0x0c), contains('Connected Master Id'));
    expect(knownMessageName(0x06, 0x0d), contains('Connected Master Id'));
    expect(knownMessageName(0x09, 0x12), isNotNull);
    expect(knownMessageName(0x09, 0x13), isNotNull);
  });
}
