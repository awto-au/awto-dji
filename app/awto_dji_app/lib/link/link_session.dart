import 'dart:async';
import 'dart:collection';

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';

import '../transport/link_transport.dart';

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
    final now = _clock();
    for (final p in _framer.add(chunk)) {
      packetCount++;
      lastPacketAt = now;
      _recent.add(now);
      final key = (p.cmdSet << 8) | p.cmdId;
      messageCounts[key] = (messageCounts[key] ?? 0) + 1;
      _addEntry(PacketLogEntry(now, p.encode(), packet: p));
      _packets.add(p);
      final osd = OsdGeneral.fromPacket(p);
      if (osd != null) {
        latestOsd = osd;
        lastTelemetryAt = now;
        _telemetry.add(osd);
      }
    }
    _notify();
  }

  void _onBad(Uint8List frame, String reason) {
    crcErrorCount = _framer.badFrames;
    _addEntry(PacketLogEntry(_clock(), frame, error: reason));
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
