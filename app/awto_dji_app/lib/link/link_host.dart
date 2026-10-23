import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';

import '../transport/aoa_transport.dart';
import '../transport/link_transport.dart';
import '../transport/replay_transport.dart';
import '../transport/simulated_transport.dart';
import '../video/video_decoder.dart';
import 'link_session.dart';

/// Owns the link session. Driven by intents (see MainActivity.kt), no on-screen form.
class LinkHost extends ChangeNotifier {
  static const defaultRelay = '192.168.25.114:9900';
  static const _deviceOsd = 0x0e;

  LinkSession? _session;
  VideoDecoder? _videoDecoder;
  String _status = 'Waiting for intent';
  int _seq = 0x7500;

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

  /// Sends the permission request, then the angle command, with no confirm step.
  /// The gimbal ignores angle commands without the permission (docs/apk-vs-dissector-gap-report).
  Future<void> sendGimbal(Map<String, String> extras) async {
    final s = _session;
    if (s == null) {
      _setStatus('gimbal: not connected');
      return;
    }
    double angle(String key) => double.tryParse(extras[key] ?? '') ?? 0;
    final permission = DumlPacket(
      senderType: DeviceType.app,
      receiverType: _deviceOsd, // not in the duml package yet
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.remote,
      cmdId: 0x22,
      payload: Uint8List(0),
    ).encode();
    final payload = ByteData(8)
      ..setInt16(0, (angle('pitch') * 10).round(), Endian.little)
      ..setInt16(2, (angle('roll') * 10).round(), Endian.little)
      ..setInt16(4, (angle('yaw') * 10).round(), Endian.little)
      ..setUint8(6, 0)
      ..setUint8(7, 5);
    final move = DumlPacket(
      senderType: DeviceType.app,
      receiverType: DeviceType.gimbal,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.gimbal,
      cmdId: 0x0a,
      payload: payload.buffer.asUint8List(),
    ).encode();
    await s.transport.write(permission);
    await s.transport.write(move);
    _setStatus('gimbal sent: pitch ${angle('pitch')} roll ${angle('roll')} yaw ${angle('yaw')}');
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
