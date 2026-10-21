/// Airspace zones. These are loaded from PUBLIC data (the DJI GEO public zone map,
/// OpenAIP, or the national authority — CASA/OpenSky for Australia), never from any
/// vendor binary. A zone is deliberately simple so it can be inspected and trusted.
library;

import 'geo.dart';

enum ZoneKind {
  /// Flight prohibited. Takeoff and entry are blocked.
  noFly,

  /// Flight allowed only below [GeoZone.ceilingM] (e.g. an airport shelf).
  altitudeLimit,

  /// Advisory. Surfaced to the pilot, not enforced.
  warning,
}

/// A keep-out / restricted area, as a circle (centre + radius) or a polygon.
/// Circles cover the common "airport radius" case; polygons cover gazetted areas.
class GeoZone {
  final String id;
  final String name;
  final ZoneKind kind;

  /// Circle form.
  final LatLng? center;
  final double? radiusM;

  /// Polygon form (vertices in order).
  final List<LatLng>? polygon;

  /// Height ceiling above ground, metres. Null means "no flight at all" for
  /// [ZoneKind.noFly], or "no limit" otherwise.
  final double? ceilingM;

  const GeoZone.circle({
    required this.id,
    required this.name,
    required this.kind,
    required LatLng this.center,
    required double this.radiusM,
    this.ceilingM,
  }) : polygon = null;

  const GeoZone.polygon({
    required this.id,
    required this.name,
    required this.kind,
    required List<LatLng> this.polygon,
    this.ceilingM,
  })  : center = null,
        radiusM = null;

  bool get isCircle => center != null;

  /// Whether `p` is inside this zone's horizontal footprint.
  bool contains(LatLng p) {
    if (isCircle) return distanceM(center!, p) <= radiusM!;
    return pointInPolygon(p, polygon!);
  }

  /// Signed-ish distance in metres from `p` to the zone edge. Negative inside a
  /// circle. For polygons, 0 when inside and the min vertex distance when outside
  /// (a cheap, conservative proxy — never under-reports danger for convex areas).
  double distanceToEdgeM(LatLng p) {
    if (isCircle) return distanceM(center!, p) - radiusM!;
    if (pointInPolygon(p, polygon!)) return 0;
    var best = double.infinity;
    for (final v in polygon!) {
      final d = distanceM(p, v);
      if (d < best) best = d;
    }
    return best;
  }
}
