import 'dart:typed_data';

import 'package:duml/duml.dart';

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

/// Minimum DUML frame size (SOF+verlen+hdrcrc8+sender+receiver+seq+cmdtype+cmdset+cmdid+crc16).
const _minDumlFrame = 13;

/// AOA envelope facts corroborated by GO's UsbAccessoryService/usb.P3.b.
/// Headers and payloads may span any number of USB/TCP reads.
///
/// Real captures (awto-dji#64) show not every byte on the command channel is
/// `55 cc`-enveloped: DUML frames sometimes arrive bare, with no envelope wrapper at
/// all, interleaved with properly-enveloped ones from the same sender. Confirmed by two
/// independent checks on live data: CRC8+CRC16 together give ~1-in-16.7M odds of a
/// random byte run passing both (expected ~0 accidental matches over the discarded
/// bytes in that capture; got thousands), and DUML sequence numbers across bare and
/// enveloped frames from one sender are continuous (53% of consecutive transitions
/// exactly `prev+1`, far beyond chance). So when envelope-matching fails at the current
/// scan position, this also tries a bare DUML frame before falling back to a true discard.
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

  /// Length of a CRC-valid bare DUML frame starting at [offset], `null` if what's there
  /// doesn't validate, `0` if there just isn't enough buffered yet to tell either way
  /// (caller should wait for more data, not conclude it's not a frame).
  ///
  /// Checks the 8-bit header CRC - cheap, only needs 4 bytes - before ever waiting for
  /// the rest of a declared-length frame. Skipping that gate and waiting on the length
  /// field alone would stall resync on any coincidental `0x55` whose next two bytes
  /// happen to decode to a large length (e.g. the leftover bytes of a rejected,
  /// oversized-for-maxPayload envelope header) instead of falling through to it.
  int? _bareDumlLength(int offset) {
    if (_buffer.length - offset < 4) return 0;
    final length = (_buffer[offset + 1] | (_buffer[offset + 2] << 8)) & 0x3FF;
    if (length < _minDumlFrame) return null;
    if (headerCrc8(_buffer.sublist(offset, offset + 3)) != _buffer[offset + 3]) {
      return null;
    }
    if (_buffer.length - offset < length) return 0;
    final frame = _buffer.sublist(offset, offset + length);
    final storedCrc = frame[length - 2] | (frame[length - 1] << 8);
    if (packetCrc16(frame, length) != storedCrc) return null;
    return length;
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
      if (_buffer.length - offset >= 2 && _buffer[offset + 1] == 0xcc) {
        if (_buffer.length - offset < 8) break;
        final channel = _buffer[offset + 2] | (_buffer[offset + 3] << 8);
        final length =
            _buffer[offset + 4] |
            (_buffer[offset + 5] << 8) |
            (_buffer[offset + 6] << 16) |
            (_buffer[offset + 7] << 24);
        if (channel >= 0x5749 && channel <= 0x574d && length <= maxPayload) {
          final end = offset + 8 + length;
          if (end > _buffer.length) break;
          // On the command channel, the sender's declared envelope length
          // occasionally overstates the real DUML frame inside it, so the
          // naive full-length payload ends up swallowing the next envelope's
          // header (seen live as literal `55 cc <channel>` bytes inside what
          // should be pure DUML payload). Validate against the actual DUML
          // frame length (same CRC8+CRC16 check as the bare-frame path) and
          // trim to it, leaving the leaked tail in the buffer to be rescanned
          // as its own envelope/frame instead of silently appending it here.
          var payloadEnd = end;
          if (channel == command) {
            final realLength = _bareDumlLength(offset + 8);
            if (realLength != null &&
                realLength > 0 &&
                realLength < length) {
              payloadEnd = offset + 8 + realLength;
            }
          }
          _discard(discardStart, offset);
          final packet = AoaPacket(
            channel,
            Uint8List.fromList(_buffer.sublist(offset + 8, payloadEnd)),
          );
          result.add(packet);
          onPacket?.call(packet);
          offset = payloadEnd;
          discardStart = payloadEnd;
          continue;
        }
      }
      final bareLength = _bareDumlLength(offset);
      if (bareLength == 0) break; // not enough data yet to tell - wait
      if (bareLength != null) {
        _discard(discardStart, offset);
        final packet = AoaPacket(
          command,
          Uint8List.fromList(_buffer.sublist(offset, offset + bareLength)),
        );
        result.add(packet);
        onPacket?.call(packet);
        offset += bareLength;
        discardStart = offset;
        continue;
      }
      offset++;
    }
    _discard(discardStart, offset);
    if (offset > 0) _buffer.removeRange(0, offset);
    return result;
  }
}
