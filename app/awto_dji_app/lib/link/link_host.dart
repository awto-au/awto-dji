import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';

import '../transport/aoa_transport.dart';
import '../transport/link_transport.dart';
import '../transport/replay_transport.dart';
import '../transport/simulated_transport.dart';
import '../video/video_decoder.dart';
import 'gimbal_commands.dart';
import 'duml_protection.dart';
import 'link_session.dart';

/// Owns the link session. Driven by intents (see MainActivity.kt), no on-screen form.
class LinkHost extends ChangeNotifier {
  LinkHost({
    this.transportFactory,
    this.reconnectDelay = const Duration(seconds: 2),
  });

  static const defaultRelay = '192.168.25.114:9900';
  final Future<LinkTransport> Function(String, Map<String, String>)?
  transportFactory;
  final Duration reconnectDelay;
  Future<void> _transition = Future.value();
  StreamSubscription<LinkState>? _linkStateSub;
  Timer? _retry;
  Map<String, String>? _desiredExtras;
  int _generation = 0;
  bool _wanted = false;
  bool _disposed = false;

  LinkSession? _session;
  VideoDecoder? _videoDecoder;
  String _status = 'Waiting for intent';
  final _gimbal = GimbalCommands();
  int _rawSeq = 0x7800;

  LinkSession? get session => _session;
  VideoDecoder? get videoDecoder => _videoDecoder;
  String get status => _status;

  Future<void> handle(String? action, Map<String, String> extras) async {
    switch (action) {
      case 'au.awto.dji.action.CONNECT':
        await connect(extras);
      case 'au.awto.dji.action.DISCONNECT':
        await disconnect();
      case 'au.awto.dji.action.GIMBAL':
        await sendGimbal(extras);
      case 'au.awto.dji.action.SEND':
        await sendRaw(extras);
      case null:
      case 'android.intent.action.MAIN':
        await connect({...?_desiredExtras, ...extras});
      case 'android.hardware.usb.action.USB_ACCESSORY_ATTACHED':
        await connect(_desiredExtras ?? extras);
      default:
        _setStatus('Unknown intent: $action');
    }
  }

  Future<void> _queue(Future<void> Function() operation) {
    final next = _transition.then((_) => operation());
    _transition = next.catchError((Object error) {
      if (!_disposed) _setStatus('link transition failed: $error');
    });
    return next;
  }

  Future<void> connect(Map<String, String> extras) {
    _wanted = true;
    _retry?.cancel();
    _retry = null;
    _desiredExtras = Map.of(extras);
    final generation = ++_generation;
    return _queue(() => _connectOnce(generation, Map.of(extras)));
  }

  void _scheduleReconnect(int generation) {
    final extras = _desiredExtras;
    if (!_wanted ||
        _disposed ||
        generation != _generation ||
        extras == null ||
        (extras['source'] ?? 'accessory') != 'accessory' ||
        _retry != null) {
      return;
    }
    _setStatus('Accessory disconnected; retrying...');
    _retry = Timer(reconnectDelay, () {
      _retry = null;
      _queue(() => _connectOnce(generation, Map.of(extras)));
    });
  }

  Future<void> _connectOnce(int generation, Map<String, String> extras) async {
    if (!_wanted || _disposed || generation != _generation) return;
    await _disconnectOnce();
    if (!_wanted || _disposed || generation != _generation) return;
    final source = extras['source'] ?? 'accessory';
    _setStatus('Connecting ($source)...');
    LinkSession? pending;
    try {
      final transport =
          await (transportFactory?.call(source, extras) ??
              _build(source, extras));
      final session = LinkSession(transport);
      pending = session;
      await session.start();
      if (!_wanted || _disposed || generation != _generation) {
        await _close(session);
        return;
      }
      if (transport.currentState != LinkState.connected) {
        _setStatus(transport.lastError ?? 'connect failed');
        await _close(session);
        _scheduleReconnect(generation);
        return;
      }
      _session = session;
      _linkStateSub = transport.state.listen((state) {
        if (state == LinkState.failed || state == LinkState.disconnected) {
          _scheduleReconnect(generation);
        }
      });
      _setStatus('Connected ($source)');
    } on Object catch (e) {
      if (pending != null) await _close(pending);
      if (_disposed || generation != _generation) return;
      _setStatus('connect failed: $e');
      _scheduleReconnect(generation);
    }
  }

  Future<void> disconnect() {
    _wanted = false;
    ++_generation;
    _retry?.cancel();
    _retry = null;
    return _queue(() async {
      await _disconnectOnce();
      if (!_disposed) _setStatus('Disconnected');
    });
  }

