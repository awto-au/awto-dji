import 'dart:async';

import 'package:flutter/services.dart';

import 'aoa_identity.dart';
import 'link_transport.dart';

/// Android Open Accessory link via the Kotlin shim (MainActivity). The phone is
/// the accessory, the RC is the USB host. Raw bytes only; no protocol logic.
/// Untested without hardware.
class AoaTransport extends BaseTransport {
  AoaTransport({MethodChannel? method, EventChannel? events})
      : _method = method ?? const MethodChannel(methodChannelName),
        _events = events ?? const EventChannel(eventChannelName);

  static const methodChannelName = 'au.awto.dji/aoa';
  static const eventChannelName = 'au.awto.dji/aoa/bytes';

  final MethodChannel _method;
  final EventChannel _events;
  StreamSubscription<dynamic>? _sub;

  @override
  String get name => 'android-accessory';

  @override
  Future<void> connect() async {
    setState(LinkState.connecting);
    try {
      _sub = _events.receiveBroadcastStream().listen(
        (dynamic b) => emit(b as Uint8List),
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
      setState(LinkState.failed, error: '${e.code}: ${e.message}');
    } on MissingPluginException {
      setState(LinkState.failed, error: 'not available on this platform');
    }
  }

  @override
  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
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
