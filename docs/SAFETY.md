# Safety, scope & regulatory — the single source

All safety, flight-gating, geofence/NFZ, RF-power and repair-scope rules live here. Technical docs
must **not** repeat them; they link here. Keep this doc current; put fact-changes in `HISTORY.md`.

## Default posture

- Bench work, **props off**, on the owner's own aircraft (dan@awto.au). Nothing here authorises flight.
- A change is bench-only until it has passed the staged bring-up (below). No exceptions in a tech doc.

## Out of scope (hard lines)

- **No geofence / no-fly-zone defeat.** The `packages/geofence` gate is a safety *limiter*, not a
  bypass. `FlyForbid` is not reverse-engineered for circumvention.
- **No RF region/TX-power unlock** (that lives on the radio modules, not the FC).
- **No DJI activation/licensing circumvention.** Activation is satisfied by DJI's normal flow.
- Component-auth (ATSHA204) work is **repair of owned hardware with a failed chip only** — it is
  anti-counterfeit parts-pairing, not a safety or regulatory control. Dual-use caveat: a stub also
  passes a non-genuine part; the intent is a dead chip on a board you own.

## Autonomy (driving the stock FC) — safety model

1. **Hard watchdog.** Offboard/virtual-stick control is a continuous stream the FC times out. If the
   loop, geofence or telemetry stalls, **stop sending** and let the FC's own timeout failsafe take
   over. Never resend a last-good setpoint on error.
2. **Characterise the FC command-timeout empirically** (bench, props off, motors disabled) before
   relying on it. Gates everything.
3. **Authority is explicit and revocable.** Enter external-control only via the verified handshake;
   a physical RC input must always be able to take control back. Confirm RC override every test.
4. **Geofence precheck on every frame.** No setpoint breaching zone/altitude/velocity is emitted;
   clamp independently of mission bugs.
5. **Staged bring-up:** props off → motors disabled → tethered → open field, with failsafe +
   override + geofence proven at each gate.

## Bench instruments & firmware patches (read-mem, hooks, replacement/patch app)

- Diagnostics (read-any-memory, FPB/DebugMonitor hooks, bootloader dump) are **comms/memory only**:
  no motor/ESC init, no control loop, never on a flying aircraft.
- **Never hook a control-loop function**, and never with props on — a DebugMonitor hook adds latency.
- Keep the stock m0306 image to reflash via DJI Assistant; the loader (sectors 0–4) is preserved, so
  a bad app is recoverable.

## Geofence / no-fly gate (`app/packages/geofence`)

The app enforces airspace limits itself, before intent becomes a DUML command. This layer only
ever **adds** restrictions; it cannot remove one.

- **Not from DJI's binary.** `libFlyForbid.so` is DJI's enforcement; RE'ing it is the same
  knowledge whether to replicate or defeat a fence, so this project does not touch it. No-fly is
  public zone data + standard geometry instead — more transparent than mimicking a vendor binary.
- **Zone data** (public, inspectable, never scraped): DJI GEO public map, OpenAIP, national
  authority (AU: CASA/OpenSky). A `GeoZone` is a circle or polygon with optional `ceilingM`.
- **Gate API.** `GeoFence` (horizontal `bufferM`, default 30 m): `checkTakeoff(at)`,
  `checkAltitude(at, reqAltM)` (lowest ceiling, caller clamps), `checkVelocity(...)` (course
  look-ahead; denies motion deeper into a zone, always allows a hold or an outbound heading).
  Each returns `allow`/`clamp`/`deny` + reason + triggering zones. Denied → no packet; clamped →
  reduced-value packet. Pure Dart; tests in `test/geofence_test.dart`.
- **Limits.** Only as current as the zone data loaded (fail safe on unknown/expired); the
  look-ahead is a simple kinematic projection (tune `bufferM` to braking distance); complements,
  never replaces, the pilot's legal responsibility for the airspace.

## Honesty convention

Separate **verified / inferred / needs-tooling** (V/I/U). Do not restate inference as proof. Cite
offsets/repro so claims can be re-derived. (This convention is enforced across all docs; see
`CLAUDE.md`.)
