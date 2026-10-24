import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/foundation.dart';

enum LinkState { disconnected, connecting, connected, failed }

/// Raw byte pipe to the aircraft link. No protocol logic lives here.
abstract class LinkTransport {
  String get name;
  LinkState get currentState;
  String? get lastError;

  /// Broadcast: subscribe before [connect] to avoid missing the first bytes.
  Stream<Uint8List> get bytes;
  Stream<LinkState> get state;

  Future<void> connect();
  Future<void> disconnect();

  /// Raw write to the device. Transports with no device (simulated, replay) reject it.
  Future<void> write(Uint8List data);

  /// Bytes of H.264 NAL units carried on the same pipe as DUML (0 if the transport has none).
  int get videoBytes;
}

/// Shared stream/state plumbing for the concrete transports.
abstract class BaseTransport implements LinkTransport {
  final _bytes = StreamController<Uint8List>.broadcast();
  final _state = StreamController<LinkState>.broadcast();
  LinkState _current = LinkState.disconnected;
  String? _error;

  @override
  int videoBytes = 0;

  @override
  LinkState get currentState => _current;
  @override
  String? get lastError => _error;
  @override
  Stream<Uint8List> get bytes => _bytes.stream;
  @override
  Stream<LinkState> get state => _state.stream;

  void emit(Uint8List chunk) {
    if (!_bytes.isClosed) _bytes.add(chunk);
  }

  void setState(LinkState s, {String? error}) {
    _current = s;
    _error = error;
    debugPrint('[transport:$name] state=$s${error != null ? ' error=$error' : ''}');
    if (!_state.isClosed) _state.add(s);
  }

  @override
  Future<void> write(Uint8List data) =>
      Future.error(UnsupportedError('$name has no device to write to'));

  Future<void> dispose() async {
    await disconnect();
    await _bytes.close();
    await _state.close();
  }
}
