import 'dart:async';

import 'package:flutter/services.dart';

import '../debug/tcp_relay.dart';
import 'aoa_identity.dart';
import 'link_transport.dart';

/// Android Open Accessory link via the Kotlin shim (MainActivity). The phone is
/// the accessory, the RC is the USB host. Raw bytes only; no protocol logic.
///
/// [relayHost]/[relayPort], if set, mirror every received chunk to a plain TCP
/// socket (see lib/debug/tcp_relay.dart) so the real decoder can run natively
/// on a dev machine instead of being rebuilt into the app each iteration.
class AoaTransport extends BaseTransport {
  AoaTransport(
      {MethodChannel? method,
      EventChannel? events,
      this.relayHost,
      this.relayPort})
      : _method = method ?? const MethodChannel(methodChannelName),
        _events = events ?? const EventChannel(eventChannelName);

  static const methodChannelName = 'au.awto.dji/aoa';
  static const eventChannelName = 'au.awto.dji/aoa/bytes';

  final String? relayHost;
  final int? relayPort;

  final MethodChannel _method;
  final EventChannel _events;
  StreamSubscription<dynamic>? _sub;
  TcpRelay? _relay;

  @override
  String get name => 'android-accessory';

  @override
  Future<void> connect() async {
    setState(LinkState.connecting);
    if (relayHost != null && relayPort != null) {
      _relay = TcpRelay(relayHost!, relayPort!);
      await _relay!.connect();
    }
    try {
      _sub = _events.receiveBroadcastStream().listen(
        (dynamic b) {
          final chunk = b as Uint8List;
          _relay?.send(chunk);
          emit(chunk);
        },
        onError: (Object e) => setState(LinkState.failed, error: '$e'),
        onDone: () => setState(LinkState.disconnected),
      );
      await _method.invokeMethod<void>('connect', <String, String>{
        'manufacturer': AoaIdentity.manufacturer,
        'model': AoaIdentity.model,
      });
      setState(LinkState.connected);
    } on PlatformException catch (e) {
      await _sub?.cancel();
      _sub = null;
      await _relay?.close();
      _relay = null;
      setState(LinkState.failed, error: '${e.code}: ${e.message}');
    } on MissingPluginException {
      setState(LinkState.failed, error: 'not available on this platform');
    }
  }

  @override
  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
    await _relay?.close();
    _relay = null;
    try {
      await _method.invokeMethod<void>('disconnect');
    } on PlatformException {
      // Already closed.
    } on MissingPluginException {
      // Not on Android.
    }
    if (currentState != LinkState.disconnected) {
      setState(LinkState.disconnected);
    }
  }

  @override
  Future<void> write(Uint8List data) =>
      _method.invokeMethod<void>('write', data);
}
