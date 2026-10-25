/// The safety gate. Every control action is run through this before it is turned
/// into a DUML command, so the app refuses — or limits — flight where airspace
/// rules say it must. This makes the direct-control app *safer*; it never removes a
/// restriction.
library;

import 'dart:math' as math;

import 'geo.dart';
import 'zones.dart';

enum Decision { allow, clamp, deny }

class SafetyVerdict {
  final Decision decision;
  final String reason;

  /// For [Decision.clamp] of an altitude request: the permitted ceiling, metres.
  final double? allowedCeilingM;

  /// Zones that triggered this verdict.
  final List<GeoZone> zones;

  const SafetyVerdict(this.decision, this.reason,
      {this.allowedCeilingM, this.zones = const []});

  bool get isAllowed => decision != Decision.deny;

  @override
  String toString() => '$decision: $reason'
      '${allowedCeilingM != null ? ' (ceiling ${allowedCeilingM!.toStringAsFixed(0)} m)' : ''}';
}

class GeoFence {
  final List<GeoZone> zones;

  /// Horizontal safety buffer, metres. The fence treats a point within this
  /// distance of a no-fly edge as if it were inside, and blocks movement toward it.
  final double bufferM;

  GeoFence(this.zones, {this.bufferM = 30.0});

  List<GeoZone> _noFlyContaining(LatLng p) => zones
      .where((z) => z.kind == ZoneKind.noFly && z.distanceToEdgeM(p) <= bufferM)
      .toList();

  List<GeoZone> _altLimitsAt(LatLng p) => zones
      .where((z) => z.kind == ZoneKind.altitudeLimit && z.contains(p))
      .toList();

  /// May the aircraft take off from here?
  SafetyVerdict checkTakeoff(LatLng at) {
    final blocking = _noFlyContaining(at);
    if (blocking.isNotEmpty) {
      return SafetyVerdict(Decision.deny,
          'takeoff inside/near no-fly zone: ${blocking.map((z) => z.name).join(", ")}',
          zones: blocking);
    }
    return const SafetyVerdict(Decision.allow, 'clear for takeoff');
  }

  /// The ceiling that applies at `at`: the lowest altitude-limit ceiling, or null if
  /// none. A requested altitude above it should be clamped down.
  SafetyVerdict checkAltitude(LatLng at, double requestedAltM) {
    final limits = _altLimitsAt(at).where((z) => z.ceilingM != null).toList();
    if (limits.isEmpty)
      return const SafetyVerdict(Decision.allow, 'no altitude limit here');
    final ceiling =
        limits.map((z) => z.ceilingM!).reduce((a, b) => a < b ? a : b);
    if (requestedAltM <= ceiling) {
      return SafetyVerdict(Decision.allow, 'within ceiling',
          allowedCeilingM: ceiling, zones: limits);
    }
    return SafetyVerdict(Decision.clamp,
        'altitude limited to ${ceiling.toStringAsFixed(0)} m by ${limits.map((z) => z.name).join(", ")}',
        allowedCeilingM: ceiling, zones: limits);
  }

  /// May the aircraft hold a horizontal velocity here? Denies if a short look-ahead
  /// at the commanded heading/speed would carry it into (or deeper toward) a no-fly
  /// zone. Zero/receding velocity is always allowed so the pilot can fly away.
  ///
  /// `forward`/`right` are body-frame m/s; `headingDeg` is the aircraft heading.
  SafetyVerdict checkVelocity(
      LatLng at, double headingDeg, double forward, double right,
      {double lookaheadS = 2.0}) {
    final speed = math.sqrt(forward * forward + right * right);
    if (speed < 0.05) return const SafetyVerdict(Decision.allow, 'stationary');

    final courseOffset = math.atan2(right, forward) * 180.0 / math.pi;
    final course = (headingDeg + courseOffset + 360) % 360;
    final ahead = destination(at, course, speed * lookaheadS);

    final hereBlock = _noFlyContaining(at);
    final aheadBlock = _noFlyContaining(ahead);
    if (aheadBlock.isEmpty) {
      return const SafetyVerdict(Decision.allow, 'path clear');
    }
    // Already near a no-fly: allow only if the move increases clearance (flying out).
    for (final z in aheadBlock) {
      final dNow = z.distanceToEdgeM(at);
      final dAhead = z.distanceToEdgeM(ahead);
      if (hereBlock.contains(z) && dAhead > dNow) {
        continue; // receding from this zone — fine
      }
      return SafetyVerdict(Decision.deny,
          'heading into no-fly zone ${z.name} in ${lookaheadS.toStringAsFixed(0)}s',
          zones: [z]);
    }
    return const SafetyVerdict(Decision.allow, 'receding from zone');
  }
}
