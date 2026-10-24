import 'package:geofence/geofence.dart';
import 'package:test/test.dart';

void main() {
  // A no-fly circle (e.g. an aerodrome), and an altitude shelf around it.
  final airport = const LatLng(-33.9461, 151.1772); // Sydney Airport
  final noFly = GeoZone.circle(
    id: 'YSSY-core',
    name: 'Sydney Airport',
    kind: ZoneKind.noFly,
    center: airport,
    radiusM: 3000,
  );
  final shelf = GeoZone.circle(
    id: 'YSSY-shelf',
    name: 'Sydney shelf',
    kind: ZoneKind.altitudeLimit,
    center: airport,
    radiusM: 8000,
    ceilingM: 45,
  );
  final fence = GeoFence([noFly, shelf], bufferM: 50);

  final farAway = const LatLng(-33.8688, 151.2093); // ~9 km NE, outside both

  group('geometry', () {
    test('distance and destination round-trip', () {
      final p = destination(farAway, 90, 1000); // 1 km east
      expect(distanceM(farAway, p), closeTo(1000, 1));
      expect(bearingDeg(farAway, p), closeTo(90, 0.5));
    });

    test('point in polygon', () {
      final square = const [
        LatLng(0, 0), LatLng(0, 1), LatLng(1, 1), LatLng(1, 0),
      ];
      expect(pointInPolygon(const LatLng(0.5, 0.5), square), isTrue);
      expect(pointInPolygon(const LatLng(2, 2), square), isFalse);
    });
  });

  group('takeoff', () {
    test('blocked inside a no-fly zone', () {
      final v = fence.checkTakeoff(airport);
      expect(v.decision, Decision.deny);
      expect(v.zones.single.id, 'YSSY-core');
    });

    test('allowed well clear', () {
      expect(fence.checkTakeoff(farAway).decision, Decision.allow);
    });
  });

  group('altitude', () {
    test('clamped under a shelf ceiling', () {
      final onShelf = destination(airport, 0, 5000); // inside 8 km shelf, outside 3 km core
      final v = fence.checkAltitude(onShelf, 120);
      expect(v.decision, Decision.clamp);
      expect(v.allowedCeilingM, 45);
    });

    test('unrestricted outside any shelf', () {
      expect(fence.checkAltitude(farAway, 120).decision, Decision.allow);
    });
  });

  group('velocity look-ahead', () {
    // ~3.04 km due north of the airport centre: 40 m past the 3 km edge, i.e. inside
    // the 50 m safety buffer, where the fence must judge intent by direction.
    final nearEdge = destination(airport, 0, 3040);

    test('denied when heading into the zone', () {
      // Facing south (heading 180), full forward -> toward the airport centre.
      final v = fence.checkVelocity(nearEdge, 180, 5.0, 0.0);
      expect(v.decision, Decision.deny);
    });

    test('allowed when flying away from the zone', () {
      // Facing north (heading 0), forward -> away from the airport.
      final v = fence.checkVelocity(nearEdge, 0, 5.0, 0.0);
      expect(v.decision, Decision.allow);
    });

    test('stationary is always allowed', () {
      expect(fence.checkVelocity(nearEdge, 180, 0.0, 0.0).decision, Decision.allow);
    });
  });
}
