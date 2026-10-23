import 'package:geofence/geofence.dart';

/// SAMPLE zones for development only. Not authoritative airspace data; real zones
/// must come from public sources (see packages/geofence).
const sampleZones = <GeoZone>[
  GeoZone.circle(
    id: 'YSSY-core',
    name: 'Sydney Airport (sample)',
    kind: ZoneKind.noFly,
    center: LatLng(-33.9461, 151.1772),
    radiusM: 3000,
  ),
  // ~300 m east of the simulator home; the sim circle passes inside its buffer.
  GeoZone.circle(
    id: 'SIM-demo',
    name: 'Demo no-fly (sample)',
    kind: ZoneKind.noFly,
    center: LatLng(-33.8688, 151.21261),
    radiusM: 135,
  ),
];

GeoFence sampleFence() => GeoFence(sampleZones, bufferM: 30);
