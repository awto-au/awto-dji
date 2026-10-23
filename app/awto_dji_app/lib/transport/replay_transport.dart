import 'dart:async';
import 'dart:typed_data';

import 'capture_loader.dart';
import 'link_transport.dart';

/// Plays a raw DUML capture as if it were the live link.
/// Captures carry no timestamps, so pacing is one frame per [frameInterval]
/// (default 100 ms ~ 10 Hz OSD push) divided by [speed]; speed <= 0 = unpaced.
class ReplayTransport extends BaseTransport {
  ReplayTransport(
    this.data, {
    this.label = 'replay',
    this.frameInterval = const Duration(milliseconds: 100),
    this.speed = 1.0,
    this.loop = false,
  });

  /// Raw bytes, or hex text, from a file.
  static Future<ReplayTransport> fromFile(String path,
      {double speed = 1.0, bool loop = false}) async {
    return ReplayTransport(await loadCaptureFile(path),
        label: 'replay:$path', speed: speed, loop: loop);
  }

  final Uint8List data;
  final String label;
  final Duration frameInterval;
  final double speed;
  final bool loop;
  int _gen = 0;

  @override
  String get name => label;

  @override
  Future<void> connect() async {
    setState(LinkState.connecting);
    setState(LinkState.connected);
    unawaited(_play(++_gen));
  }

  @override
  Future<void> disconnect() async {
    _gen++;
    if (currentState != LinkState.disconnected) {
      setState(LinkState.disconnected);
    }
  }

  Future<void> _play(int gen) async {
    final frames = splitFrames(data);
    final delay = speed > 0
        ? Duration(microseconds: (frameInterval.inMicroseconds / speed).round())
        : Duration.zero;
    do {
      for (final f in frames) {
        if (gen != _gen) return;
        emit(f);
        // Unpaced still yields so listeners run between frames.
        await (speed > 0 ? Future<void>.delayed(delay) : Future<void>.value());
      }
    } while (loop && gen == _gen && frames.isNotEmpty);
    if (gen == _gen) setState(LinkState.disconnected); // end of capture
  }
}
