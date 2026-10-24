import 'dart:typed_data';

/// Phone -> PC v1 records: AWTO, version u8, kind u8, channel u16 LE,
/// payload length u32 LE, payload. PC -> phone remains a raw DUML stream.
class RelayRecord {
  static const envelope = 1;
  static const discarded = 2;

  static Uint8List encode(int kind, int channel, Uint8List payload) {
    final header = ByteData(12)
      ..setUint32(0, 0x4f545741, Endian.little)
      ..setUint8(4, 1)
      ..setUint8(5, kind)
      ..setUint16(6, channel, Endian.little)
      ..setUint32(8, payload.length, Endian.little);
    return Uint8List.fromList([...header.buffer.asUint8List(), ...payload]);
  }
}
