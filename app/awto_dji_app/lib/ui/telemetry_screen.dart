import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../safety/safety_gate.dart';
import '../transport/link_transport.dart';

class TelemetryScreen extends StatelessWidget {
  const TelemetryScreen({super.key, required this.session, required this.gate});
  final LinkSession session;
  final SafetyGate gate;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: session,
      builder: (context, _) {
        final osd = session.latestOsd;
        final safety = gate.evaluate(osd);
        final gs = osd == null ? null : math.sqrt(osd.vgx * osd.vgx + osd.vgy * osd.vgy);
        return ListView(
          padding: const EdgeInsets.all(12),
          children: [
            _SafetyCard(safety: safety, gate: gate),
            _card('Position', [
              _row('Latitude', osd == null ? '-' : osd.latitude.toStringAsFixed(6)),
              _row('Longitude', osd == null ? '-' : osd.longitude.toStringAsFixed(6)),
            ]),
            _card('Altitude and speed', [
              _row('Height above home', osd == null ? '-' : '${osd.relativeHeight.toStringAsFixed(1)} m'),
              _row('Ground speed', gs == null ? '-' : '${gs.toStringAsFixed(1)} m/s'),
              _row('Vertical speed', osd == null ? '-' : '${osd.vgz.toStringAsFixed(1)} m/s'),
            ]),
            _card('Attitude', [
              _row('Pitch', osd == null ? '-' : '${osd.pitch.toStringAsFixed(1)} deg'),
              _row('Roll', osd == null ? '-' : '${osd.roll.toStringAsFixed(1)} deg'),
              _row('Yaw', osd == null ? '-' : '${osd.yaw.toStringAsFixed(1)} deg'),
            ]),
            _LinkCard(session: session),
          ],
        );
      },
    );
  }
}

Widget _row(String k, String v) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [Text(k), Text(v, style: const TextStyle(fontFeatures: [FontFeature.tabularFigures()]))],
      ),
    );

Widget _card(String title, List<Widget> rows) => Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ...rows,
          ],
        ),
      ),
    );

class _LinkCard extends StatelessWidget {
  const _LinkCard({required this.session});
  final LinkSession session;

  @override
  Widget build(BuildContext context) {
    final now = DateTime.now();
    final last = session.lastPacketAt;
    final age = last == null ? '-' : '${now.difference(last).inMilliseconds} ms ago';
    return _card('Link health', [
      _row('Transport', '${session.transport.name} (${session.linkState.name})'),
      _row('Health', session.health.name),
      _row('Packets', '${session.packetCount}  (${session.packetsPerSecond(now).toStringAsFixed(0)}/s)'),
      _row('CRC errors', '${session.crcErrorCount}'),
      _row('Last packet', age),
      if (session.transport.currentState == LinkState.failed)
        _row('Error', session.transport.lastError ?? ''),
    ]);
  }
}

class _SafetyCard extends StatelessWidget {
  const _SafetyCard({required this.safety, required this.gate});
  final SafetyStatus safety;
  final SafetyGate gate;

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final (label, color) = switch (safety.state) {
      GateState.noFix => ('NO FIX', cs.outline),
      GateState.allowed => ('ALLOWED', Colors.green),
      GateState.limited => ('LIMITED', Colors.orange),
      GateState.blocked => ('BLOCKED', cs.error),
    };
    final z = safety.nearestZone;
    final d = safety.nearestDistanceM;
    return Card(
      key: const Key('safety-card'),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              const Text('Geofence gate', style: TextStyle(fontWeight: FontWeight.bold)),
              const Spacer(),
              Chip(
                label: Text(label, key: const Key('gate-state')),
                backgroundColor: color.withValues(alpha: 0.2),
                side: BorderSide(color: color),
              ),
            ]),
            Text(safety.reason),
            if (z != null && d != null)
              _row('Nearest zone', '${z.name}, ${d.toStringAsFixed(0)} m to edge'),
            _row('Zones loaded', '${gate.zones.length} (sample data, not airspace authority)'),
          ],
        ),
      ),
    );
  }
}
