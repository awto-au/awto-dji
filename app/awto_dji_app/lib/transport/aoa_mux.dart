import 'dart:typed_data';

class AoaPacket {
  AoaPacket(this.channel, this.payload);
  final int channel;
  final Uint8List payload;

  Uint8List encode() {
    final header = ByteData(8)
      ..setUint16(0, 0xcc55, Endian.little)
      ..setUint16(2, channel, Endian.little)
      ..setUint32(4, payload.length, Endian.little);
    return Uint8List.fromList([...header.buffer.asUint8List(), ...payload]);
  }
}

/// AOA envelope facts corroborated by GO's UsbAccessoryService/usb.P3.b.
/// Headers and payloads may span any number of USB/TCP reads.
class AoaMux {
  static const command = 0x5749;
  static const cameraVideo = 0x574a;
  static const fpvVideo = 0x574b;
  static const unknown574c = 0x574c;
  static const unknown574d = 0x574d;
  final List<int> _buffer = [];
  final int maxPayload;
  void Function(AoaPacket packet)? onPacket;
  void Function(Uint8List bytes)? onDiscard;
  int discarded = 0;

  AoaMux({this.maxPayload = 1024 * 1024}) {
    if (maxPayload < 1) throw ArgumentError.value(maxPayload, 'maxPayload');
  }

  void reset() {
    _buffer.clear();
    discarded = 0;
  }

  void _discard(int start, int end) {
    if (end <= start) return;
    discarded += end - start;
    onDiscard?.call(Uint8List.fromList(_buffer.sublist(start, end)));
  }

  /// Flush an incomplete envelope at a USB connection boundary for diagnostics.
  void finish() {
    _discard(0, _buffer.length);
    _buffer.clear();
  }

  List<AoaPacket> add(Uint8List bytes) {
    _buffer.addAll(bytes);
    final result = <AoaPacket>[];
    var offset = 0;
    var discardStart = 0;
    while (offset < _buffer.length) {
      if (_buffer[offset] != 0x55) {
        offset++;
        continue;
      }
      if (_buffer.length - offset < 2) break;
      if (_buffer[offset + 1] != 0xcc) {
        offset++;
        continue;
      }
      if (_buffer.length - offset < 8) break;
      final channel = _buffer[offset + 2] | (_buffer[offset + 3] << 8);
      final length =
          _buffer[offset + 4] |
          (_buffer[offset + 5] << 8) |
          (_buffer[offset + 6] << 16) |
          (_buffer[offset + 7] << 24);
      if (channel < 0x5749 || channel > 0x574d || length > maxPayload) {
        offset++;
        continue;
      }
      final end = offset + 8 + length;
      if (end > _buffer.length) break;
      _discard(discardStart, offset);
      final packet = AoaPacket(
        channel,
        Uint8List.fromList(_buffer.sublist(offset + 8, end)),
      );
      result.add(packet);
      onPacket?.call(packet);
      offset = end;
      discardStart = end;
    }
    _discard(discardStart, offset);
    if (offset > 0) _buffer.removeRange(0, offset);
    return result;
  }
}
