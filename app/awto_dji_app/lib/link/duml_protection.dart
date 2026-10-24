import 'dart:typed_data';

import 'package:duml/duml.dart';

enum DumlProtectionMode { auto, none, simple }

/// App-side SIMPLE mode selection, separate from the packet transform itself.
/// Auto follows CRC-valid incoming packets and the APK's COMMON/camera exclusions.
class DumlProtection {
  DumlProtection({this.mode = DumlProtectionMode.auto});

  final DumlProtectionMode mode;
  final _received = DumlFramer();
  final _proxy = DumlFramer();
  bool _peerUsesSimple = false;

  void reset() {
    _peerUsesSimple = false;
    _received.reset();
    _proxy.reset();
  }

  static bool eligible(DumlPacket packet) =>
      packet.cmdSet != CmdSet.general &&
      !(packet.cmdSet == CmdSet.camera &&
          const [0x10, 0x11, 0x70, 0x71].contains(packet.cmdId));

  void observe(Uint8List bytes) {
    for (final packet in _received.add(bytes)) {
      if (packet.encryptType == EncryptType.simple) {
        _peerUsesSimple = true;
      } else if (eligible(packet)) {
        _peerUsesSimple = false;
      }
    }
  }

  /// The command proxy is TCP: a read may contain a partial frame or many frames.
  List<Uint8List> prepareProxyBytes(Uint8List bytes) {
    final result = <Uint8List>[];
    _proxy.onFrame = (wire, _) => result.add(prepare(wire));
    try {
      _proxy.add(bytes);
    } finally {
      _proxy.onFrame = null;
    }
    return result;
  }

  Uint8List prepare(Uint8List wire) {
    final useSimple =
        mode == DumlProtectionMode.simple ||
        (mode == DumlProtectionMode.auto && _peerUsesSimple);
    if (!useSimple) return wire;
    final packet = DumlPacket.decode(wire);
    if (packet.wholeLength != wire.length) {
      throw const FormatException('Expected one outgoing DUML packet');
    }
    // Preserve explicitly protected frames; never apply the XOR twice.
    if (packet.encryptType != EncryptType.none || !eligible(packet)) {
      return wire;
    }
    // GO modifies the body and mode in the existing wire buffer, then refreshes
    // CRC16. Preserve reserved flag bits and all other original header bytes.
    final protected = Uint8List.fromList(wire);
    applySimple(
      protected,
      packet.sequence,
      start: 9,
      end: protected.length - 2,
    );
    protected[8] |= EncryptType.simple;
    final crc = packetCrc16(protected, protected.length);
    protected[protected.length - 2] = crc & 0xff;
    protected[protected.length - 1] = crc >> 8;
    return protected;
  }
}
