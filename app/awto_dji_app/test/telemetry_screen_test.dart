import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/safety/safety_gate.dart';
import 'package:awto_dji_app/safety/sample_zones.dart';
import 'package:awto_dji_app/transport/simulated_transport.dart';
import 'package:awto_dji_app/ui/telemetry_screen.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('dashboard shows simulated telemetry and link health', (tester) async {
    final sim = SimulatedAircraftTransport(tickInterval: null);
    final session = LinkSession(sim);
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: TelemetryScreen(session: session, gate: SafetyGate(sampleFence())))));

    await tester.runAsync(() async {
      await session.start();
      sim.emitTick();
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(find.textContaining('-33.8'), findsOneWidget); // latitude
    expect(find.text('Link health'), findsOneWidget);
    expect(find.textContaining('Transport / Health'), findsOneWidget);
    expect(find.textContaining(' / ok'), findsOneWidget);
    expect(find.textContaining('DUML Mbps'), findsOneWidget);
    expect(find.textContaining('Video Mbps'), findsOneWidget);

    await tester.runAsync(() async {
      await session.stop();
    });
    session.dispose();
  });
}