  Future<void> _disconnectOnce() async {
    await _linkStateSub?.cancel();
    _linkStateSub = null;
    final s = _session;
    _session = null;
    if (s != null) await _close(s);
  }

  /// Gimbal move: permission request, then the angle command. Extras: pitch, roll, yaw
  /// (degrees), duration (ms), overtime.
  Future<void> sendGimbal(Map<String, String> extras) async {
    final s = _session;
    if (s == null) {
      _setStatus('gimbal: not connected');
      return;
    }
    double angle(String key) => double.tryParse(extras[key] ?? '') ?? 0;
    await s.transport.write(_gimbal.permissionRequest());
    await s.transport.write(
      _gimbal.angle(
        pitch: angle('pitch'),
        roll: angle('roll'),
        yaw: angle('yaw'),
        durationMs: int.tryParse(extras['duration'] ?? '') ?? 300,
        overtime: int.tryParse(extras['overtime'] ?? '') ?? 10,
      ),
    );
    _setStatus(
      'gimbal sent: pitch ${angle('pitch')} roll ${angle('roll')} yaw ${angle('yaw')}',
    );
  }

  /// Any DUML command. Extras: set, id, receiver (required, decimal or 0x hex), sender
  /// (default app), ack (0-2, default 2), payload (hex, optional).
  Future<void> sendRaw(Map<String, String> extras) async {
    final s = _session;
    if (s == null) {
      _setStatus('send: not connected');
      return;
    }
    final set = int.tryParse(extras['set'] ?? '');
    final id = int.tryParse(extras['id'] ?? '');
    final receiver = int.tryParse(extras['receiver'] ?? '');
    if (set == null || id == null || receiver == null) {
      _setStatus('send: set, id and receiver are required');
      return;
    }
    final hex = (extras['payload'] ?? '').replaceAll(RegExp(r'\s'), '');
    if (hex.length.isOdd || !RegExp(r'^[0-9a-fA-F]*$').hasMatch(hex)) {
      _setStatus('send: payload must be hex bytes');
      return;
    }
    final payload = Uint8List.fromList([
      for (var i = 0; i < hex.length; i += 2)
        int.parse(hex.substring(i, i + 2), radix: 16),
    ]);
    final ack = (int.tryParse(extras['ack'] ?? '') ?? 2).clamp(0, 2);
    final pkt = DumlPacket(
      senderType: int.tryParse(extras['sender'] ?? '') ?? DeviceType.app,
      receiverType: receiver,
      sequence: _rawSeq++,
      ackType: AckType.values[ack],
      cmdSet: set,
      cmdId: id,
      payload: payload,
    ).encode();
    await s.transport.write(pkt);
    _setStatus(
      'sent set=0x${set.toRadixString(16)} id=0x${id.toRadixString(16)} '
      'to 0x${receiver.toRadixString(16)}: ${payload.length}B payload',
    );
  }

  Future<LinkTransport> _build(
    String source,
    Map<String, String> extras,
  ) async {
    _videoDecoder = null;
    switch (source) {
      case 'simulated':
        return SimulatedAircraftTransport();
      case 'replay':
        return ReplayTransport.fromFile(
          extras['path'] ?? '',
          speed: double.tryParse(extras['speed'] ?? '') ?? 1.0,
        );
      default:
        final parts = (extras['relay'] ?? defaultRelay).split(':');
        final host = parts.isNotEmpty && parts[0].isNotEmpty ? parts[0] : null;
        final port = parts.length > 1 ? int.tryParse(parts[1]) : null;
        _videoDecoder = VideoDecoder();
        final protection = switch (extras['protection'] ?? 'auto') {
          'auto' => DumlProtectionMode.auto,
          'none' => DumlProtectionMode.none,
          'simple' => DumlProtectionMode.simple,
          final value => throw ArgumentError('Unknown protection mode: $value'),
        };
        return AoaTransport(
          relayHost: host,
          relayPort: port,
          videoDecoder: _videoDecoder,
          protectionMode: protection,
          relayVideo: switch (extras['relayVideo'] ?? 'true') {
            'true' => true,
            'false' => false,
            final value => throw ArgumentError(
              'Unknown relayVideo value: $value',
            ),
          },
        );
    }
  }

  Future<void> _close(LinkSession s) async {
    await s.stop();
    s.dispose();
  }

  void _setStatus(String s) {
    if (_disposed) return;
    _status = s;
    notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    disconnect();
    super.dispose();
  }
}
