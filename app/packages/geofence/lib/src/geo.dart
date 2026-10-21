/// Small WGS-84 geometry helpers for geofencing. Spherical-earth approximations,
/// accurate to well within the metre-scale tolerances a drone safety buffer needs.
library;

import 'dart:math' as math;

const double _earthRadiusM = 6378137.0;

double _rad(double deg) => deg * math.pi / 180.0;
double _deg(double rad) => rad * 180.0 / math.pi;

class LatLng {
  final double lat; // degrees
  final double lon; // degrees
  const LatLng(this.lat, this.lon);

  @override
  String toString() => '(${lat.toStringAsFixed(6)}, ${lon.toStringAsFixed(6)})';
}

/// Great-circle distance in metres (haversine).
double distanceM(LatLng a, LatLng b) {
  final dLat = _rad(b.lat - a.lat);
  final dLon = _rad(b.lon - a.lon);
  final sa = math.sin(dLat / 2);
  final so = math.sin(dLon / 2);
  final h = sa * sa + math.cos(_rad(a.lat)) * math.cos(_rad(b.lat)) * so * so;
  return 2 * _earthRadiusM * math.asin(math.min(1.0, math.sqrt(h)));
}

/// Initial bearing from `a` to `b`, degrees clockwise from north [0, 360).
double bearingDeg(LatLng a, LatLng b) {
  final dLon = _rad(b.lon - a.lon);
  final y = math.sin(dLon) * math.cos(_rad(b.lat));
  final x = math.cos(_rad(a.lat)) * math.sin(_rad(b.lat)) -
      math.sin(_rad(a.lat)) * math.cos(_rad(b.lat)) * math.cos(dLon);
  return (_deg(math.atan2(y, x)) + 360) % 360;
}

/// Point reached from `start` after `distance` metres on `bearing` degrees.
LatLng destination(LatLng start, double bearingDegrees, double distanceM) {
  final d = distanceM / _earthRadiusM;
  final br = _rad(bearingDegrees);
  final lat1 = _rad(start.lat);
  final lon1 = _rad(start.lon);
  final lat2 = math.asin(
      math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br));
  final lon2 = lon1 +
      math.atan2(math.sin(br) * math.sin(d) * math.cos(lat1),
          math.cos(d) - math.sin(lat1) * math.sin(lat2));
  return LatLng(_deg(lat2), (_deg(lon2) + 540) % 360 - 180);
}

/// True if `p` is inside the polygon `ring` (list of vertices, not necessarily
/// closed), by ray casting. Treats the edge as inside-ish; good enough as a
/// conservative keep-out test.
bool pointInPolygon(LatLng p, List<LatLng> ring) {
  var inside = false;
  final n = ring.length;
  for (var i = 0, j = n - 1; i < n; j = i++) {
    final yi = ring[i].lat, xi = ring[i].lon;
    final yj = ring[j].lat, xj = ring[j].lon;
    final intersect = ((yi > p.lat) != (yj > p.lat)) &&
        (p.lon < (xj - xi) * (p.lat - yi) / ((yj - yi) == 0 ? 1e-12 : (yj - yi)) + xi);
    if (intersect) inside = !inside;
  }
  return inside;
}
