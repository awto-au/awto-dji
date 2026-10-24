import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../safety/safety_gate.dart';
import '../safety/sample_zones.dart';
import '../video/video_decoder.dart';
import 'about_screen.dart';
import 'command_test_screen.dart';
import 'diagnostics_screen.dart';
import 'gimbal_screen.dart';
import 'packet_log_screen.dart';
import 'telemetry_screen.dart';
import 'video_screen.dart';

class HomeShell extends StatefulWidget {
  const HomeShell({super.key, required this.session, this.gate, this.videoDecoder});
  final LinkSession session;
  final SafetyGate? gate;
  final VideoDecoder? videoDecoder;

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
      VideoScreen(decoder: widget.videoDecoder, session: widget.session),
      PacketLogScreen(session: widget.session),
      CommandTestScreen(session: widget.session),
      GimbalScreen(session: widget.session),
      DiagnosticsScreen(session: widget.session),
      AboutScreen(session: widget.session),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(const [
          'Telemetry',
          'Video',
          'Packet log',
          'Command test',
          'Gimbal',
          'Diagnostics',
          'About'
        ][_index]),
      ),
      body: pages[_index],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _index,
        onDestinationSelected: (i) => setState(() => _index = i),
        destinations: const [
          NavigationDestination(icon: Icon(Icons.speed), label: 'Telemetry'),
          NavigationDestination(icon: Icon(Icons.videocam_outlined), label: 'Video'),
          NavigationDestination(icon: Icon(Icons.list_alt), label: 'Packets'),
          NavigationDestination(icon: Icon(Icons.science_outlined), label: 'Test'),
          NavigationDestination(icon: Icon(Icons.camera_outdoor_outlined), label: 'Gimbal'),
          NavigationDestination(icon: Icon(Icons.health_and_safety_outlined), label: 'Diag'),
          NavigationDestination(icon: Icon(Icons.info_outline), label: 'About'),
        ],
      ),
    );
  }
}
