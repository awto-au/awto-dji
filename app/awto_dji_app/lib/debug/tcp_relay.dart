import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

/// Debug-only raw byte mirror, now bidirectional: forwards every chunk received from a
/// transport to a plain TCP socket (so the real decoder can run natively on a dev machine
/// instead of being rebuilt into the app for every protocol change), AND forwards any bytes
/// the dev machine sends back on that same socket to [onCommand] - a command proxy, so a PC
/// script can inject arbitrary DUML frames straight onto the AOA link with no UI involved
/// (see scripts/re/aoa_send.py / aoa_relay_server.py's control FIFO).
/// Best-effort: a relay failure never affects the real transport.
class TcpRelay {
  TcpRelay(this.host, this.port, {this.onCommand});
  final String host;
  final int port;
  final void Function(Uint8List bytes)? onCommand;
  Socket? _socket;
  StreamSubscription<Uint8List>? _sub;

  Future<void> connect() async {
    try {
      final s = await Socket.connect(host, port,
          timeout: const Duration(seconds: 3));
      _socket = s;
      debugPrint('[relay] connected to $host:$port');
      _sub = s.listen(
        (chunk) => onCommand?.call(chunk),
        onError: (Object e) => debugPrint('[relay] rx error: $e'),
      );
    } on Object catch (e) {
      debugPrint('[relay] connect failed: $e');
      _socket = null;
    }
  }

  void send(Uint8List chunk) {
    final s = _socket;
    if (s == null) return;
    try {
      s.add(chunk);
    } on Object catch (e) {
      debugPrint('[relay] send failed: $e');
    }
  }

  Future<void> close() async {
    await _sub?.cancel();
    _sub = null;
    try {
      await _socket?.close();
    } on Object {
      // best-effort
    }
    _socket = null;
  }
}
