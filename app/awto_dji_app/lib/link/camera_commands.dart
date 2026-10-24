import 'dart:typed_data';

import 'package:duml/duml.dart';

/// Camera exposure control: AE lock + EV compensation + exposure mode (cmdset
/// 0x02 "CAMERA"). Payload layouts reversed from the decompiled vendor app's own
/// UI call sites, not guessed from `scripts/re/duml_catalog.py` names alone (see
/// awto-dji#38 and this project's gimbal-command precedent, awto-dji#37). Decoders
/// for the Get* replies live in `package:duml` (`camera_exposure.dart`).
///
/// Both `tmp/apk/dynamic` (dji.go.v4) and `tmp/apk/pilot_dynamic` (DJI Pilot)
/// carry byte-identical `dji.midware.data.model.P3.DataCameraSet{AELock,
/// ExposureMode}` classes and the same `dji.pilot.fpv.camera.setting`/`topbar` UI
/// package names - see awto-dji#30 on which APK tree is the "correct" one for a
/// P3 Pro; this cross-tree agreement is independent corroboration of the raw wire
/// format regardless of that answer. `DataCameraSetEV` (exposure compensation)
/// was found only in `pilot_dynamic`.
class CameraCommands {
  CameraCommands([this._seq = 0x6c00]);
  int _seq;

  Uint8List _request(int cmdId, Uint8List payload) => DumlPacket(
        senderType: DeviceType.app,
        receiverType: DeviceType.camera,
        sequence: _seq++,
        ackType: AckType.afterExec,
        cmdSet: CmdSet.camera,
        cmdId: cmdId,
        payload: payload,
      ).encode();

  /// CAMERA/0x68 (SetAELock). `DataCameraSetAELock.doPack()`: 1-byte payload,
  /// 1 = lock, 0 = unlock. Real toggle: `DJIFpvTopBaseView.l()` -
  /// `DataCameraSetAELock.getInstance().a(!this.xI).start(...)`, bound to view id
  /// 2131298860 ("FPV_RightBarView_CameraControllView_Button_AELock").
  Uint8List setAeLock(bool locked) =>
      _request(0x68, Uint8List.fromList([locked ? 1 : 0]));

  /// CAMERA/0x69 (GetAELock). Empty request payload, mirroring
  /// `DataCameraGetAELock.doPack()` (leaves `_sendData` unset).
  Uint8List getAeLock() => _request(0x69, Uint8List(0));

  /// CAMERA/0x2e (SetExposureCompensation). `DataCameraSetEV.doPack()`: 1-byte
  /// payload, raw step 1..31 (1/3-EV units, 16 = 0.0 EV) - the real +/-/reset
  /// buttons (`DJICameraSettingBaseView$1`, tracked events
  /// "FPV_LeftBarView_CameraAdvancedView_Button_EvAdd/EvSub/EvReset") step an
  /// index over exactly this range. [ev] is clamped to -5.0..+5.0 and rounded to
  /// the nearest 1/3 stop; range/step confirmed against the public SDK enum
  /// `dji.common.camera.DJICameraSettingsDef$CameraExposureCompensation`
  /// (N_5_0=1 .. N_0_0=16 .. P_5_0=31).
  Uint8List setExposureCompensation(double ev) {
    final clamped = ev.clamp(-5.0, 5.0);
    final raw = (16 + (clamped * 3).round()).clamp(1, 31);
    return _request(0x2e, Uint8List.fromList([raw]));
  }

  /// CAMERA/0x2f (GetExposureCompensation). Empty request payload - no dedicated
  /// Get class was decompiled (see `camera_exposure.dart` doc comment), assumed
  /// empty like every other Get in this cmdset that was decompiled (GetAELock,
  /// GetVersion) **(I)**.
  Uint8List getExposureCompensation() => _request(0x2f, Uint8List(0));

  /// CAMERA/0x1e (SetExposureMode). `DataCameraSetExposureMode.doPack()`: 2-byte
  /// payload, byte0 = mode, byte1 = scene index, only sent/meaningful when
  /// `mode == CameraExposureMode.scn`.
  Uint8List setExposureMode(CameraExposureMode mode, {int scene = 0}) {
    final payload = Uint8List(2);
    payload[0] = mode.value;
    if (mode == CameraExposureMode.scn) payload[1] = scene;
    return _request(0x1e, payload);
  }

  /// CAMERA/0x1f (GetExposureMode). Empty request payload **(I)**, same basis as
  /// [getExposureCompensation].
  Uint8List getExposureMode() => _request(0x1f, Uint8List(0));
}
