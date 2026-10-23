import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/safety/safety_gate.dart';
import 'package:awto_dji_app/safety/sample_zones.dart';
import 'package:awto_dji_app/transport/simulated_transport.dart';
import 'package:awto_dji_app/ui/telemetry_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:geofence/geofence.dart';

void main() {
  testWidgets('dashboard shows simulated telemetry and gate state', (tester) async {
    final sim = SimulatedAircraftTransport(tickInterval: null);
    final session = LinkSession(sim);
    final gate = SafetyGate(sampleFence());
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(body: TelemetryScreen(session: session, gate: gate))));
    expect(find.text('NO FIX'), findsOneWidget);

    await tester.runAsync(() async {
      await session.start();
      sim.emitTick();
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(find.text('NO FIX'), findsNothing);
    expect(find.text('ALLOWED'), findsOneWidget);
    expect(find.textContaining('-33.8'), findsOneWidget); // latitude
    expect(find.text('Link health'), findsOneWidget);
    expect(find.text('ok'), findsOneWidget);

    await tester.runAsync(() async {
      await session.stop();
    });
    session.dispose();
  });

  test('gate blocks inside a no-fly zone, no fix without telemetry', () async {
    final gate = SafetyGate(GeoFence(const [
      GeoZone.circle(
          id: 'z',
          name: 'Zone',
          kind: ZoneKind.noFly,
          center: LatLng(-33.8688, 151.2093),
          radiusM: 500),
    ]));
    final sim = SimulatedAircraftTransport(tickInterval: null);
    final session = LinkSession(sim);
    expect(gate.evaluate(null).state, GateState.noFix);
    await session.start();
    sim.emitTick();
    await Future<void>.delayed(Duration.zero);
    final st = gate.evaluate(session.latestOsd);
    expect(st.state, GateState.blocked);
    expect(st.nearestZone!.id, 'z');
    await session.stop();
    session.dispose();
  });
}
