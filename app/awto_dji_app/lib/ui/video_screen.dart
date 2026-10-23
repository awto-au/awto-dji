import 'package:flutter/material.dart';

import '../video/video_decoder.dart';

/// Shows the live H.264 decode from [decoder] (android/.../VideoShim.kt), if any. Only
/// populated on the Android accessory transport - other transports never set a decoder.
class VideoScreen extends StatelessWidget {
  const VideoScreen({super.key, required this.decoder});
  final VideoDecoder? decoder;

  @override
  Widget build(BuildContext context) {
    final id = decoder?.textureId;
    if (id == null) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Text(
            'No video texture. Only available over the Android accessory link, '
            'and only once H.264 NAL units have actually been seen on the wire.',
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    return Container(
      color: Colors.black,
      child: Center(child: Texture(textureId: id)),
    );
  }
}
