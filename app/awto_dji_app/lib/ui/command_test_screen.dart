import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/material.dart';

import '../debug/command_catalog.dart';
import '../link/link_session.dart';

enum _Status { idle, sent, replied, timeout }

/// Sends every read-only (Get*) command from [kSafeCommandCatalog] one at a time and shows
/// whether each got a reply. Never sends Set*/control commands. Read-only transports (sim,
/// replay) reject every write - that's expected, not a bug.
class CommandTestScreen extends StatefulWidget {
  const CommandTestScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<CommandTestScreen> createState() => _CommandTestScreenState();
}

class _CommandTestScreenState extends State<CommandTestScreen> {
  final _status = <int, _Status>{}; // index into kSafeCommandCatalog -> status
  bool _running = false;
  int _sentCount = 0, _repliedCount = 0;
  StreamSubscription<DumlPacket>? _sub;
  int? _awaiting; // cmdSet<<8|cmdId of the command currently awaiting a reply

  @override
  void initState() {
    super.initState();
    _sub = widget.session.packets.listen((p) {
      final key = (p.cmdSet << 8) | p.cmdId;
      if (_awaiting == key) {
        _awaiting = null;
      }
    });
  }

  @override
  void dispose() {
    _sub?.cancel();
    super.dispose();
  }

  Future<void> _runAll() async {
    setState(() {
      _running = true;
      _sentCount = 0;
      _repliedCount = 0;
      _status.clear();
    });
    var seq = 0x6000;
    for (var i = 0; i < kSafeCommandCatalog.length; i++) {
      if (!_running) break;
      final c = kSafeCommandCatalog[i];
      final key = (c.cmdSet << 8) | c.cmdId;
      final pkt = DumlPacket(
        senderType: DeviceType.pc,
        receiverType: DeviceType.remoteController,
        sequence: seq++,
        ackType: AckType.afterExec,
        cmdSet: c.cmdSet,
        cmdId: c.cmdId,
      );
      _awaiting = key;
      setState(() {
        _status[i] = _Status.sent;
        _sentCount++;
      });
      try {
        await widget.session.transport.write(pkt.encode());
      } on Object catch (_) {
        // Read-only transport (sim/replay) or link not connected - leave as sent/timeout below.
      }
      await Future<void>.delayed(const Duration(milliseconds: 250));
      final replied = _awaiting != key;
      setState(() {
        _status[i] = replied ? _Status.replied : _Status.timeout;
        if (replied) _repliedCount++;
      });
    }
    setState(() => _running = false);
  }

  void _stop() => setState(() => _running = false);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            children: [
              FilledButton.icon(
                onPressed: _running ? null : _runAll,
                icon: const Icon(Icons.play_arrow),
                label: Text('Run all ${kSafeCommandCatalog.length} (Get* only)'),
              ),
              const SizedBox(width: 8),
              if (_running)
                OutlinedButton.icon(
                  onPressed: _stop,
                  icon: const Icon(Icons.stop),
                  label: const Text('Stop'),
                ),
              const Spacer(),
              Text('$_repliedCount/$_sentCount replied'),
            ],
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: kSafeCommandCatalog.length,
            itemBuilder: (context, i) {
              final c = kSafeCommandCatalog[i];
              final s = _status[i] ?? _Status.idle;
              final (icon, color) = switch (s) {
                _Status.idle => (Icons.circle_outlined, cs.outline),
                _Status.sent => (Icons.hourglass_top, cs.secondary),
                _Status.replied => (Icons.check_circle, Colors.green),
                _Status.timeout => (Icons.cancel_outlined, cs.outline),
              };
              return ListTile(
                dense: true,
                leading: Icon(icon, color: color, size: 18),
                title: Text('${c.cmdSetName}.${c.name}'),
                subtitle: Text(
                    'set=0x${c.cmdSet.toRadixString(16)} id=0x${c.cmdId.toRadixString(16)}'),
              );
            },
          ),
        ),
      ],
    );
  }
}
