/// Telemetry inventory: turn a DUML capture into a readable picture of what is in
/// it, and surface the metadata/identifier fields empirically — without hard-coding
/// field offsets for messages whose layout we have not confirmed against a capture.
///
/// The idea (see docs/link-security.md): the Master-ID / serial number ride the
/// cleartext DUML/telemetry stream as metadata. Rather than guess which cmd_id
/// carries them, let the data show it — a static identifier is a payload that is
/// *constant* across many packets of the same (cmd_set, cmd_id); a serial/name is a
/// run of printable ASCII. Both fall straight out of a capture.
library;

import 'dart:typed_data';

import 'packet.dart';

/// Human name for a command set, for readable reports.
///
/// Verified against DJI GO 4 v4.3.64's own `dji.midware.data.config.P3.CmdSet` enum
/// (docs/apk-analysis.md "Runtime unpacking", docs/data/apk-cmdset-devicetype.tsv) —
/// not a guess. Earlier names here for 0x09-0x0e were wrong (e.g. 0x0b was labelled
/// "battery" but is SIMULATOR; real BATTERY is 0x0c); corrected from the app's own
/// enum, which also cross-confirmed our independent m0900/m1400 firmware RE
/// (DeviceType.OFDM=9, FPGA=0x13, FPGA_G=0x14 match exactly).
String cmdSetName(int set) {
  switch (set) {
    case 0x00:
      return 'general'; // COMMON
    case 0x01:
      return 'special'; // SPECIAL
    case 0x02:
      return 'camera'; // CAMERA
    case 0x03:
      return 'flight-controller'; // FLYC
    case 0x04:
      return 'gimbal'; // GIMBAL
    case 0x05:
      return 'center-board'; // CENTER
    case 0x06:
      return 'remote-controller'; // RC
    case 0x07:
      return 'wifi'; // WIFI
    case 0x08:
      return 'dm36x'; // DM368
    case 0x09:
      return 'osd'; // OSD - Lightbridge/radio-link config+telemetry (m0900 set 0x09)
    case 0x0a:
      return 'eye'; // EYE - vision/obstacle-avoidance module
    case 0x0b:
      return 'simulator'; // SIMULATOR
    case 0x0c:
      return 'battery'; // BATTERY
    case 0x0d:
      return 'smart-battery'; // SMARTBATTERY
    case 0x0f:
      return 'rtk'; // RTK
    case 0x11:
      return 'ads-b'; // ADS_B
    case 0xee:
      return 'recognize'; // RECOGNIZE (238)
    case 0x64:
      return 'other'; // OTHER (100) - app's own catch-all value
    default:
      return 'set-0x${set.toRadixString(16).padLeft(2, '0')}';
  }
}

/// Names for the few (cmd_set, cmd_id) pairs we are confident about. Everything
/// else is reported generically; extend this only when a capture confirms it.
///
/// Set 0x06 (RC) ids 12/13 and set 0x09 (OSD) ids 5/6/7/12/13 are doubly confirmed:
/// independently by m1400/m0900 firmware disassembly (docs/id-entry-point.md,
/// docs/symbols/m0900_V01.11.0020.tsv) AND by DJI GO 4's own CmdSet.RC/OSD enums
/// (docs/apk-analysis.md). Everything else here is still the app-codec's own guess.
String? knownMessageName(int set, int id) {
  if (set == 0x00 && id == 0x01) return 'Get Version / device info';
  if (set == 0x03 && id == 0x43) return 'OSD General (telemetry push)';
  if (set == 0x03 && id == 0x44) return 'OSD Home Point';
  if (set == 0x06 && id == 0x0c) return 'RC Set Connected Master Id';
  if (set == 0x06 && id == 0x0d) return 'RC Get Connected Master Id';
  if (set == 0x09 && id == 0x05) return 'OSD FPGA register read';
  if (set == 0x09 && id == 0x06) return 'OSD FPGA/AD9363 register write';
  if (set == 0x09 && id == 0x07) return 'OSD FPGA/AD9363 register read';
  if (set == 0x09 && id == 0x12) return 'OSD Set radio/channel params';
  if (set == 0x09 && id == 0x13) return 'OSD Get radio/channel params';
  return null;
}

/// Per-(cmd_set, cmd_id) accumulated statistics across a capture.
class MessageStat {
  final int cmdSet;
  final int cmdId;
  int count = 0;
  final Set<int> payloadLengths = {};
  final Set<String> routes = {}; // "sender->receiver" device-type pairs
  Uint8List? _first; // first payload seen
  bool payloadConstant = true; // still identical across all seen so far

  MessageStat(this.cmdSet, this.cmdId);

