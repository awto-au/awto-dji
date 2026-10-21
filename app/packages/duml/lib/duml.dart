/// Pure-Dart DUML codec: the DJI phone↔aircraft wire format, with no Flutter or
/// native dependencies, so it runs anywhere Dart runs and is unit-testable off-device.
///
/// This is interoperability work for aircraft the operator owns. It does not defeat
/// any DJI protection, and it is not a substitute for the operator's own
/// responsibility for airspace rules, geofencing and safe flight.
library duml;

export 'src/crc.dart';
export 'src/packet.dart';
export 'src/telemetry.dart';
