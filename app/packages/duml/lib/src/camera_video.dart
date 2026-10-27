/// Classic DJI GO 3.1.8 recording-setting getters, checked against a saved P3 Pro
/// push. See docs/camera-video-push.md for hashes, locators and remaining limits.
library;

import 'generated/camera_push_state.dart';
import 'generated/camera_shot_params.dart';
import 'packet.dart';

export 'generated/camera_push_state.dart';
export 'generated/camera_shot_params.dart';

/// Pushes are requests with no ACK, from camera index 0 to app index 0. In
/// particular, a command ACK/error or another camera must not update this state.
bool _isCameraPush(DumlPacket p) =>
    p.senderType == DeviceType.camera &&
    p.senderIndex == 0 &&
    p.receiverType == DeviceType.app &&
    p.receiverIndex == 0 &&
    p.packetType == PacketType.request &&
    p.ackType == AckType.none;

class CameraStateInfo {
  const CameraStateInfo(this.raw);
  final CameraPushState raw;

  /// Classic GO CameraType.DJICameraTypeFC300X, observed in the owned P3 Pro.
  bool get isPhantom3Professional => raw.cameraType == 4;

  static CameraStateInfo? fromPacket(DumlPacket p) {
    if (!_isCameraPush(p)) return null;
    final raw = CameraPushState.fromPacket(p);
    return raw == null ? null : CameraStateInfo(raw);
  }
}

class CameraRecordingSettings {
  const CameraRecordingSettings(this.raw);
  final CameraShotParams raw;

  /// Only the five P3 recording sizes traced through classic GO's FC300X UI.
  /// Unrecognised wire values stay unknown rather than selecting a default.
  (int, int)? get resolution => switch (raw.resolutionCode) {
        4 => (1280, 720),
        10 => (1920, 1080),
        16 => (3840, 2160),
        22 => (4096, 2160),
        24 => (2704, 1520),
        _ => null,
      };

  /// Nominal UI rate. These codes do not establish exact rational timing (e.g.
  /// 24000/1001 versus 24); never substitute a MediaCodec-measured rate here.
  int? get nominalFrameRate => switch (raw.frameRateCode) {
        1 => 24,
        2 => 25,
        3 => 30,
        4 => 48,
        5 => 50,
        6 => 60,
        _ => null,
      };

  int? get primaryEncodingCode =>
      raw.videoEncodeByte == null ? null : raw.videoEncodeByte! & 0x0f;
  int? get secondaryEncodingCode =>
      raw.videoEncodeByte == null ? null : (raw.videoEncodeByte! >> 4) & 0x0f;

  String get resolutionLabel {
    final size = resolution;
    return size == null
        ? 'resolution ${_unknown(raw.resolutionCode)}'
        : '${size.$1} × ${size.$2}';
  }

  String get frameRateLabel => nominalFrameRate == null
      ? 'fps ${_unknown(raw.frameRateCode)}'
      : '$nominalFrameRate fps (nominal)';

  String get containerLabel => switch (raw.containerCode) {
        0 => 'MOV',
        1 => 'MP4',
        _ => 'container ${_unknown(raw.containerCode)}',
      };

  String get primaryEncodingLabel => switch (primaryEncodingCode) {
        null => 'encoding unavailable',
        0 => 'H.264',
        1 => 'H.265',
        final code => 'encoding ${_unknown(code)}',
      };

  String get description =>
      '$resolutionLabel · $frameRateLabel · $primaryEncodingLabel · $containerLabel';

  static String _unknown(int code) =>
      'unknown (0x${code.toRadixString(16).padLeft(2, '0')})';

  static CameraRecordingSettings? fromPacket(DumlPacket p) {
    if (!_isCameraPush(p)) return null;
    final raw = CameraShotParams.fromPacket(p);
    return raw == null ? null : CameraRecordingSettings(raw);
  }
}
