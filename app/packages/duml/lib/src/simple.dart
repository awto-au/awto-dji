import 'dart:typed_data';

/// DUML protection field values supported by this codec.
class EncryptType {
  static const int none = 0;
  static const int simple = 3;
}

// Bundled protocol table, matched in GO 4 v4.3.64 libGroudStation.so and C1
// m1601. Independently implemented from disassembly; see docs/duml-protection.md.
// The native routine permits index 21, the string's terminating zero byte.
const _table = <int>[
  0x78,
  0x4f,
  0x24,
  0x33,
  0x28,
  0x2d,
  0x32,
  0x40,
  0x23,
  0x6c,
  0x64,
  0x2a,
  0x76,
  0x69,
  0x41,
  0x51,
  0x7e,
  0x69,
  0x78,
  0x46,
  0x45,
  0x00,
];

/// Transform one command-set/id/payload region in place. Applying twice restores
/// the original. The table recurrence restarts at the start of each packet body;
/// it must not restart at the payload or at USB/TCP chunk boundaries.
void applySimple(Uint8List bytes, int sequence, {int start = 0, int? end}) {
  final stop = end ?? bytes.length;
  RangeError.checkValidRange(start, stop, bytes.length);
  var index = 0;
  for (var position = 0; position < stop - start; position++) {
    index = (index + 1) ^ (position & 0x0f);
    if (index > 21) index = 0;
    final sequenceByte = (sequence >> (position.isEven ? 0 : 8)) & 0xff;
    bytes[start + position] ^= _table[index] ^ sequenceByte;
  }
}
