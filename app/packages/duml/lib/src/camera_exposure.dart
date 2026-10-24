/// Camera AE-lock, exposure-compensation and exposure-mode decoders
/// (`cmd_set = 0x02` "CAMERA"). Companion builders:
/// `app/awto_dji_app/lib/link/camera_commands.dart` - see that file for the exact
/// UI call sites this was reversed from (awto-dji#38).
///
/// V (AE lock): `dji.midware.data.model.P3.DataCameraSetAELock`/`DataCameraGetAELock`
/// - byte-identical in `tmp/apk/dynamic` (dji.go.v4) and `tmp/apk/pilot_dynamic`
/// (DJI Pilot). `doPack()`/`isLock()` read/write a single byte, 1 = locked. The real
/// toggle button (`DJIFpvTopBaseView.l()`, view id 2131298860, tracked event
/// "FPV_RightBarView_CameraControllView_Button_AELock") sends
/// `DataCameraSetAELock.getInstance().a(!this.xI).start(...)`, where `this.xI`
/// mirrors `DataCameraGetPushShotParams.isAELock()` (push payload byte 56, same 0/1
/// encoding). No dedicated `DataCameraGetAELock` reply struct was decompiled (the
/// app reads lock state from the push, not a direct Get/reply round-trip) - this
/// decoder assumes the Get reply uses the same 1-byte layout as the Set payload and
/// the push field **(I)**.
///
/// V (exposure compensation): payload is a single raw byte, step 1..31, 1/3-EV
/// units, 16 = 0.0 EV. Cross-checked three ways: `DataCameraSetEV.doPack()`
/// (`tmp/apk/pilot_dynamic` only - not found in `tmp/apk/dynamic`, see awto-dji#38
/// comment), 1-byte payload, driven by the real EV +/-/reset buttons
/// (`DJICameraSettingBaseView$1`, tracked events
/// "FPV_LeftBarView_CameraAdvancedView_Button_EvAdd/EvSub/EvReset"); the live push
/// field `DataCameraGetPushShotParams.getExposureCompensation()` (byte offset 6, 1
/// byte, same scale); and the public SDK enum
/// `dji.common.camera.DJICameraSettingsDef$CameraExposureCompensation`
/// (N_5_0=1 .. N_0_0=16 .. P_5_0=31, 1/3-EV steps) - same numbering. No dedicated
/// `GetExposureCompensation` reply struct was decompiled; assumed same 1-byte
/// layout **(I)**.
///
/// V (exposure mode): 2-byte payload, byte0 = mode, byte1 = scene index (only sent
/// when mode == `scn`) - `DataCameraSetExposureMode.doPack()`/`ExposureMode` enum,
/// identical in both APK trees. No dedicated `GetExposureMode` reply struct was
/// decompiled; assumed same 2-byte layout **(I)**.
library;

import 'packet.dart';

/// Mirrors `dji.midware.data.model.P3.DataCameraSetExposureMode.ExposureMode`'s
/// real enum values exactly.
enum CameraExposureMode {
  auto(0),
  p(1),
  s(2),
  a(3),
  m(4),
  b(5),
  scn(6),
  c(7),
  other(100);

  const CameraExposureMode(this.value);
  final int value;

  static CameraExposureMode fromValue(int v) => CameraExposureMode.values
      .firstWhere((e) => e.value == v, orElse: () => CameraExposureMode.other);
}

class CameraAeLock {
  final bool locked;
  const CameraAeLock(this.locked);

  static const int cmdSet = CmdSet.camera;
  static const int cmdId = 0x69; // GetAELock, per scripts/re/duml_catalog.py

  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.isNotEmpty;

  static CameraAeLock? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return CameraAeLock(p.payload[0] == 1);
  }

  @override
  String toString() => 'CameraAeLock(locked=$locked)';
}

class CameraExposureCompensation {
  /// Raw wire step, 1..31 (1/3-EV units, 16 = 0.0 EV).
  final int rawStep;
  const CameraExposureCompensation(this.rawStep);

  /// EV stops, e.g. -1.0, 0.0, +0.3.
  double get ev => (rawStep - 16) / 3.0;

  static const int cmdSet = CmdSet.camera;
  static const int cmdId = 0x2f; // GetExposureCompensation

  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.isNotEmpty;

  static CameraExposureCompensation? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return CameraExposureCompensation(p.payload[0]);
  }

  @override
  String toString() =>
      'CameraExposureCompensation(raw=$rawStep ev=${ev.toStringAsFixed(1)})';
}

class CameraExposureModeState {
  final CameraExposureMode mode;

  /// Scene index; only meaningful when [mode] is [CameraExposureMode.scn].
  final int scene;
  const CameraExposureModeState(this.mode, this.scene);

  static const int cmdSet = CmdSet.camera;
  static const int cmdId = 0x1f; // GetExposureMode

  static bool matches(DumlPacket p) =>
      p.cmdSet == cmdSet && p.cmdId == cmdId && p.payload.length >= 2;

  static CameraExposureModeState? fromPacket(DumlPacket p) {
    if (!matches(p)) return null;
    return CameraExposureModeState(
        CameraExposureMode.fromValue(p.payload[0]), p.payload[1]);
  }

  @override
  String toString() => 'CameraExposureModeState(mode=$mode scene=$scene)';
}
