import 'dart:io';

import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../transport/aoa_transport.dart';
import '../transport/link_transport.dart';
import '../transport/replay_transport.dart';
import '../transport/simulated_transport.dart';
import '../video/video_decoder.dart';
import 'home_shell.dart';

enum Source { simulated, replay, accessory }

class ConnectScreen extends StatefulWidget {
  const ConnectScreen({super.key});

  @override
  State<ConnectScreen> createState() => _ConnectScreenState();
}

class _ConnectScreenState extends State<ConnectScreen> {
  Source _source = Source.simulated;
  final _path = TextEditingController();
  final _relay = TextEditingController();
  double _speed = 1.0;
  String? _error;
  bool _busy = false;

  bool get _aoaAvailable => Platform.isAndroid;
  VideoDecoder? _videoDecoder;

  @override
  void dispose() {
    _path.dispose();
    _relay.dispose();
    super.dispose();
  }

  Future<LinkTransport> _build() async {
    switch (_source) {
      case Source.simulated:
        return SimulatedAircraftTransport();
      case Source.replay:
        return ReplayTransport.fromFile(_path.text.trim(), speed: _speed);
      case Source.accessory:
        final parts = _relay.text.trim().split(':');
        final host = parts.isNotEmpty && parts[0].isNotEmpty ? parts[0] : null;
        final port = parts.length > 1 ? int.tryParse(parts[1]) : null;
        _videoDecoder = VideoDecoder();
        return AoaTransport(
            relayHost: host, relayPort: port, videoDecoder: _videoDecoder);
    }
  }

  Future<void> _connect() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final nav = Navigator.of(context);
    try {
      final session = LinkSession(await _build());
      await session.start();
      if (session.transport.currentState == LinkState.failed) {
        _error = session.transport.lastError ?? 'connect failed';
        await session.stop();
        session.dispose();
      } else if (mounted) {
        await nav.push(MaterialPageRoute<void>(
            builder: (_) =>
                HomeShell(session: session, videoDecoder: _videoDecoder)));
        await session.stop();
        session.dispose();
      }
    } on Object catch (e) {
      _error = '$e';
    }
    if (mounted) setState(() => _busy = false);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Connect')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const Text('Read-only monitor. Nothing is ever sent to the aircraft.'),
          const SizedBox(height: 8),
          RadioGroup<Source>(
            groupValue: _source,
            onChanged: (v) => setState(() => _source = v ?? _source),
            child: Column(children: [
              const RadioListTile<Source>(
                value: Source.simulated,
                title: Text('Simulated aircraft'),
                subtitle: Text('Generated OSD telemetry, no hardware'),
              ),
              const RadioListTile<Source>(
                value: Source.replay,
                title: Text('Replay capture file'),
                subtitle: Text('Raw DUML bytes or hex text'),
              ),
              RadioListTile<Source>(
                value: Source.accessory,
                enabled: _aoaAvailable,
                title: const Text('Android accessory (RC)'),
                subtitle: Text(_aoaAvailable
                    ? 'Phone as USB accessory of the controller'
                    : 'Android only'),
              ),
            ]),
          ),
          if (_source == Source.accessory) ...[
            TextField(
              controller: _relay,
              decoration: const InputDecoration(
                  labelText: 'Diag relay host:port (optional)',
                  helperText: 'Mirrors raw bytes to a dev-machine TCP listener',
                  border: OutlineInputBorder()),
            ),
          ],
          if (_source == Source.replay) ...[
            TextField(
              controller: _path,
              decoration: const InputDecoration(
                  labelText: 'Capture file path', border: OutlineInputBorder()),
            ),
            Row(children: [
              const Text('Speed'),
              Expanded(
                child: Slider(
                  value: _speed,
                  min: 0.25,
                  max: 8,
                  divisions: 31,
                  label: '${_speed.toStringAsFixed(2)}x',
                  onChanged: (v) => setState(() => _speed = v),
                ),
              ),
              Text('${_speed.toStringAsFixed(2)}x'),
            ]),
          ],
          if (_error != null)
            Padding(
              padding: const EdgeInsets.only(top: 8),
              child: Text(_error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error)),
            ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _busy ? null : _connect,
            icon: const Icon(Icons.link),
            label: const Text('Connect'),
          ),
        ],
      ),
    );
  }
}
