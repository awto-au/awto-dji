import 'dart:async';
import 'dart:typed_data';

import 'package:duml/duml.dart';

import 'aoat.dart';
import 'bench_model.dart';

enum BenchMode { passive, echo, sink, source, duml }

/// The test-mode state machine. Pure Dart: bytes in via [onChunk]/[onDuml], bytes out via
/// [write], verdicts out via [onResult]. Params arrive in a [ModeCmd] (docs: AOA bench app).
///
/// Bounds (waits for / expected / multiplier / on expiry):
/// - source `dur_ms` (default 10000): a source run ends by `count`, or at `dur_ms`; the
///   longest planned throughput window is 2 s, 5x. Expiry: stop, emit `result`.
/// - source write: 3 consecutive failed writes end the run (a dead pipe fails at once;
///   3 rules out one transient). Result has pass=false and the error.
class ModeEngine {
  ModeEngine({
    required this.write,
    required this.onResult,
    required this.nowMs,
    this.log,
  });

  final Future<void> Function(Uint8List data) write;
  final void Function(Map<String, Object?> body) onResult;
  final int Function() nowMs;
  final void Function(String lvl, String msg)? log;

  BenchMode mode = BenchMode.passive;
  Map<String, Object?> params = const {};
  int testId = 0;
  AoatChecker? _checker;
  // sink bookkeeping outside the checker
  int _shortCount = 0, _shortBytes = 0, _echoChunks = 0, _echoBytes = 0;
  // duml bookkeeping
  int _dumlOk = 0, _dumlBad = 0, _dumlBytes = 0, _dumlAnswered = 0;
  // source bookkeeping
  int _sent = 0, _sentBytes = 0, _writeErrors = 0;
  String? _sourceError;
  bool _sourceDone = false;
  int _startMs = 0, _endMs = 0;
  int _gen = 0;

  int _int(String k, int d) => (params[k] as num?)?.toInt() ?? d;
  String _str(String k, String d) => params[k] as String? ?? d;

  /// Switch mode; null = done, else the rejection (state untouched). The previous test's
  /// verdict is emitted first when it did anything.
  String? setMode(ModeCmd cmd) {
    final m = BenchMode.values.where((v) => v.name == cmd.m).firstOrNull;
    if (m == null) {
      log?.call('W', 'unknown mode ${cmd.m}');
      return 'unknown mode ${cmd.m}';
    }
    final pat = cmd.params['pattern'];
    if (pat != null && !patternNames.containsKey(pat)) {
      log?.call('W', 'unknown pattern $pat');
      return 'unknown pattern $pat (${patternNames.keys.join('|')})';
    }
    if (_active) emitResult(final_: true);
    _gen++;
    mode = m;
    params = cmd.params;
    testId = _int('test', 0);
    _checker = AoatChecker(testId: params.containsKey('test') ? testId : null);
    _shortCount = _shortBytes = _echoChunks = _echoBytes = 0;
    _dumlOk = _dumlBad = _dumlBytes = _dumlAnswered = 0;
    _sent = _sentBytes = _writeErrors = 0;
    _sourceError = null;
    _sourceDone = false;
    _startMs = nowMs();
    _endMs = 0;
    log?.call('I', 'mode ${m.name} $params');
    if (m == BenchMode.source || (m == BenchMode.duml && _str('act', 'answer') == 'emit')) {
      unawaited(_runSource(_gen));
    }
    return null;
  }

  /// Zero the counters of the running mode without restarting it (a source keeps its
  /// frame index so `count` and the pattern sequence stay valid).
  void resetStats() {
    _checker = AoatChecker(testId: params.containsKey('test') ? testId : null);
    _shortCount = _shortBytes = _echoChunks = _echoBytes = 0;
    _dumlOk = _dumlBad = _dumlBytes = _dumlAnswered = 0;
    _sentBytes = _writeErrors = 0;
    _sourceError = null;
    _startMs = nowMs();
  }

