import 'dart:io';
import 'dart:typed_data';

/// Wireshark-dissectable ground truth for the raw accessory byte stream: one UDP
/// datagram per chunk, verbatim, before AoaMux (or anything DUML-aware) touches it.
/// UDP preserves datagram boundaries exactly - no length-prefix parsing needed, unlike
/// the TCP debug relay - and seq/crc32 here are independent of any DUML self-described
/// length/CRC, since diagnosing whether DUML's own framing can be trusted is the point.
///
/// Wire format (8-byte header + payload): seq u32 LE, crc32 u32 LE (IEEE 802.3, over
/// payload only), payload. Decoded on the PC side by aoa_relay_server.py's UDP listener.
class UdpRawRelay {
  UdpRawRelay(this.host, this.port);
  final String host;
  final int port;
  RawDatagramSocket? _socket;
  int _seq = 0;

  Future<void> connect() async {
    try {
      _socket = await RawDatagramSocket.bind(InternetAddress.anyIPv4, 0);
    } on Object {
      _socket = null;
    }
  }

  void send(Uint8List payload) {
    final socket = _socket;
    if (socket == null) return;
    final header = ByteData(8)
      ..setUint32(0, _seq, Endian.little)
      ..setUint32(4, _crc32(payload), Endian.little);
    _seq = (_seq + 1) & 0xffffffff;
    try {
      socket.send(
        Uint8List.fromList([...header.buffer.asUint8List(), ...payload]),
        InternetAddress(host),
        port,
      );
    } on Object {
      // Best-effort, same policy as TcpRelay: a relay failure never affects
      // the real transport.
    }
  }

  void close() {
    _socket?.close();
    _socket = null;
  }
}

int _crc32(Uint8List data) {
  var crc = 0xFFFFFFFF;
  for (final byte in data) {
    crc ^= byte;
    for (var i = 0; i < 8; i++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
    }
  }
  return (~crc) & 0xFFFFFFFF;
}
