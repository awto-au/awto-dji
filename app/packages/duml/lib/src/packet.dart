/// DUML v1 packet build and parse (the DJI phone↔aircraft wire format).
///
/// Layout (little-endian), reconstructed from the o-gs/dji-firmware-tools reference:
/// ```
///  0     SOF = 0x55
///  1..2  ver_length_tag: bits 0-9 = whole length (incl. 2 CRC bytes), bits 10-15 = version
///  3     header CRC-8 (over bytes 0..2)
///  4     sender:   type bits 0-4, index bits 5-7
///  5     receiver: type bits 0-4, index bits 5-7
///  6..7  sequence number
///  8     cmd type: encrypt bits 0-2, ack bits 5-6, response bit 7
///  9     command set
///  10    command id
///  11..  payload
///  last2 CRC-16 (over bytes 0 .. len-3)
/// ```
library;

import 'dart:typed_data';

import 'crc.dart';
import 'simple.dart';

const int sof = 0x55;

/// Device type ids used in the sender/receiver bytes (`COMM_DEV_TYPE`).
class DeviceType {
  static const int any = 0;
  static const int camera = 1;
  static const int app = 2;
  static const int flightController = 3;
  static const int gimbal = 4;
  static const int centerBoard = 5;
  static const int remoteController = 6; // REMOTE_RADIO
  static const int pc = 10;
}

/// Command sets (`CMD_SET_TYPE`).
class CmdSet {
  static const int general = 0x00;
  static const int special = 0x01;
  static const int camera = 0x02;
  static const int flightController = 0x03;
  static const int gimbal = 0x04;
  static const int remote = 0x06;
  static const int hdLink =
      0x09; // "OSD" in the app's own naming; radio/FPGA/AD9363 link control
}

enum PacketType { request, response }

/// Whether/when the receiver must acknowledge (`ACK_TYPE`).
enum AckType { none, beforeExec, afterExec }

class DumlPacket {
  final int version;
  final int senderType;
  final int senderIndex;
  final int receiverType;
  final int receiverIndex;
  final int sequence;
  final PacketType packetType;
  final AckType ackType;

  /// On-wire protection mode. [cmdSet], [cmdId] and [payload] are always decoded
  /// values; encode reapplies SIMPLE when this is [EncryptType.simple].
  final int encryptType;
  final int cmdSet;
  final int cmdId;
  final Uint8List payload;

  DumlPacket({
    this.version = 1,
    required this.senderType,
    this.senderIndex = 0,
    required this.receiverType,
    this.receiverIndex = 0,
    required this.sequence,
    this.packetType = PacketType.request,
    this.ackType = AckType.none,
    this.encryptType = 0,
    required this.cmdSet,
    required this.cmdId,
    Uint8List? payload,
  }) : payload = payload ?? Uint8List(0);

  /// Total on-wire length: 11-byte header + payload + 2-byte CRC.
  int get wholeLength => 11 + payload.length + 2;

  DumlPacket withEncryptType(int value) => DumlPacket(
        version: version,
        senderType: senderType,
        senderIndex: senderIndex,
        receiverType: receiverType,
        receiverIndex: receiverIndex,
        sequence: sequence,
        packetType: packetType,
        ackType: ackType,
        encryptType: value,
        cmdSet: cmdSet,
        cmdId: cmdId,
        payload: Uint8List.fromList(payload),
      );

  /// Serialise to bytes, filling in both checksums.
  Uint8List encode() {
    final len = wholeLength;
    if (len > 1023) throw ArgumentError('DUML: packet exceeds 10-bit length');
    if (encryptType != EncryptType.none && encryptType != EncryptType.simple) {
      throw UnsupportedError('DUML: unsupported protection mode $encryptType');
    }
    final out = Uint8List(len);
    out[0] = sof;
    final tag = (len & 0x3FF) | ((version & 0x3F) << 10);
    out[1] = tag & 0xFF;
    out[2] = (tag >> 8) & 0xFF;
    out[3] = headerCrc8(out); // over bytes 0..2
    out[4] = (senderType & 0x1F) | ((senderIndex & 0x7) << 5);
    out[5] = (receiverType & 0x1F) | ((receiverIndex & 0x7) << 5);
    out[6] = sequence & 0xFF;
    out[7] = (sequence >> 8) & 0xFF;
    out[8] = (encryptType & 0x7) |
        ((ackType.index & 0x3) << 5) |
        ((packetType == PacketType.response ? 1 : 0) << 7);
    out[9] = cmdSet & 0xFF;
    out[10] = cmdId & 0xFF;
    out.setRange(11, 11 + payload.length, payload);
    if (encryptType == EncryptType.simple) {
      applySimple(out, sequence, start: 9, end: len - 2);
    }
    final crc = packetCrc16(out, len);
    out[len - 2] = crc & 0xFF;
    out[len - 1] = (crc >> 8) & 0xFF;
    return out;
  }