  bool get _active =>
      mode != BenchMode.passive &&
      (_sent > 0 || (_checker?.report.frames ?? 0) > 0 || _echoChunks > 0 ||
          _shortCount > 0 || _dumlOk + _dumlBad > 0 || (_checker?.report.zlp ?? 0) > 0);

  // ---- receive side -----------------------------------------------------------------

  /// Raw bulk chunk (empty = ZLP). Not used in duml mode (mux path) or passive.
  void onChunk(Uint8List c) {
    switch (mode) {
      case BenchMode.echo:
        _echoChunks++;
        _echoBytes += c.length;
        unawaited(write(c)); // empty c = echo a zero-length write
      case BenchMode.sink:
        final startsMagic = c.length >= 4 && _eq(c, aoatMagic);
        // Headerless transfer (< 24 B, not an AOAT fragment): counted, verified by length only.
        if (c.isNotEmpty && c.length < aoatMinFrame && !startsMagic && _checker!.pending == 0) {
          _shortCount++;
          _shortBytes += c.length;
        } else {
          _checker!.feed(c);
        }
        final expect = _int('expect', 0);
        if (expect > 0 && _checker!.report.frames >= expect) {
          emitResult(final_: true);
          mode = BenchMode.passive;
        }
      case BenchMode.duml:
      case BenchMode.source:
      case BenchMode.passive:
        break;
    }
  }

  static bool _eq(Uint8List c, List<int> m) {
    for (var i = 0; i < m.length; i++) {
      if (c[i] != m[i]) return false;
    }
    return true;
  }

  /// A decoded DUML payload from the mux (duml mode). [ok] = DUML CRCs valid.
  void onDuml(Uint8List payload, bool ok) {
    if (mode != BenchMode.duml) return;
    _dumlBytes += payload.length;
    if (!ok) {
      _dumlBad++;
      return;
    }
    _dumlOk++;
    if (_str('act', 'answer') == 'answer') {
      final seq = payload[6] | (payload[7] << 8);
      final reply = DumlPacket(
        senderType: payload[5] & 0x1F,
        receiverType: payload[4] & 0x1F,
        sequence: seq,
        packetType: PacketType.response,
        ackType: AckType.none,
        cmdSet: payload[9],
        cmdId: payload[10],
        payload: Uint8List.fromList([0]),
      ).encode();
      _dumlAnswered++;
      unawaited(write(dumlEnvelope(reply)));
    }
  }

  static Uint8List dumlEnvelope(Uint8List frame, [int channel = 0x5749]) {
    final out = Uint8List(8 + frame.length);
    final bd = ByteData.sublistView(out);
    bd.setUint16(0, 0xcc55, Endian.little);
    bd.setUint16(2, channel, Endian.little);
    bd.setUint32(4, frame.length, Endian.little);
    out.setRange(8, out.length, frame);
    return out;
  }

  // ---- source side -----------------------------------------------------------------------

  Uint8List _frameFor(int seq, int size) {
    final seed = _int('seed', 1);
    if (mode == BenchMode.duml) {
      final bad = _str('bad', 'none');
      final mixBad = bad == 'mix' && seq % 4 == 3;
      return dumlEnvelope(dumlTestFrame(
        sender: _int('sender', DeviceType.pc),
        receiver: _int('receiver', DeviceType.app),
        cmdSet: _int('cmd_set', 0x02),
        cmdId: _int('cmd_id', 0x10),
        seq: _int('seq0', 0) + seq,
        payloadLen: _int('payload_len', 16),
        seed: seed,
        badHdrCrc: bad == 'hdr' || mixBad,
        badCrc: bad == 'crc',
        testId: testId,
      ));
    }
    if (size < aoatMinFrame) return makePayload(pAddr, size, seed, seq, testId);
    return buildFrame(size, patternNames[_str('pattern', 'addr')] ?? pAddr, seed, seq,
        testId: testId, flags: 0);
  }

