import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'bench_model.dart';

/// TCP client to scripts/re/bench_host.py. JSON lines both ways. Best-effort: a host
/// failure never affects the AOA side; it only retries.
///
/// Bounds (each: waits for / expected / multiplier / on expiry):
/// - [connectTimeout] 3 s: TCP connect on the LAN. Expected <= 1 s (WiFi power-save wake
///   plus one SYN retransmit at 1 s); 3x. Expiry: log, back off, retry.
/// - Backoff 1 s, 2 s, 4 s, 8 s then 8 s: a host script restart takes a few seconds; the
///   8 s cap bounds how long a freshly started script waits to see the app. Resets to 1 s
///   on a successful connect.
class BenchHostClient {
  BenchHostClient({
    required this.host,
    required this.port,
    required this.onCmd,
    required this.onConnection,
    this.log,
    this.connectTimeout = const Duration(seconds: 3),
    this.backoffStart = const Duration(seconds: 1),
    this.backoffCap = const Duration(seconds: 8),
  });

  final String host;
  final int port;
  final void Function(HostCmd cmd) onCmd;

  /// Called with true after TCP connect (send hello here), false on loss.
  final void Function(bool connected) onConnection;
  final void Function(String level, String msg)? log;
  final Duration connectTimeout, backoffStart, backoffCap;

  Socket? _socket;
  Timer? _retry;
  bool _running = false;
  Duration _backoff = Duration.zero;
  int _gen = 0;

  bool get connected => _socket != null;

  void start() {
    if (_running) return;
    _running = true;
    _backoff = backoffStart;
    _attempt();
  }

  Future<void> _attempt() async {
    if (!_running || _socket != null) return;
    final gen = ++_gen;
    try {
      final s = await Socket.connect(host, port, timeout: connectTimeout);
      if (!_running || gen != _gen) {
        s.destroy();
        return;
      }
      s.setOption(SocketOption.tcpNoDelay, true);
      _socket = s;
      _backoff = backoffStart;
      log?.call('I', 'host $host:$port connected');
      onConnection(true);
      s.done.then<void>((_) {}, onError: (_) {});
      s
          .cast<List<int>>()
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen(
            (line) {
              final cmd = HostCmd.decode(line);
              if (cmd == null) {
                log?.call('W', 'host: unparsable line: $line');
              } else {
                onCmd(cmd);
              }
            },
            onError: (Object e) => _lost(s, '$e'),
            onDone: () => _lost(s, 'closed by host'),
            cancelOnError: true,
          );
    } on Object catch (e) {
      log?.call('W', 'host $host:$port connect failed: $e; retry in ${_backoff.inSeconds} s');
      _scheduleRetry();
    }
  }

  void _lost(Socket s, String why) {
    if (!identical(_socket, s)) return;
    _socket = null;
    s.destroy();
    log?.call('W', 'host lost: $why');
    onConnection(false);
    _scheduleRetry();
  }

  void _scheduleRetry() {
    if (!_running) return;
    _retry?.cancel();
    final d = _backoff;
    _backoff = _backoff * 2 > backoffCap ? backoffCap : _backoff * 2;
    _retry = Timer(d, _attempt);
  }

  /// Fire-and-forget; dropped when not connected.
  void send(AppMsg m) {
    final s = _socket;
    if (s == null) return;
    try {
      s.write('${m.encode()}\n');
    } on Object catch (e) {
      _lost(s, 'write failed: $e');
    }
  }

  Future<void> stop() async {
    _running = false;
    _retry?.cancel();
    _retry = null;
    final s = _socket;
    _socket = null;
    if (s != null) {
      s.destroy();
      onConnection(false);
    }
  }
}
