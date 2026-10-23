import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../safety/safety_gate.dart';
import '../safety/sample_zones.dart';
import 'about_screen.dart';
import 'packet_log_screen.dart';
import 'telemetry_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.session, this.gate});
  final LinkSession session;
  final SafetyGate? gate;

  @override
  State<HomeShell> createState() => _HomeShellState();
}

class _HomeShellState extends State<HomeShell> {
  int _index = 0;
  late final SafetyGate _gate = widget.gate ?? SafetyGate(sampleFence());

  @override
  Widget build(BuildContext context) {
    final pages = [
      TelemetryScreen(session: widget.session, gate: _gate),
      PacketLogScreen(session: widget.session),
      AboutScreen(session: widget.session),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(const ['Telemetry', 'Packet log', 'About'][_index]),
        actions: [
          Padding(
            padding: const EdgeInsets.only(right: 12),
            child: Chip(
              avatar: const Icon(Icons.visibility, size: 16),
              label: const Text('READ-ONLY'),
            ),
          ),
        ],
      ),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.speed), label: 'Telemetry'),
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Packets'),
          NavigationDestination(icon: Icon(Icons.info_outline), label: 'About'),
        ],
      ),
    );
  }
}
