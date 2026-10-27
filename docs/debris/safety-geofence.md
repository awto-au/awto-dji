# No-fly / altitude safety gate

The direct-control app enforces airspace restrictions itself, in `app/packages/geofence`.
Every control action is vetted here before it becomes a DUML command. This layer only
ever **adds** restrictions — it has no ability to remove one.

## Why not from DJI's binary

`libFlyForbid.so` is DJI's geofence *enforcement*. Reverse-engineering it is the same
knowledge whether you want to replicate or defeat the fence (the open-source
`dji_flyc_nofly_ed.py` uses exactly that understanding to *edit out* zones), so this
project does not touch it. We don't need to: no-fly enforcement is just public zone
data plus standard geometry, which is more transparent and trustworthy than mimicking
a vendor binary.

## Zone data (public sources)

Zones are loaded as plain `GeoZone` values from published airspace data, never scraped
from an app:

- **DJI GEO** public zone map (the same zones DJI publishes to pilots)
- **OpenAIP** (community airspace, worldwide)
- **National authority** — for Australia, CASA / OpenSky aerodrome data

A `GeoZone` is a circle (centre + radius, the common aerodrome case) or a polygon, with
an optional `ceilingM`. Because the data is plain and inspectable, you can see and
update exactly what the app enforces.

## Enforcement

`GeoFence` (with a configurable horizontal `bufferM`, default 30 m) exposes:

- `checkTakeoff(at)` — denies takeoff inside or within the buffer of a no-fly zone.
- `checkAltitude(at, requestedAltM)` — returns the lowest applicable ceiling and asks
  the caller to clamp a request above it.
- `checkVelocity(at, headingDeg, forward, right)` — a short look-ahead along the
  commanded course; denies motion that would carry the aircraft into (or deeper toward)
  a no-fly zone, while always allowing a stationary hold or a heading that increases
  clearance, so the pilot can always fly back out.

Each returns a `SafetyVerdict` of `allow` / `clamp` / `deny` with a human-readable
reason and the zones that triggered it, so the UI can explain *why* an action was
limited.

## How it wires into control

```
pilot input / autonomy
      │
   GeoFence.check*()   ── allow / clamp / deny (+ reason)
      │  (allow or clamped value only)
   DUML command  ──►  aircraft
```

The gate sits between intent and the DUML codec: a denied action never produces a
packet; a clamped altitude produces a packet with the reduced value. Tests in
`test/geofence_test.dart` cover takeoff blocking, ceiling clamping, and the
into-zone / out-of-zone velocity cases. Pure Dart, no native code.

## Honest limits

- Enforcement is only as current as the zone data loaded; wire a refresh against the
  chosen public source and fail safe (treat unknown/expired data conservatively).
- The velocity look-ahead is a simple kinematic projection; tune `bufferM` and the
  look-ahead horizon to the aircraft's braking distance at its max commanded speed.
- This complements, and does not replace, the pilot's legal responsibility for the
  airspace they fly in.
