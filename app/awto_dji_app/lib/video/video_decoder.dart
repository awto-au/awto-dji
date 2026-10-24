import 'package:flutter/services.dart';

import 'h264_access_units.dart';

/// Thin wrapper over the native MediaCodec decoder (android/.../VideoShim.kt). Not a transport -
/// just push extracted NAL units ([feedNal]) and show [textureId] in a Flutter `Texture` widget.
class VideoDecoder {
  VideoDecoder({MethodChannel? method})
    : _method = method ?? const MethodChannel('au.awto.dji/video');

  final MethodChannel _method;
  final _accessUnits = H264AccessUnits();
  int? textureId;

  Future<bool> start() async {
    _accessUnits.reset();
    try {
      final id = await _method.invokeMethod<int>('createTexture');
      textureId = id;
      return id != null;
    } on Object {
      textureId = null;
      return false;
    }
  }

  void feedNal(Uint8List nal) {
    if (textureId == null) return;
    for (final picture in _accessUnits.add(nal)) {
      _method.invokeMethod<void>('feedAccessUnit', picture).ignore();
    }
  }

  Future<void> stop() async {
    textureId = null;
    _accessUnits.reset();
    try {
      await _method.invokeMethod<void>('release');
    } on Object {
      // Already released or not on Android.
    }
  }
}
