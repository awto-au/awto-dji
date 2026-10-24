import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:duml/duml.dart';

Uint8List hex(String value) => Uint8List.fromList([
      for (var i = 0; i < value.length; i += 2)
        int.parse(value.substring(i, i + 2), radix: 16),
    ]);

void check(bool condition, String message) {
  if (!condition) throw StateError(message);
}

bool equal(List<int> a, List<int> b) =>
    a.length == b.length &&
    List.generate(a.length, (i) => a[i] == b[i]).every((v) => v);

void main(List<String> args) {
  if (args.length != 1) throw ArgumentError('Expected native vector JSON path');
  final vectors =
      jsonDecode(File(args.single).readAsStringSync())['vectors'] as List;
  var count = 0;
  for (final vector in vectors) {
    final plain = hex(vector['plain'] as String);
    final expected = hex(vector['protected'] as String);
    final sequence = vector['sequence'] as int;
    final transformed = Uint8List.fromList(plain);
    applySimple(transformed, sequence);
    check(equal(transformed, expected),
        'Native transform mismatch at case $count');
    applySimple(transformed, sequence);
    check(equal(transformed, plain), 'Inverse mismatch at case $count');
    if (plain.length >= 2) {
      final packet = DumlPacket(
        senderType: 2,
        receiverType: 4,
        sequence: sequence,
        encryptType: EncryptType.simple,
        cmdSet: plain[0],
        cmdId: plain[1],
        payload: Uint8List.sublistView(plain, 2),
      );
      final wire = packet.encode();
      check(equal(wire.sublist(9, wire.length - 2), expected),
          'Packet-body mismatch at case $count');
      final decoded = DumlPacket.decode(wire);
      check(decoded.cmdSet == plain[0] && decoded.cmdId == plain[1],
          'Header decode mismatch at case $count');
      check(equal(decoded.payload, plain.sublist(2)),
          'Payload decode mismatch at case $count');
    }
    count++;
  }
  print(
      'PASS: Dart transform and packet codec match both native routines for $count cases.');
}
