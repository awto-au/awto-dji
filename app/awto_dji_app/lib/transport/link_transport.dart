import 'dart:async';
import 'dart:typed_data';

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

  /// Raw write. Read-only transports reject it; [LinkSession] never calls it.
  Future<void> write(Uint8List data);
}

/// Shared stream/state plumbing for the concrete transports.
abstract class BaseTransport implements LinkTransport {
  final _bytes = StreamController<Uint8List>.broadcast();
  final _state = StreamController<LinkState>.broadcast();
  LinkState _current = LinkState.disconnected;
  String? _error;

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
    if (!_state.isClosed) _state.add(s);
  }

  @override
  Future<void> write(Uint8List data) =>
      Future.error(UnsupportedError('$name is read-only'));

  Future<void> dispose() async {
    await disconnect();
    await _bytes.close();
    await _state.close();
  }
}
