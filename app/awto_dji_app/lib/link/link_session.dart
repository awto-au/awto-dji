import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';

import '../transport/link_transport.dart';

/// Gap between packet arrivals over a window: mean interval, jitter (standard deviation of the
/// interval) and the worst gap, in ms. Measured at chunk arrival on this device.
class GapStats {
  const GapStats(this.count, this.meanMs, this.jitterMs, this.maxMs);
  final int count;
  final double meanMs, jitterMs, maxMs;
}

/// Throughput over a window, KB/s.
class ByteRates {
  const ByteRates(this.duml, this.video, this.other);
  final double duml, video, other;
}

/// One received frame, good or bad, for the packet log.
class PacketLogEntry {
  PacketLogEntry(this.time, this.raw, {this.packet, this.error});
  final DateTime time;
  final Uint8List raw;
  final DumlPacket? packet; // null when the frame failed to decode
  final String? error;
  bool get crcOk => packet != null;
}

enum LinkHealth { noData, ok, stale }

/// Feeds transport bytes through [DumlFramer], decodes packets and OSD telemetry,
/// and keeps counters. Receive-only: it never writes to the transport.
class LinkSession extends ChangeNotifier {
  LinkSession(this.transport,
      {DateTime Function()? clock, this.maxLog = 2000, this.staleAfter = const Duration(seconds: 1)})
      : _clock = clock ?? DateTime.now {
    _framer.onBadFrame = _onBad;
  }

  final LinkTransport transport;
  final int maxLog;

  /// OSD arrives ~10 Hz; 1 s without any packet = 10 missed intervals.
  final Duration staleAfter;
  final DateTime Function() _clock;
  final _framer = DumlFramer();
  final _packets = StreamController<DumlPacket>.broadcast();
  final _telemetry = StreamController<OsdGeneral>.broadcast();
  final _entries = StreamController<PacketLogEntry>.broadcast();
  final _log = Queue<PacketLogEntry>();
  final _recent = Queue<DateTime>();
  final Map<int, int> messageCounts = {}; // key = set<<8 | id
  StreamSubscription<Uint8List>? _bytesSub;
  StreamSubscription<LinkState>? _stateSub;
  bool _disposed = false;

  int bytesReceived = 0;
  int dumlBytes = 0; // whole on-wire length of every CRC-valid packet
  int get videoBytes => transport.videoBytes;
  int packetCount = 0;
  int crcErrorCount = 0;
  DateTime? lastPacketAt;
  DateTime? lastTelemetryAt;
  OsdGeneral? latestOsd;
  LinkState linkState = LinkState.disconnected;

  Stream<DumlPacket> get packets => _packets.stream;
  Stream<OsdGeneral> get telemetry => _telemetry.stream;
  Stream<PacketLogEntry> get entries => _entries.stream;
  List<PacketLogEntry> get log => List.unmodifiable(_log);

  Future<void> start() async {
    _bytesSub = transport.bytes.listen(_onBytes);
    _stateSub = transport.state.listen((s) {
      linkState = s;
      _notify();
    });
    await transport.connect();
    linkState = transport.currentState;
    _notify();
  }

  Future<void> stop() async {
    await _bytesSub?.cancel();
    await _stateSub?.cancel();
    _bytesSub = _stateSub = null;
    await transport.disconnect();
    linkState = LinkState.disconnected;
    _notify();
  }

  LinkHealth healthAt(DateTime now) {
    final t = lastPacketAt;
    if (t == null) return LinkHealth.noData;
    return now.difference(t) > staleAfter ? LinkHealth.stale : LinkHealth.ok;
  }

  LinkHealth get health => healthAt(_clock());

  /// Packets in the last second.
  double packetsPerSecond([DateTime? now]) {
    final n = now ?? _clock();
    while (_recent.isNotEmpty &&
        n.difference(_recent.first) > const Duration(seconds: 1)) {
      _recent.removeFirst();
    }
    return _recent.length.toDouble();
  }

