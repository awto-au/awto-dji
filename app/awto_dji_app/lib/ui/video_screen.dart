import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../transport/aoa_transport.dart';
import '../video/video_decoder.dart';
import 'camera_video_info.dart';

/// Shows the live H.264 decode from [decoder] (android/.../VideoShim.kt), if any. Only
/// populated on the Android accessory transport - other transports never set a decoder.
///
/// Carries a manual "Request keyframe" action ([AoaTransport.requestIFrame]) because a decode
/// session that starts mid-GOP never sees SPS/PPS/IDR on its own
/// (docs/aoa-live-test-2026-10-23.md) - this is sent automatically on connect, but a retry
/// button covers the case where the first request was missed or the encoder restarted since.
class VideoScreen extends StatelessWidget {
  const VideoScreen({super.key, required this.decoder, this.session});
  final VideoDecoder? decoder;
  final LinkSession? session;

  @override
  Widget build(BuildContext context) {
    final id = decoder?.textureId;
    final transport = session?.transport;
    final canRequestFrame = transport is AoaTransport;
    final body = id == null
        ? const Center(
            child: Padding(
              padding: EdgeInsets.all(24),
              child: Text(
                'No video texture yet. Only available over the Android accessory link, '
                'and only once H.264 NAL units have actually been seen on the wire.',
                textAlign: TextAlign.center,
              ),
            ),
          )
        : Container(
            color: Colors.black,
            child: Center(child: Texture(textureId: id)),
          );
    return Stack(
      children: [
        body,
        if (session != null)
          Positioned(
            left: 8,
            right: 8,
            top: 8,
            child: CameraVideoInfo(session: session!),
          ),
        if (canRequestFrame)
          Positioned(
            right: 16,
            bottom: 16,
            child: FloatingActionButton.extended(
              onPressed: () => (transport as AoaTransport).requestIFrame(),
              icon: const Icon(Icons.refresh),
              label: const Text('Request keyframe'),
            ),
          ),
      ],
    );
  }
}
