import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../debug/tcp_relay.dart';
import '../video/annexb_extractor.dart';
import '../video/video_decoder.dart';
import 'aoa_identity.dart';
import 'link_transport.dart';

/// Android Open Accessory link via the Kotlin shim (MainActivity). The phone is
/// the accessory, the RC is the USB host. Raw bytes only; no protocol logic.
///
/// [relayHost]/[relayPort], if set, mirror every received chunk to a plain TCP
/// socket (see lib/debug/tcp_relay.dart) so the real decoder can run natively
/// on a dev machine instead of being rebuilt into the app each iteration.
///
/// [videoDecoder], if set, also runs every chunk through [AnnexBExtractor] and feeds any
/// H.264 NAL units found to it - the raw AOA stream interleaves DUML and video with no demux
/// header (docs/aoa-live-test-2026-10-23.md), so this runs alongside normal DUML framing on
/// the exact same bytes, not instead of it.
class AoaTransport extends BaseTransport {
  AoaTransport(
      {MethodChannel? method,
      EventChannel? events,
      this.relayHost,
      this.relayPort,
      this.videoDecoder})
      : _method = method ?? const MethodChannel(methodChannelName),
        _events = events ?? const EventChannel(eventChannelName);

  static const methodChannelName = 'au.awto.dji/aoa';
  static const eventChannelName = 'au.awto.dji/aoa/bytes';

  final String? relayHost;
  final int? relayPort;
  final VideoDecoder? videoDecoder;

  final MethodChannel _method;
  final EventChannel _events;
  StreamSubscription<dynamic>? _sub;
  TcpRelay? _relay;
  final _nals = AnnexBExtractor();

  @override
  String get name => 'android-accessory';

  @override
  Future<void> connect() async {
    setState(LinkState.connecting);
    if (relayHost != null && relayPort != null) {
      _relay = TcpRelay(relayHost!, relayPort!);
      await _relay!.connect();
    }
    if (videoDecoder != null) await videoDecoder!.start();
    try {
      _sub = _events.receiveBroadcastStream().listen(
        (dynamic b) {
          final chunk = b as Uint8List;
          _relay?.send(chunk);
          if (videoDecoder != null) {
            for (final nal in _nals.add(chunk)) {
              videoDecoder!.feedNal(nal);
            }
          }
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
      if (_relay != null) _sendDiagQueries();
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
    await videoDecoder?.stop();
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

  /// Diag-relay-only (see [relayHost]): sends a handful of known-safe, read-only
  /// `Get*` status queries (never `Set*`/control) so their replies show up in the
  /// capture, matching docs/apk-vs-dissector-gap-report-2026-10-23.md's
  /// "safe to send" tier. One-shot, fires once right after connect.
  Future<void> _sendDiagQueries() async {
    var seq = 0x7000; // high range, won't collide with the real app's own sequence numbers
    final queries = <(int cmdSet, int cmdId, String label)>[
      (CmdSet.hdLink, 0x05, 'GetFPGA'),
      (CmdSet.hdLink, 0x07, 'Get9363'),
      (CmdSet.general, 0x01, 'GetVersion'),
    ];
    for (final (cmdSet, cmdId, label) in queries) {
      final pkt = DumlPacket(
        senderType: DeviceType.pc,
        receiverType: DeviceType.remoteController,
        sequence: seq++,
        ackType: AckType.afterExec,
        cmdSet: cmdSet,
        cmdId: cmdId,
      );
      debugPrint('[aoa-diag] sending $label (set=0x${cmdSet.toRadixString(16)} '
          'id=0x${cmdId.toRadixString(16)})');
      try {
        await write(pkt.encode());
      } on Object catch (e) {
        debugPrint('[aoa-diag] $label send failed: $e');
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }
}
