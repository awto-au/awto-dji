import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';

import '../transport/aoa_transport.dart';
import '../transport/link_transport.dart';
import '../transport/replay_transport.dart';
import '../transport/simulated_transport.dart';
import '../video/video_decoder.dart';
import 'gimbal_commands.dart';
import 'link_session.dart';

/// Owns the link session. Driven by intents (see MainActivity.kt), no on-screen form.
class LinkHost extends ChangeNotifier {
  static const defaultRelay = '192.168.25.114:9900';

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
      case 'android.hardware.usb.action.USB_ACCESSORY_ATTACHED':
        await connect(extras);
      default:
        _setStatus('Unknown intent: $action');
    }
  }

  Future<void> connect(Map<String, String> extras) async {
    await disconnect();
    final source = extras['source'] ?? 'accessory';
    _setStatus('Connecting ($source)...');
    try {
      final transport = await _build(source, extras);
      final session = LinkSession(transport);
      await session.start();
      if (transport.currentState == LinkState.failed) {
        _setStatus(transport.lastError ?? 'connect failed');
        await _close(session);
        return;
      }
      _session = session;
      _setStatus('Connected ($source)');
    } on Object catch (e) {
      _setStatus('connect failed: $e');
    }
  }

  Future<void> disconnect() async {
    final s = _session;
    _session = null;
    if (s != null) await _close(s);
    _setStatus('Disconnected');
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
    await s.transport.write(_gimbal.angle(
      pitch: angle('pitch'),
      roll: angle('roll'),
      yaw: angle('yaw'),
      durationMs: int.tryParse(extras['duration'] ?? '') ?? 300,
      overtime: int.tryParse(extras['overtime'] ?? '') ?? 10,
    ));
    _setStatus('gimbal sent: pitch ${angle('pitch')} roll ${angle('roll')} yaw ${angle('yaw')}');
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
    final payload = Uint8List.fromList(
        [for (var i = 0; i < hex.length; i += 2) int.parse(hex.substring(i, i + 2), radix: 16)]);
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
    _setStatus('sent set=0x${set.toRadixString(16)} id=0x${id.toRadixString(16)} '
        'to 0x${receiver.toRadixString(16)}: ${payload.length}B payload');
  }

  Future<LinkTransport> _build(String source, Map<String, String> extras) async {
    _videoDecoder = null;
    switch (source) {
      case 'simulated':
        return SimulatedAircraftTransport();
      case 'replay':
        return ReplayTransport.fromFile(
            extras['path'] ?? '', speed: double.tryParse(extras['speed'] ?? '') ?? 1.0);
      default:
        final parts = (extras['relay'] ?? defaultRelay).split(':');
        final host = parts.isNotEmpty && parts[0].isNotEmpty ? parts[0] : null;
        final port = parts.length > 1 ? int.tryParse(parts[1]) : null;
        _videoDecoder = VideoDecoder();
        return AoaTransport(relayHost: host, relayPort: port, videoDecoder: _videoDecoder);
    }
  }

  Future<void> _close(LinkSession s) async {
    await s.stop();
    s.dispose();
  }

  void _setStatus(String s) {
    _status = s;
    notifyListeners();
  }
}
