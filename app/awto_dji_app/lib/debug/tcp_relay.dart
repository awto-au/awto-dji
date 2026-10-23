import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

/// Debug-only raw byte mirror: forwards every chunk received from a transport
/// to a plain TCP socket, so the real decoder can run natively on a dev
/// machine instead of being rebuilt into the app for every protocol change.
/// Best-effort: a relay failure never affects the real transport.
class TcpRelay {
  TcpRelay(this.host, this.port);
  final String host;
  final int port;
  Socket? _socket;

  Future<void> connect() async {
    try {
      _socket = await Socket.connect(host, port,
          timeout: const Duration(seconds: 3));
      debugPrint('[relay] connected to $host:$port');
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
    try {
      await _socket?.close();
    } on Object {
      // best-effort
    }
    _socket = null;
  }
}
