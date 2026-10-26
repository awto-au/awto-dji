import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../debug/tcp_relay.dart';
import '../debug/relay_record.dart';
import '../debug/udp_raw_relay.dart';
import '../link/duml_protection.dart';
import '../video/annexb_extractor.dart';
import '../video/video_decoder.dart';
import 'aoa_identity.dart';
import 'aoa_mux.dart';
import 'link_transport.dart';

/// Android Open Accessory link via the Kotlin shim (MainActivity). The phone is
/// the accessory, the RC is the USB host. Demultiplexes AOA envelopes and applies the
/// configured DUML protection policy to outgoing command frames.
///
/// [relayHost]/[relayPort], if set, forward framed records to a plain TCP
/// socket (see lib/debug/tcp_relay.dart) so the real decoder can run natively
/// on a dev machine instead of being rebuilt into the app each iteration.
///
/// Only command payloads reach LinkSession/protection; only camera video reaches
/// [AnnexBExtractor]. Unknown channels remain visible in the diagnostic relay.
class AoaTransport extends BaseTransport {
  AoaTransport({
    MethodChannel? method,
    EventChannel? events,
    this.relayHost,
    this.relayPort,
    this.videoDecoder,
    this.relayVideo = true,
    DumlProtectionMode protectionMode = DumlProtectionMode.auto,
  }) : _method = method ?? const MethodChannel(methodChannelName),
       _events = events ?? const EventChannel(eventChannelName),
       _protection = DumlProtection(mode: protectionMode) {
    _mux.onPacket = _onPacket;
    _mux.onDiscard = (bytes) =>
        _relay?.sendRecord(RelayRecord.discarded, 0, bytes);
  }

  static const methodChannelName = 'au.awto.dji/aoa';
  static const eventChannelName = 'au.awto.dji/aoa/bytes';

  final String? relayHost;
  final int? relayPort;
  final VideoDecoder? videoDecoder;

  /// Suppress camera/FPV records on WiFi only; local decoding is unaffected.
  final bool relayVideo;

  final MethodChannel _method;
  final EventChannel _events;
  StreamSubscription<dynamic>? _sub;
  TcpRelay? _relay;
  UdpRawRelay? _udpRaw;
  final _nals = AnnexBExtractor();
  final DumlProtection _protection;
  final _mux = AoaMux();

  void _onPacket(AoaPacket packet) {
    final video =
        packet.channel == AoaMux.cameraVideo ||
        packet.channel == AoaMux.fpvVideo;
    if (!video || relayVideo) {
      _relay?.sendRecord(RelayRecord.envelope, packet.channel, packet.encode());
    }
    if (packet.channel == AoaMux.command) {
      _protection.observe(packet.payload);
      emit(packet.payload);
    } else if (packet.channel == AoaMux.cameraVideo) {
      videoBytes += packet.payload.length;
      if (videoDecoder != null) {
        for (final nal in _nals.add(packet.payload)) {
          videoDecoder!.feedNal(nal);
        }
      }
    }
  }

  @override
  String get name => 'android-accessory';