  Future<void> _runSource(int gen) async {
    final size = _int('size', 64);
    final lo = _int('size_min', size), hi = _int('size_max', lo);
    final count = _int('count', 0);
    final rate = _int('rate', 0);
    final gapMs = _int('gap_ms', 0);
    final durMs = _int('dur_ms', 10000);
    final idle = _int('idle_ms', 0);
    if (idle > 0) await Future<void>.delayed(Duration(milliseconds: idle));
    _startMs = nowMs();
    var failures = 0;
    while (gen == _gen && (count == 0 || _sent < count) && nowMs() - _startMs < durMs) {
      final f = _frameFor(_sent, hi > lo ? randSize(lo, hi, _int('seed', 1), _sent, testId) : size);
      try {
        await write(f);
        failures = 0;
        _sentBytes += f.length;
      } on Object catch (e) {
        _writeErrors++;
        _sourceError = '$e';
        if (++failures >= 3) break;
      }
      _sent++;
      if (rate > 0) {
        final due = _startMs + (_sent * 1000 ~/ rate);
        final wait = due - nowMs();
        if (wait > 0) await Future<void>.delayed(Duration(milliseconds: wait));
      } else if (gapMs > 0) {
        await Future<void>.delayed(Duration(milliseconds: gapMs));
      } else {
        await Future<void>.delayed(Duration.zero); // yield so the UI/host link stay alive
      }
    }
    if (gen != _gen) return;
    _sourceDone = true;
    _endMs = nowMs();
    emitResult(final_: true);
  }

  // ---- verdict ------------------------------------------------------------------------------

  /// Live verdict (grid) and the `result` message body.
  Map<String, Object?> result() {
    final now = _endMs != 0 ? _endMs : nowMs();
    final elapsed = now - _startMs;
    final body = <String, Object?>{'test': testId, 'mode': mode.name, 'elapsed_ms': elapsed};
    switch (mode) {
      case BenchMode.sink:
        final r = _checker!.report..shortCount = _shortCount;
        body
          ..addAll(r.toJson())
          ..['bytes'] = r.bytes + _shortBytes
          ..['bytes_per_s'] = elapsed > 0 ? (r.bytes + _shortBytes) * 1000 / elapsed : 0;
      case BenchMode.echo:
        body
          ..['frames'] = _echoChunks
          ..['bytes'] = _echoBytes
          ..['zlp'] = 0
          ..['pass'] = true;
      case BenchMode.source:
        body
          ..['frames'] = _sent
          ..['bytes'] = _sentBytes
          ..['write_errors'] = _writeErrors
          ..['error'] = _sourceError
          ..['done'] = _sourceDone
          ..['bytes_per_s'] = elapsed > 0 ? _sentBytes * 1000 / elapsed : 0
          ..['pass'] = _writeErrors == 0;
      case BenchMode.duml:
        body
          ..['frames'] = _dumlOk + _dumlBad + _sent
          ..['bytes'] = _dumlBytes + _sentBytes
          ..['duml_ok'] = _dumlOk
          ..['duml_bad_crc'] = _dumlBad
          ..['answered'] = _dumlAnswered
          ..['sent'] = _sent
          ..['write_errors'] = _writeErrors
          ..['pass'] = _writeErrors == 0 && (_str('bad', 'none') != 'none' || _dumlBad == 0);
      case BenchMode.passive:
        body['pass'] = null;
    }
    return body;
  }

  void emitResult({bool final_ = false}) {
    if (mode == BenchMode.passive) return;
    final b = result();
    if (final_) b['final'] = true;
    onResult(b);
  }

  /// Fields for the state grid.
  ({int frames, int bytes, int bad, int? firstOffset, bool? pass}) grid() {
    if (mode == BenchMode.passive) return (frames: 0, bytes: 0, bad: 0, firstOffset: null, pass: null);
    final r = result();
    final fm = (r['first_mismatch'] as Map<String, Object?>?)?['offset'] as int?;
    return (
      frames: (r['frames'] as int?) ?? 0,
      bytes: (r['bytes'] as int?) ?? 0,
      bad: (r['bad_frames'] as int?) ?? (r['duml_bad_crc'] as int?) ?? (r['write_errors'] as int?) ?? 0,
      firstOffset: fm,
      pass: r['pass'] as bool?,
    );
  }

  void reset() {
    _gen++;
    mode = BenchMode.passive;
  }
}
