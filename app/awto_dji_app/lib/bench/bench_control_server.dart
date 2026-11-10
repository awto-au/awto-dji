import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'bench_model.dart';

/// Default control port (the bench app serves it; the PC dials in, e.g. `./dev.py ctl`).
const benchControlPort = 6560;

/// TCP command-and-control server, JSON lines both ways, same commands as the host link
/// plus `get`. Passive: no timers, no polling; a dead peer is dropped by TCP.
///
/// Bounds: [maxClients] 4 (a script, a harness, a human, one spare); the 5th is closed at
/// once with a logged reason. Bind failure is logged, never thrown: the app keeps running.
class BenchControlServer {
  BenchControlServer({
    required this.port,
    required this.onCmd,
    this.log,
    this.maxClients = 4,
  });

  final int port;

  /// [reply] answers only the asking client.
  final void Function(HostCmd cmd, void Function(AppMsg) reply) onCmd;
  final void Function(String level, String msg)? log;
  final int maxClients;

  ServerSocket? _server;
  final _clients = <Socket>{};

  int get clients => _clients.length;

  /// Bound port (differs from [port] when that is 0), or null when binding failed.
  Future<int?> start() async {
    try {
      final s = await ServerSocket.bind(InternetAddress.anyIPv4, port, shared: false);
      _server = s;
      s.listen(_accept, onError: (Object e) => log?.call('E', 'control accept: $e'));
      log?.call('I', 'control port ${s.port} listening');
      return s.port;
    } on Object catch (e) {
      log?.call('E', 'control port $port bind failed: $e');
      return null;
    }
  }

  void _accept(Socket c) {
    if (_clients.length >= maxClients) {
      log?.call('W', 'control: ${c.remoteAddress.address} refused (max $maxClients clients)');
      c.destroy();
      return;
    }
    c.setOption(SocketOption.tcpNoDelay, true);
    _clients.add(c);
    log?.call('I', 'control: ${c.remoteAddress.address} connected (${_clients.length})');
    void drop(String why) {
      if (_clients.remove(c)) log?.call('I', 'control: client gone ($why)');
      c.destroy();
    }

    c.done.then<void>((_) {}, onError: (_) {});
    c
        .cast<List<int>>()
        .transform(utf8.decoder)
        .transform(const LineSplitter())
        .listen(
          (line) {
            final cmd = HostCmd.decode(line);
            if (cmd == null) {
              _write(c, const ReplyMsg('?', {'error': 'unparsable or unknown command'}, ok: false));
            } else {
              onCmd(cmd, (m) => _write(c, m));
            }
          },
          onError: (Object e) => drop('$e'),
          onDone: () => drop('closed'),
          cancelOnError: true,
        );
  }

  void _write(Socket c, AppMsg m) {
    try {
      c.write('${m.encode()}\n');
    } on Object {
      _clients.remove(c);
      c.destroy();
    }
  }

  /// Push to every client (test verdicts).
  void broadcast(AppMsg m) {
    for (final c in _clients.toList()) {
      _write(c, m);
    }
  }

  Future<void> stop() async {
    await _server?.close();
    _server = null;
    for (final c in _clients.toList()) {
      c.destroy();
    }
    _clients.clear();
  }
}