  /// Parse one packet starting at `offset`. Throws [FormatException] on a bad SOF,
  /// truncation, or a checksum mismatch.
  static DumlPacket decode(Uint8List data, [int offset = 0]) {
    if (offset < 0 || offset + 11 > data.length) {
      throw const FormatException('DUML: too short for header');
    }
    if (data[offset] != sof) {
      throw FormatException(
          'DUML: bad SOF 0x${data[offset].toRadixString(16)}');
    }
    final tag = data[offset + 1] | (data[offset + 2] << 8);
    final len = tag & 0x3FF;
    if (len < 13 || offset + len > data.length) {
      throw FormatException('DUML: bad length $len');
    }
    final frame = Uint8List.sublistView(data, offset, offset + len);
    if (frame[3] != headerCrc8(frame)) {
      throw const FormatException('DUML: header CRC mismatch');
    }
    final wantCrc = frame[len - 2] | (frame[len - 1] << 8);
    if (wantCrc != packetCrc16(frame, len)) {
      throw const FormatException('DUML: packet CRC mismatch');
    }
    final cmdType = frame[8];
    final encryptType = cmdType & 0x7;
    if (encryptType != EncryptType.none && encryptType != EncryptType.simple) {
      throw FormatException('DUML: unsupported protection mode $encryptType');
    }
    final ack = (cmdType >> 5) & 0x3;
    if (ack >= AckType.values.length) {
      throw FormatException('DUML: unsupported acknowledgement mode $ack');
    }
    final sequence = frame[6] | (frame[7] << 8);
    final body = Uint8List.fromList(frame.sublist(9, len - 2));
    if (encryptType == EncryptType.simple) applySimple(body, sequence);
    return DumlPacket(
      version: (tag >> 10) & 0x3F,
      senderType: frame[4] & 0x1F,
      senderIndex: (frame[4] >> 5) & 0x7,
      receiverType: frame[5] & 0x1F,
      receiverIndex: (frame[5] >> 5) & 0x7,
      sequence: sequence,
      packetType:
          (cmdType & 0x80) != 0 ? PacketType.response : PacketType.request,
      ackType: AckType.values[ack],
      encryptType: encryptType,
      cmdSet: body[0],
      cmdId: body[1],
      payload: Uint8List.fromList(body.sublist(2)),
    );
  }

  @override
  String toString() =>
      'DUML(set=0x${cmdSet.toRadixString(16)} id=0x${cmdId.toRadixString(16)} '
      '${senderType}->${receiverType} seq=$sequence ${packetType.name} '
      'payload=${payload.length}B)';
}

/// Incrementally extracts whole DUML frames from a byte stream (e.g. the AOA
/// accessory input). Feed it whatever arrives; it yields complete packets and keeps
/// any partial tail for next time, resynchronising on the SOF after corruption.
class DumlFramer {
  final List<int> _buf = [];

  /// Frames dropped for a CRC/format failure (approximate: a spurious SOF inside
  /// a corrupt frame can add extra counts).
  int badFrames = 0;

  /// Called with the rejected bytes and the reason, for packet logs.
  void Function(Uint8List frame, String reason)? onBadFrame;

  /// Called for a valid decoded packet with its original wire bytes, preserving
  /// reserved header bits when forwarding frames from a stream.
  void Function(Uint8List frame, DumlPacket packet)? onFrame;

  List<DumlPacket> add(List<int> chunk) {
    _buf.addAll(chunk);
    final out = <DumlPacket>[];
    while (true) {
      // Drop bytes until a SOF.
      final start = _buf.indexOf(sof);
      if (start < 0) {
        _buf.clear();
        break;
      }
      if (start > 0) _buf.removeRange(0, start);
      if (_buf.length < 4)
        break; // GO validates CRC8 before trusting the length
      final header = Uint8List.fromList(_buf.sublist(0, 4));
      if (header[3] != headerCrc8(header)) {
        badFrames++;
        onBadFrame?.call(header, 'DUML: header CRC mismatch');
        _buf.removeAt(0);
        continue;
      }
      final len = (_buf[1] | (_buf[2] << 8)) & 0x3FF;
      if (len < 13 || len > 1023) {
        _buf.removeAt(0); // bogus; skip this SOF and resync
        continue;
      }
      if (_buf.length < len) break; // wait for the rest
      final frame = Uint8List.fromList(_buf.sublist(0, len));
      DumlPacket packet;
      try {
        packet = DumlPacket.decode(frame);
      } on FormatException catch (e) {
        badFrames++;
        onBadFrame?.call(frame, e.message);
        // A CRC-valid frame with an unsupported mode is still a whole frame.
        // Do not reinterpret protected payload bytes as another header.
        final intact = frame[3] == headerCrc8(frame) &&
            packetCrc16(frame, len) == (frame[len - 2] | (frame[len - 1] << 8));
        if (intact) {
          _buf.removeRange(0, len);
        } else {
          _buf.removeAt(0); // bad CRC: skip and resync
        }
        continue;
      }
      out.add(packet);
      _buf.removeRange(0, len);
      onFrame?.call(frame, packet);
    }
    return out;
  }

  void reset() {
    _buf.clear();
    badFrames = 0;
  }
}