  @override
  Future<void> connect() async {
    _protection.reset();
    _mux.reset();
    _nals.reset();
    videoBytes = 0;
    setState(LinkState.connecting);
    Future<void>? relayConnecting;
    if (relayHost != null && relayPort != null) {
      _relay = TcpRelay(
        relayHost!,
        relayPort!,
        onCommand: (bytes) {
          debugPrint(
            '[aoa-proxy] relaying ${bytes.length}B command from PC to accessory',
          );
          for (final frame in _protection.prepareProxyBytes(bytes)) {
            write(frame).catchError((Object error) {
              debugPrint('[aoa-proxy] write failed: $error');
            });
          }
        },
      );
      relayConnecting = _relay!.connect();
      // Raw ground-truth stream lives on its own UDP port (TCP relay port + 1,
      // see scripts/re/aoa_relay_server.py's UDP listener) - independent of
      // the TCP relay above, never gated on it.
      _udpRaw = UdpRawRelay(relayHost!, relayPort! + 1);
      unawaited(_udpRaw!.connect());
    }
    try {
      _sub = _events.receiveBroadcastStream().listen(
        (dynamic b) {
          final chunk = b as Uint8List;
          // Ground truth for the PC side, independent of AoaMux - see UdpRawRelay.
          _udpRaw?.send(chunk);
          _mux.add(chunk);
        },
        onError: (Object e) {
          _mux.finish();
          _protection.reset();
          _nals.reset();
          setState(LinkState.failed, error: '$e');
        },
        onDone: () {
          _mux.finish();
          _protection.reset();
          _nals.reset();
          setState(LinkState.disconnected);
        },
      );
      await _method.invokeMethod<void>('connect', <String, String>{
        'manufacturer': AoaIdentity.manufacturer,
        'model': AoaIdentity.model,
      });
      // Claim the accessory inside Android's handshake window. Decoder startup
      // and a slow/absent debug relay must not delay openAccessory().
      if (videoDecoder != null) await videoDecoder!.start();
      await relayConnecting;
      setState(LinkState.connected);
      if (_relay != null) _sendDiagQueries();
      if (videoDecoder != null) await requestIFrame();
    } on PlatformException catch (e) {
      await _sub?.cancel();
      _sub = null;
      await relayConnecting;
      await _relay?.close();
      _relay = null;
      _udpRaw?.close();
      _udpRaw = null;
      await videoDecoder?.stop();
      setState(LinkState.failed, error: '${e.code}: ${e.message}');
    } on MissingPluginException {
      await _sub?.cancel();
      _sub = null;
      await relayConnecting;
      await _relay?.close();
      _relay = null;
      _udpRaw?.close();
      _udpRaw = null;
      await videoDecoder?.stop();
      setState(LinkState.failed, error: 'not available on this platform');
    }
  }

  @override
  Future<void> disconnect() async {
    await _sub?.cancel();
    _sub = null;
    _mux.finish();
    _protection.reset();
    _nals.reset();
    await _relay?.close();
    _relay = null;
    _udpRaw?.close();
    _udpRaw = null;
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
  Future<void> write(Uint8List data) {
    final wire = _protection.prepare(data);
    debugPrint(
      '[aoa-tx] ${wire.length}B '
      '${wire.map((v) => v.toRadixString(16).padLeft(2, '0')).join()}',
    );
    return _method.invokeMethod<void>('write', wire);
  }

  var _ifrSeq = 0x7100;

  /// `RequestIFrame` (CmdSet.camera/0xb3, docs/data/apk-dynamic-cmdset-ids.tsv:182) - asks the
  /// camera encoder to emit a fresh SPS/PPS/IDR now, instead of waiting for one. Needed because
  /// a capture/decode session that starts mid-GOP never sees parameter sets
  /// (docs/aoa-live-test-2026-10-23.md "Video decode... needs a capture that spans stream
  /// start"). Only affects the video encoder's own GOP timing.
  Future<void> requestIFrame() async {
    final pkt = DumlPacket(
      senderType: DeviceType.app,
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
      if (currentState != LinkState.connected) return;
      final pkt = DumlPacket(
        senderType: DeviceType.pc,
        receiverType: DeviceType.remoteController,
        sequence: seq++,
        ackType: AckType.afterExec,
        cmdSet: cmdSet,
        cmdId: cmdId,
      );
      debugPrint(
        '[aoa-diag] sending $label (set=0x${cmdSet.toRadixString(16)} '
        'id=0x${cmdId.toRadixString(16)})',
      );
      try {
        await write(pkt.encode());
      } on Object catch (e) {
        debugPrint('[aoa-diag] $label send failed: $e');
      }
      await Future<void>.delayed(const Duration(milliseconds: 200));
    }
  }
}