  void _onBytes(Uint8List chunk) {
    bytesReceived += chunk.length;
    debugPrint('[link] rx ${chunk.length}B total=$bytesReceived '
        '${_hex(chunk, 32)}');
    final now = _clock();
    final prev = lastPacketAt;
    var gotPacket = false;
    for (final p in _framer.add(chunk)) {
      gotPacket = true;
      packetCount++;
      dumlBytes += p.wholeLength;
      lastPacketAt = now;
      _recent.add(now);
      final key = (p.cmdSet << 8) | p.cmdId;
      messageCounts[key] = (messageCounts[key] ?? 0) + 1;
      _addEntry(PacketLogEntry(now, p.encode(), packet: p));
      debugPrint('[link] packet set=0x${p.cmdSet.toRadixString(16)} '
          'id=0x${p.cmdId.toRadixString(16)} sender=${p.senderType} '
          'receiver=${p.receiverType} ${_hex(p.encode(), 32)}');
      _packets.add(p);
      final osd = OsdGeneral.fromPacket(p);
      if (osd != null) {
        latestOsd = osd;
        lastTelemetryAt = now;
        _telemetry.add(osd);
      }
    }
    if (gotPacket && prev != null) {
      _gaps.add((now, now.difference(prev).inMilliseconds));
      while (_gaps.isNotEmpty && now.difference(_gaps.first.$1) > _gapHistory) {
        _gaps.removeFirst();
      }
    }
    _samples.add((now, bytesReceived, dumlBytes, videoBytes));
    while (_samples.length > 1 && now.difference(_samples.elementAt(1).$1) > _gapHistory) {
      _samples.removeFirst();
    }
    _notify();
  }

  final _samples = Queue<(DateTime, int, int, int)>(); // (time, total, duml, video) cumulative

  /// Throughput in KB/s over the last [window], split into DUML, video and everything else.
  ByteRates byteRates(Duration window, [DateTime? now]) {
    final n = now ?? _clock();
    if (_samples.isEmpty) return const ByteRates(0, 0, 0);
    final cur = _samples.last;
    var base = _samples.first;
    for (final s in _samples) {
      if (n.difference(s.$1) < window) break;
      base = s;
    }
    final secs = n.difference(base.$1).inMilliseconds / 1000;
    if (secs <= 0) return const ByteRates(0, 0, 0);
    final duml = cur.$3 - base.$3;
    final video = cur.$4 - base.$4;
    final other = math.max(0, (cur.$2 - base.$2) - duml - video);
    double kbps(int b) => b / secs / 1024;
    return ByteRates(kbps(duml), kbps(video), kbps(other));
  }

  static const _gapHistory = Duration(minutes: 1);
  final _gaps = Queue<(DateTime, int)>(); // (arrival, gap since previous packet in ms)

  /// Arrival-gap stats over the last [window] (at most one minute is kept).
  GapStats gapStats(Duration window, [DateTime? now]) {
    final n = now ?? _clock();
    final g = [
      for (final (t, ms) in _gaps)
        if (n.difference(t) <= window) ms
    ];
    if (g.isEmpty) return const GapStats(0, 0, 0, 0);
    final mean = g.reduce((a, b) => a + b) / g.length;
    final variance = g.map((x) => (x - mean) * (x - mean)).reduce((a, b) => a + b) / g.length;
    return GapStats(g.length, mean, math.sqrt(variance), g.reduce(math.max).toDouble());
  }

  void _onBad(Uint8List frame, String reason) {
    crcErrorCount = _framer.badFrames;
    debugPrint('[link] bad frame ($reason) ${frame.length}B ${_hex(frame, 32)}');
    _addEntry(PacketLogEntry(_clock(), frame, error: reason));
  }

  static String _hex(Uint8List b, int max) {
    final n = b.length > max ? max : b.length;
    final s = b.sublist(0, n).map((x) => x.toRadixString(16).padLeft(2, '0')).join(' ');
    return b.length > max ? '$s...' : s;
  }

  void _addEntry(PacketLogEntry e) {
    _log.add(e);
    if (_log.length > maxLog) _log.removeFirst();
    _entries.add(e);
  }

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    _bytesSub?.cancel();
    _stateSub?.cancel();
    _packets.close();
    _telemetry.close();
    _entries.close();
    super.dispose();
  }
}
