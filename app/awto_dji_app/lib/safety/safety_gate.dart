import 'package:duml/duml.dart';
import 'package:geofence/geofence.dart';

enum GateState { noFix, allowed, limited, blocked }

/// Display-only view of the geofence gate for the current position. There is no
/// override: the gate only reports, and any future control path must pass it.
class SafetyStatus {
  const SafetyStatus(this.state, this.reason,
      {this.position, this.nearestZone, this.nearestDistanceM, this.verdicts = const []});
  final GateState state;
  final String reason;
  final LatLng? position;
  final GeoZone? nearestZone;

  /// Metres to the nearest zone edge (negative = inside a circle).
  final double? nearestDistanceM;
  final List<SafetyVerdict> verdicts;
}

class SafetyGate {
  SafetyGate(this.fence);
  final GeoFence fence;

  List<GeoZone> get zones => fence.zones;

  SafetyStatus evaluate(OsdGeneral? osd) {
    if (osd == null || (osd.latitude == 0 && osd.longitude == 0)) {
      return const SafetyStatus(GateState.noFix, 'no position fix');
    }
    final pos = LatLng(osd.latitude, osd.longitude);
    GeoZone? nearest;
    double? nearestD;
    for (final z in zones) {
      final d = z.distanceToEdgeM(pos);
      if (nearestD == null || d < nearestD) {
        nearest = z;
        nearestD = d;
      }
    }
    final place = fence.checkTakeoff(pos); // no-fly proximity at this position
    final alt = fence.checkAltitude(pos, osd.relativeHeight);
    final verdicts = [place, alt];
    final GateState state;
    final String reason;
    if (place.decision == Decision.deny) {
      state = GateState.blocked;
      reason = place.reason;
    } else if (alt.decision == Decision.clamp) {
      state = GateState.limited;
      reason = alt.reason;
    } else {
      state = GateState.allowed;
      reason = 'clear of mapped zones';
    }
    return SafetyStatus(state, reason,
        position: pos,
        nearestZone: nearest,
        nearestDistanceM: nearestD,
        verdicts: verdicts);
  }
}
