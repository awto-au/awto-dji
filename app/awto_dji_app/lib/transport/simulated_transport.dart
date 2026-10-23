import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:geofence/geofence.dart';

import 'link_transport.dart';

/// Generates plausible OSD General pushes (a circular flight) with the duml
/// encoder, so the UI works without hardware. [tickInterval] null = manual
/// stepping via [emitTick] (tests).
class SimulatedAircraftTransport extends BaseTransport {
  SimulatedAircraftTransport({
    this.tickInterval = const Duration(milliseconds: 100),
    this.home = const LatLng(-33.8688, 151.2093),
    this.radiusM = 150,
    this.speedMps = 5,
    this.corruptEvery = 0,
  });

  final Duration? tickInterval;
  final LatLng home;
  final double radiusM;
  final double speedMps;

  /// Every Nth OSD frame gets a flipped CRC byte (0 = never), to exercise CRC counters.
  final int corruptEvery;

  static const _nominalDt = 0.1; // s, used when stepping manually
  Timer? _timer;
  int _tick = 0;
  int _seq = 0;

  @override
  String get name => 'simulated';

  int get ticks => _tick;

  @override
  Future<void> connect() async {
    setState(LinkState.connecting);
    setState(LinkState.connected);
    final iv = tickInterval;
    if (iv != null) _timer = Timer.periodic(iv, (_) => emitTick());
  }

  @override
  Future<void> disconnect() async {
    _timer?.cancel();
    _timer = null;
    if (currentState != LinkState.disconnected) {
      setState(LinkState.disconnected);
    }
  }

  /// Emits one OSD General frame (plus a version reply every 20th tick).
  void emitTick() {
    final dt = tickInterval == null
        ? _nominalDt
        : tickInterval!.inMicroseconds / 1e6;
    final t = _tick * dt;
    _tick++;

    final angVel = speedMps / radiusM; // rad/s
    final thetaDeg = (angVel * t) * 180 / math.pi;
    final pos = destination(home, thetaDeg % 360, radiusM);
    final course = (thetaDeg + 90) % 360; // tangent, clockwise
    final cr = course * math.pi / 180;

    final payload = Uint8List(60);
    final d = ByteData.sublistView(payload);
    const radPerDeg = math.pi / 180;
    d.setFloat64(0, pos.lon * radPerDeg, Endian.little);
    d.setFloat64(8, pos.lat * radPerDeg, Endian.little);
    int dm(double v) => (v * 10).round();
    d.setInt16(16, dm(40 + 10 * math.sin(t / 10)), Endian.little);
    d.setInt16(18, dm(speedMps * math.cos(cr)), Endian.little); // north
    d.setInt16(20, dm(speedMps * math.sin(cr)), Endian.little); // east
    d.setInt16(22, dm(math.cos(t / 10)), Endian.little);
    d.setInt16(24, dm(3 * math.sin(t / 3)), Endian.little); // pitch
    d.setInt16(26, dm(5 * math.cos(t / 5)), Endian.little); // roll
    d.setInt16(28, dm(course > 180 ? course - 360 : course), Endian.little);

    final bytes = _packet(OsdGeneral.cmdSet, OsdGeneral.cmdId, payload);
    if (corruptEvery > 0 && _tick % corruptEvery == 0) {
      bytes[bytes.length - 1] ^= 0xFF;
    }
    emit(bytes);

    if ((_tick - 1) % 20 == 0) {
      emit(_packet(CmdSet.general, 0x01,
          Uint8List.fromList('SIM-P3P'.codeUnits)));
    }
  }

  Uint8List _packet(int set, int id, Uint8List payload) => DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        sequence: _seq++ & 0xFFFF,
        cmdSet: set,
        cmdId: id,
        payload: payload,
      ).encode();
}
