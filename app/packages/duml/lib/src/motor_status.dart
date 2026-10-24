/// Enums decoded from the OSD General push (`DataOsdGetPushCommon`, see
/// `telemetry.dart`), ported field-for-field from the real
/// `dji.midware.data.model.P3.DataOsdGetPushCommon` decompile (dji.go.v4, found under
/// `tmp/apk/dynamic/decompiled/sources/...`, gitignored - not in this repo).
///
/// V (byte-for-byte port of the real `enum` values/ranges); live semantics (which of
/// these actually fire on a real P3P) not yet confirmed - see awto-dji#16.
library;

/// `MotorStartFailedCause` - why the motors refuse to arm, or a running-state fault.
/// Covers compass/IMU/battery/ESC errors, calibration-in-progress, and gimbal health
/// (`gimbalDisorder`/`gimbalPitchShock`/etc - these also serve as a coarse "gimbal
/// health" readout even outside a motor-arm attempt). `remoteUsbConnected` covers the
/// 200-255 range, matching the real class's `REMOTE_USB_CONNECTED(200, 255)`.
///
/// Original Java names/spelling (including its typos, e.g. `seriouLowVoltage`,
/// `cyroAbnormal`) are kept so this stays grep-able against the decompile.
enum MotorStartFailedCause {
  none(0),
  compassError(1),
  assistantProtected(2),
  deviceLocked(3),
  distanceLimit(4),
  imuNeedCalibration(5),
  imuSnError(6),
  imuWarning(7),
  compassCalibrating(8),
  attiError(9),
  noviceProtected(10),
  batteryCellError(11),
  batteryCommuniteError(12),
  seriouLowVoltage(13),
  seriouLowPower(14),
  lowVoltage(15),
  tempureVolLow(16),
  smartLowToLand(17),
  batteryNotReady(18),
  simulatorMode(19),
  packMode(20),
  attitudeAbNormal(21),
  unActive(22),
  flyForbiddenError(23),
  biasError(24),
  escError(25),
  imuInitError(26),
  systemUpgrade(27),
  simulatorStarted(28),
  imuingError(29),
  attiAngleOver(30),
  gyroscopeError(31),
  acceletorError(32),
  compassFailed(33),
  barometerError(34),
  barometerNegative(35),
  compassBig(36),
  gyroscopeBiasBig(37),
  acceletorBiasBig(38),
  compassNoiseBig(39),
  barometerNoiseBig(40),
  invalidSn(41),
  flashOperating(44),
  gpsDisconnect(45),
  sdCardException(47),
  imuNoconnection(61),
  rcCalibration(62),
  rcCalibrationException(63),
  rcCalibrationUnfinished(64),
  rcCalibrationException2(65),
  rcCalibrationException3(66),
  aircraftTypeMismatch(67),
  foundUnfinishedModule(68),
  cyroAbnormal(70),
  baroAbnormal(71),
  compassAbnormal(72),
  gpsAbnormal(73),
  nsAbnormal(74),
  topologyAbnormal(75),
  rcNeedCali(76),
  invalidFloat(77),
  m600BatTooLittle(78),
  m600BatAuthErr(79),
  m600BatCommErr(80),
  m600BatDifVoltLarge1(81),
  m600BatDifVoltLarge2(82),
  invalidVersion(83),
  gimbalGyroAbnormal(84),
  gimbalEscPitchNonData(85),
  gimbalEscRollNonData(86),
  gimbalEscYawNonData(87),
  gimbalFirmIsUpdating(88),
  gimbalDisorder(89),
  gimbalPitchShock(90),
  gimbalRollShock(91),
  gimbalYawShock(92),
  imuCalibrationFinished(93),
  takeoffRollover(94),
  motorStuck(95),
  motorUnbalanced(96),
  motorLessPaddle(97),
  motorStartError(98),
  motorAutoTakeoffFail(99),
  batVersionError(101),
  rtkBadSignal(102),
  rtkDeviationError(103),
  escCalibrating(112),
  gpsSignInvalid(113),
  gimbalIsCalibrating(114),
  lockByApp(115),
  startFlyHeightError(116),
  escVersionNotMatch(117),
  imuOriNotMatch(118),
  stopByApp(119),
  compassImuOriNotMatch(120),
  escEchoing(122),
  batteryOverTemperature(123),
  batteryInstallError(124),
  beImpact(125),
  crash(127),
  lowVersionOfBattery(129),
  voltageOfBatteryIsTooHigh(130),
  batteryEmbedError(131),
  coolingFanException(132),
  rcThrottleIsNotInMiddle(136),
  ridParseOperatiorPosFailed(180),
  remoteUsbConnected(200, 255),
  other(-1, -1);

  const MotorStartFailedCause(this.min, [int? max]) : max = max ?? min;
  final int min;
  final int max;

  static MotorStartFailedCause find(int value) {
    for (final c in MotorStartFailedCause.values) {
      if (c != other && value >= c.min && value <= c.max) return c;
    }
    return other;
  }
}

/// `IMU_INITFAIL_REASON` - why IMU init/preflight checks have not passed, including
/// calibration-in-progress (`colletingData`) and the resting/at-rest states checked
/// before an on-ground calibration is allowed to start. Spelling kept from source.
enum ImuInitFailReason {
  monitorError(0),
  colletingData(1),
  gyroDead(2),
  acceDead(3),
  compassDead(4),
  barometerDead(5),
  barometerNegative(6),
  compassModTooLarge(7),
  gyroBiasTooLarge(8),
  acceBiasTooLarge(9),
  compassNoiseTooLarge(10),
  barometerNoiseTooLarge(11),
  waitingMcStationary(12),
  acceMoveTooLarge(13),
  mcHeaderMoved(14),
  mcVirbrated(15),
  none(100);

  const ImuInitFailReason(this.value);
  final int value;

  static ImuInitFailReason find(int value) {
    for (final r in ImuInitFailReason.values) {
      if (r.value == value) return r;
    }
    return none;
  }
}
