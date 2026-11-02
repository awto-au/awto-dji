import 'dart:typed_data';

import 'package:duml/duml.dart';

/// AOAT test frames. Mirror of scripts/re/aoa_testkit.py (format documented there);
/// scripts/re/aoat_vectors.json pins the two implementations together.
const aoatMagic = [0x41, 0x4f, 0x41, 0x54];
const aoatHeader = 20;
const aoatMinFrame = 24;
const _mask = 0xFFFFFFFF;

const pAddr = 0, pCounter = 1, pRandom = 2, pZeros = 3, pOnes = 4, pAlt = 5;
const patternNames = {
  'addr': pAddr,
  'counter': pCounter,
  'random': pRandom,
  'zeros': pZeros,
  'ones': pOnes,
  'alt': pAlt,
};

final _crcTable = () {
  final t = List<int>.filled(256, 0);
  for (var i = 0; i < 256; i++) {
    var c = i;
    for (var k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? (0xEDB88320 ^ (c >> 1)) : (c >> 1);
    }
    t[i] = c;
  }
  return t;
}();

int crc32(List<int> data, [int end = -1]) {
  var c = _mask;
  final n = end < 0 ? data.length : end;
  for (var i = 0; i < n; i++) {
    c = _crcTable[(c ^ data[i]) & 0xFF] ^ (c >> 8);
  }
  return (c ^ _mask) & _mask;
}

int mix(int seed, int seq, int testId) =>
    (((seq * 0x9E3779B1) & _mask) ^ seed ^ (testId << 16)) & _mask;

Uint8List makePayload(int pattern, int n, int seed, int seq, [int testId = 0]) {
  final out = Uint8List(n);
  switch (pattern) {
    case pAddr:
      final m = mix(seed, seq, testId);
      for (var o = 0; o < n; o += 4) {
        final w = ((o ^ m) & _mask);
        for (var b = 0; b < 4 && o + b < n; b++) {
          out[o + b] = (w >> (8 * b)) & 0xFF;
        }
      }
    case pCounter:
      for (var i = 0; i < n; i++) {
        out[i] = (i + seq) & 0xFF;
      }
    case pRandom:
      var s = mix(seed, seq, testId);
      if (s == 0) s = 1;
      for (var i = 0; i < n; i++) {
        s ^= (s << 13) & _mask;
        s ^= s >> 17;
        s ^= (s << 5) & _mask;
        out[i] = s & 0xFF;
      }
    case pZeros:
      break;
    case pOnes:
      out.fillRange(0, n, 0xFF);
    case pAlt:
      for (var i = 0; i < n; i++) {
        out[i] = i.isEven ? 0xAA : 0x55;
      }
    default:
      throw ArgumentError.value(pattern, 'pattern');
  }
  return out;
}

Uint8List buildFrame(int total, int pattern, int seed, int seq,
    {int testId = 0, int flags = 0}) {
  if (total < aoatMinFrame) {
    throw ArgumentError('AOAT frame needs >= $aoatMinFrame bytes, got $total');
  }
  final out = Uint8List(total);
  final bd = ByteData.view(out.buffer);
  out.setRange(0, 4, aoatMagic);
  bd.setUint16(4, testId, Endian.little);
  out[6] = pattern;
  out[7] = flags;
  bd.setUint32(8, seed, Endian.little);
  bd.setUint32(12, seq, Endian.little);
  bd.setUint32(16, total, Endian.little);
  out.setRange(aoatHeader, total - 4, makePayload(pattern, total - aoatMinFrame, seed, seq, testId));
  bd.setUint32(total - 4, crc32(out, total - 4), Endian.little);
  return out;
}

class Mismatch {
  const Mismatch(this.seq, this.offset, this.got, this.expected, this.hint);
  final int seq, offset;
  final List<int> got, expected;
  final String hint;
  Map<String, Object?> toJson() => {
    'seq': seq,
    'offset': offset,
    'got': got.map((b) => b.toRadixString(16).padLeft(2, '0')).join(),
    'expected': expected.map((b) => b.toRadixString(16).padLeft(2, '0')).join(),
    'hint': hint,
  };
}

Mismatch? firstMismatch(Uint8List got, Uint8List exp, int pattern, int seed, int seq, int testId) {
  final n = got.length < exp.length ? got.length : exp.length;
  List<int> w4(Uint8List b, int i) => b.sublist(i, i + 4 > b.length ? b.length : i + 4);
  for (var i = 0; i < n; i++) {
    if (got[i] != exp[i]) {
      var hint = '';
      final w = i & ~3;
      if (pattern == pAddr && got.length >= w + 4) {
        final v = ByteData.sublistView(got, w, w + 4).getUint32(0, Endian.little);
        hint = 'word at $w carries address ${v ^ mix(seed, seq, testId)}';
      }
      return Mismatch(seq, i, w4(got, i), w4(exp, i), hint);
    }
  }
  if (got.length != exp.length) {
    return Mismatch(seq, n, const [], const [], 'length got ${got.length} expected ${exp.length}');
  }
  return null;
}