  void add(DumlPacket p) {
    count++;
    payloadLengths.add(p.payload.length);
    routes.add('${p.senderType}->${p.receiverType}');
    if (_first == null) {
      _first = p.payload;
    } else if (payloadConstant) {
      final a = _first!;
      if (a.length != p.payload.length) {
        payloadConstant = false;
      } else {
        for (var i = 0; i < a.length; i++) {
          if (a[i] != p.payload[i]) {
            payloadConstant = false;
            break;
          }
        }
      }
    }
  }

  Uint8List get samplePayload => _first ?? Uint8List(0);

  /// A static, repeated payload on a frequently-seen message is a strong
  /// identifier/metadata candidate (e.g. a Master-ID or serial field).
  bool get looksLikeStaticId =>
      payloadConstant && count >= 3 && samplePayload.isNotEmpty;
}

/// Printable-ASCII run of >= minLen inside a payload — serial-number / name hint.
List<String> asciiRuns(Uint8List data, {int minLen = 4}) {
  final out = <String>[];
  final sb = StringBuffer();
  void flush() {
    if (sb.length >= minLen) out.add(sb.toString());
    sb.clear();
  }

  for (final b in data) {
    if (b >= 0x20 && b < 0x7f) {
      sb.writeCharCode(b);
    } else {
      flush();
    }
  }
  flush();
  return out;
}

/// The full inventory of a capture.
class StreamInventory {
  final Map<int, MessageStat> _byKey = {}; // key = set<<8 | id
  int total = 0;

  void add(DumlPacket p) {
    total++;
    final key = (p.cmdSet << 8) | p.cmdId;
    (_byKey[key] ??= MessageStat(p.cmdSet, p.cmdId)).add(p);
  }

  List<MessageStat> get messages {
    final l = _byKey.values.toList();
    l.sort((a, b) => b.count.compareTo(a.count));
    return l;
  }

  /// Build an inventory from already-decoded packets.
  static StreamInventory of(Iterable<DumlPacket> packets) {
    final inv = StreamInventory();
    for (final p in packets) {
      inv.add(p);
    }
    return inv;
  }

  /// A human-readable report: message table, static-ID candidates, ASCII strings.
  String report() {
    final b = StringBuffer();
    b.writeln('DUML capture inventory: $total packet(s), '
        '${messages.length} distinct message type(s)\n');
    b.writeln(
        'count  set  id    name                               len      route(s)');
    b.writeln(
        '-----  ---  ----  ---------------------------------  -------  --------');
    for (final m in messages) {
      final name =
          knownMessageName(m.cmdSet, m.cmdId) ?? '(${cmdSetName(m.cmdSet)})';
      final lens = m.payloadLengths.join(',');
      b.writeln('${m.count.toString().padLeft(5)}  '
          '0x${m.cmdSet.toRadixString(16).padLeft(2, '0')}  '
          '0x${m.cmdId.toRadixString(16).padLeft(2, '0')}  '
          '${name.padRight(33)}  ${lens.padRight(7)}  ${m.routes.join(' ')}');
    }

    final statics = messages.where((m) => m.looksLikeStaticId).toList();
    b.writeln(
        '\nStatic / repeated payloads (identifier & metadata candidates):');
    if (statics.isEmpty) {
      b.writeln(
          '  (none — need more packets, or no constant fields at message level)');
    } else {
      for (final m in statics) {
        b.writeln('  set 0x${m.cmdSet.toRadixString(16).padLeft(2, '0')} '
            'id 0x${m.cmdId.toRadixString(16).padLeft(2, '0')} '
            '(x${m.count}): ${_hex(m.samplePayload)}');
        for (final s in asciiRuns(m.samplePayload)) {
          b.writeln('      ascii: "$s"');
        }
      }
    }

    b.writeln(
        '\nASCII strings across all message types (serial / name hints):');
    final seen = <String>{};
    for (final m in messages) {
      for (final s in asciiRuns(m.samplePayload)) {
        if (seen.add(s)) {
          b.writeln(
              '  "$s"  (set 0x${m.cmdSet.toRadixString(16).padLeft(2, '0')} '
              'id 0x${m.cmdId.toRadixString(16).padLeft(2, '0')})');
        }
      }
    }
    if (seen.isEmpty) b.writeln('  (none)');
    return b.toString();
  }

  static String _hex(Uint8List d) {
    const max = 32;
    final take = d.length > max ? max : d.length;
    final s = [
      for (var i = 0; i < take; i++) d[i].toRadixString(16).padLeft(2, '0')
    ].join(' ');
    return d.length > max ? '$s … (${d.length}B)' : s;
  }
}
