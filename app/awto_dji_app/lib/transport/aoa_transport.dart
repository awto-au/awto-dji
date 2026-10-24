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
      _relay = TcpRelay(relayHost!, relayPort!, onCommand: (bytes) {
        debugPrint('[aoa-proxy] relaying ${bytes.length}B command from PC to accessory');
        write(bytes);
      });
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
              videoBytes += nal.length;
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
      if (videoDecoder != null) await requestIFrame();
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

  var _ifrSeq = 0x7100;

  /// `RequestIFrame` (CmdSet.camera/0xb3, docs/data/apk-dynamic-cmdset-ids.tsv:182) - asks the
  /// camera encoder to emit a fresh SPS/PPS/IDR now, instead of waiting for one. Needed because
  /// a capture/decode session that starts mid-GOP never sees parameter sets
  /// (docs/aoa-live-test-2026-10-23.md "Video decode... needs a capture that spans stream
  /// start"). Only affects the video encoder's own GOP timing.
  Future<void> requestIFrame() async {
    final pkt = DumlPacket(
      senderType: DeviceType.pc,
      receiverType: DeviceType.camera,
      sequence: _ifrSeq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.camera,
      cmdId: 0xb3,
    );
    debugPrint('[aoa-video] requesting I-frame (set=0x2 id=0xb3)');
    try {
      await write(pkt.encode());
    } on Object catch (e) {
      debugPrint('[aoa-video] I-frame request failed: $e');
    }
  }

  /// Diag-relay-only (see [relayHost]): sends a handful of `Get*` status queries so their
  /// replies show up in the capture. One-shot, fires once right after connect.
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