/// Counters for one test run; `toJson` is the body of the `result` message.
class AoatReport {
  int frames = 0, bytes = 0, badFrames = 0, crcBad = 0;
  int seqGaps = 0, seqDups = 0, resyncBytes = 0, shortCount = 0, zlp = 0;
  Mismatch? firstMismatch;
  bool get passed => badFrames == 0 && seqGaps == 0 && seqDups == 0 && resyncBytes == 0;
  Map<String, Object?> toJson() => {
    'frames': frames,
    'bytes': bytes,
    'bad_frames': badFrames,
    'crc_bad': crcBad,
    'seq_gaps': seqGaps,
    'seq_dups': seqDups,
    'resync_bytes': resyncBytes,
    'short': shortCount,
    'zlp': zlp,
    'first_mismatch': firstMismatch?.toJson(),
    'pass': passed,
  };
}

/// Stream verifier, same rules as aoa_testkit.Checker. An empty chunk counts as a ZLP.
class AoatChecker {
  AoatChecker({this.testId, this.maxFrame = 1 << 20});
  final int? testId;
  final int maxFrame;
  final report = AoatReport();
  final List<int> _buf = [];
  int? _nextSeq;

  /// Bytes buffered of an incomplete frame.
  int get pending => _buf.length;

  void feed(Uint8List chunk) {
    if (chunk.isEmpty) {
      report.zlp++;
      return;
    }
    _buf.addAll(chunk);
    while (true) {
      final i = _find();
      if (i < 0) {
        _lose(_buf.length > 3 ? _buf.length - 3 : 0);
        return;
      }
      if (i > 0) _lose(i);
      if (_buf.length < aoatHeader) return;
      final bd = ByteData.sublistView(Uint8List.fromList(_buf.sublist(0, aoatHeader)));
      final tid = bd.getUint16(4, Endian.little);
      final pattern = bd.getUint8(6);
      final seed = bd.getUint32(8, Endian.little);
      final seq = bd.getUint32(12, Endian.little);
      final total = bd.getUint32(16, Endian.little);
      if (total < aoatMinFrame || total > maxFrame || pattern > pAlt) {
        _lose(1);
        continue;
      }
      if (_buf.length < total) return;
      final frame = Uint8List.fromList(_buf.sublist(0, total));
      _buf.removeRange(0, total);
      _check(frame, tid, pattern, seed, seq, total);
    }
  }

  int _find() {
    for (var i = 0; i + 4 <= _buf.length; i++) {
      if (_buf[i] == 0x41 && _buf[i + 1] == 0x4f && _buf[i + 2] == 0x41 && _buf[i + 3] == 0x54) {
        return i;
      }
    }
    return -1;
  }

  void _lose(int n) {
    if (n <= 0) return;
    report.resyncBytes += n;
    report.badFrames++;
    _buf.removeRange(0, n);
  }

  void _check(Uint8List f, int tid, int pattern, int seed, int seq, int total) {
    if (testId != null && tid != testId) {
      report.badFrames++;
      return;
    }
    report.frames++;
    report.bytes += total;
    final got = Uint8List.sublistView(f, aoatHeader, total - 4);
    final exp = makePayload(pattern, total - aoatMinFrame, seed, seq, tid);
    final crcOk = crc32(f, total - 4) == ByteData.sublistView(f).getUint32(total - 4, Endian.little);
    final mm = firstMismatch(got, exp, pattern, seed, seq, tid);
    if (!crcOk) report.crcBad++;
    if (!crcOk || mm != null) {
      report.badFrames++;
      report.firstMismatch ??= mm ?? Mismatch(seq, -1, const [], const [], 'crc only (payload equal)');
    }
    final next = _nextSeq;
    if (next != null) {
      if (seq > next) {
        report.seqGaps++;
      } else if (seq < next) {
        report.seqDups++;
      }
    }
    _nextSeq = (seq + 1) & _mask;
  }
}

/// DUML test frame with changeable addresses and a fake address-pattern payload.
/// [badHdrCrc]/[badCrc] flip one CRC byte. Wrapped in the AOA envelope by [duml envelope].
Uint8List dumlTestFrame({
  int sender = DeviceType.pc,
  int receiver = DeviceType.app,
  int cmdSet = 0x02,
  int cmdId = 0x10,
  int seq = 1,
  int payloadLen = 16,
  int seed = 0,
  bool badHdrCrc = false,
  bool badCrc = false,
  int testId = 0,
}) {
  final f = DumlPacket(
    senderType: sender,
    receiverType: receiver,
    sequence: seq,
    ackType: AckType.afterExec,
    cmdSet: cmdSet,
    cmdId: cmdId,
    payload: makePayload(pAddr, payloadLen, seed, seq, testId),
  ).encode();
  if (badHdrCrc) f[3] ^= 0xFF;
  if (badCrc) f[f.length - 1] ^= 0xFF;
  return f;
}
