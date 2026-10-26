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
            _compactCard(
              context,
              'Position',
              [
                ('Lat', osd == null ? '-' : osd.latitude.toStringAsFixed(6)),
                ('Lon', osd == null ? '-' : osd.longitude.toStringAsFixed(6)),
                ('Alt', osd == null ? '-' : '${osd.relativeHeight.toStringAsFixed(1)} m'),
                ('GS', gs == null ? '-' : '${gs.toStringAsFixed(1)} m/s'),
                ('VS', osd == null ? '-' : '${osd.vgz.toStringAsFixed(1)} m/s'),
                ('Pitch', osd == null ? '-' : '${osd.pitch.toStringAsFixed(1)} deg'),
                ('Roll', osd == null ? '-' : '${osd.roll.toStringAsFixed(1)} deg'),
                ('Yaw', osd == null ? '-' : '${osd.yaw.toStringAsFixed(1)} deg'),
              ],
              key: const Key('safety-card'),
              trailing: _gateBadge(context, safety),
            ),
            _card('RC signal', [
              _row('Quality', session.latestSignal == null
                  ? '-' : '${session.latestSignal!.aggregateQuality}/127 '
                      '(${session.latestSignal!.qualityPercent.toStringAsFixed(0)}%)'),
              _row('Direction', session.latestSignal == null
                  ? '-' : session.latestSignal!.isUplink ? 'Up' : 'Down'),
              _row('Antenna 1', session.latestSignal == null
                  ? '-' : '${session.latestSignal!.antenna1Dbm} dBm'),
              _row('Antenna 2', session.latestSignal == null
                  ? '-' : '${session.latestSignal!.antenna2Dbm} dBm'),
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

/// Small geofence status badge; the reason (and sample-data note) is in the tooltip.
Widget _gateBadge(BuildContext context, SafetyStatus safety) {
  final cs = Theme.of(context).colorScheme;
  final (label, color) = switch (safety.state) {
    GateState.noFix => ('NO FIX', cs.outline),
    GateState.allowed => ('ALLOWED', Colors.green),
    GateState.limited => ('LIMITED', Colors.orange),
    GateState.blocked => ('BLOCKED', cs.error),
  };
  return Tooltip(
    message: '${safety.reason}\nZones are sample data, not airspace authority.',
    child: Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.2),
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(label,
          key: const Key('gate-state'), style: Theme.of(context).textTheme.labelSmall),
    ),
  );
}

/// One small tile: label/value pairs flowing on shared lines, optional badge beside the title.
Widget _compactCard(BuildContext context, String title, List<(String, String)> items,
    {Key? key, Widget? trailing}) {
  final small = Theme.of(context).textTheme.bodySmall;
  return Card(
    key: key,
    child: Padding(
      padding: const EdgeInsets.all(8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(children: [
            Text(title, style: small?.copyWith(fontWeight: FontWeight.bold)),
            const Spacer(),
            ?trailing,
          ]),
          const SizedBox(height: 2),
          Wrap(
            spacing: 14,
            runSpacing: 2,
            children: [
              for (final (k, v) in items)
                Text('$k $v',
                    style: small?.copyWith(fontFeatures: const [FontFeature.tabularFigures()])),
            ],
          ),
        ],
      ),
    ),
  );
}

String _size(int b) => b < 1024
    ? '$b B'
    : b < 1024 * 1024
        ? '${(b / 1024).toStringAsFixed(1)} KB'
        : '${(b / (1024 * 1024)).toStringAsFixed(2)} MB';

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
    final windows = [
      session.gapStats(const Duration(seconds: 1), now),
      session.gapStats(const Duration(seconds: 5), now),
      session.gapStats(const Duration(minutes: 1), now),
    ];
    String rolling(double Function(GapStats) pick) =>
        windows.map((w) => w.count == 0 ? '-' : pick(w).toStringAsFixed(0)).join(' / ');
    final rates = [
      session.byteRates(const Duration(seconds: 1), now),
      session.byteRates(const Duration(seconds: 5), now),
      session.byteRates(const Duration(minutes: 1), now),
    ];
    String mbps(double Function(ByteRates) pick) =>
        rates.map((r) => pick(r).toStringAsFixed(2)).join(' / ');
    return _card('Link health', [
      _row('Transport / Health',
          '${session.transport.name} (${session.linkState.name}) / ${session.health.name}'),
      _row('Received', _size(session.bytesReceived)),
      _row('DUML Mbps 1s/5s/1m', mbps((r) => r.duml)),
      _row('Video Mbps 1s/5s/1m', mbps((r) => r.video)),
      _row('Other Mbps 1s/5s/1m', mbps((r) => r.other)),
      _row('Packets', '${session.packetCount}  (${session.packetsPerSecond(now).toStringAsFixed(0)}/s)'),
      _row('CRC errors', '${session.crcErrorCount}'),
      _row('Interval 1s/5s/1m (ms)', rolling((w) => w.meanMs)),
      _row('Jitter 1s/5s/1m (ms)', rolling((w) => w.jitterMs)),
      _row('Max gap 1s/5s/1m (ms)', rolling((w) => w.maxMs)),
      if (session.transport.currentState == LinkState.failed)
        _row('Error', session.transport.lastError ?? ''),
    ]);
  }
}
