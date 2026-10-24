import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../debug/command_catalog.dart';
import '../link/link_session.dart';

enum _Status { idle, sent, replied, timeout }

enum _Filter { get, other, all }

/// Sends commands from [kCommandCatalog] and shows whether each got a reply. Tap a row to send
/// that command with the receiver and payload fields; Run sends every command in the filter
/// with an empty payload, one at a time. Transports with no device (sim, replay) reject writes.
class CommandTestScreen extends StatefulWidget {
  const CommandTestScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<CommandTestScreen> createState() => _CommandTestScreenState();
}

class _CommandTestScreenState extends State<CommandTestScreen> {
  final _status = <int, _Status>{}; // index into kCommandCatalog -> status
  final _receiver = TextEditingController(text: '6');
  final _payload = TextEditingController();
  _Filter _filter = _Filter.get;
  bool _running = false;
  int _sentCount = 0, _repliedCount = 0;
  String? _error;
  StreamSubscription<DumlPacket>? _sub;
  int? _awaiting; // cmdSet<<8|cmdId of the command currently awaiting a reply
  int _seq = 0x6000;

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
    _receiver.dispose();
    _payload.dispose();
    super.dispose();
  }

  List<int> get _visible => [
        for (var i = 0; i < kCommandCatalog.length; i++)
          if (switch (_filter) {
            _Filter.get => kCommandCatalog[i].isGet,
            _Filter.other => !kCommandCatalog[i].isGet,
            _Filter.all => true,
          })
            i,
      ];

  Uint8List? _payloadBytes() {
    final hex = _payload.text.replaceAll(RegExp(r'\s'), '');
    if (hex.length.isOdd || !RegExp(r'^[0-9a-fA-F]*$').hasMatch(hex)) return null;
    return Uint8List.fromList(
        [for (var i = 0; i < hex.length; i += 2) int.parse(hex.substring(i, i + 2), radix: 16)]);
  }

  Future<void> _sendOne(int i, Uint8List payload) async {
    final c = kCommandCatalog[i];
    final key = (c.cmdSet << 8) | c.cmdId;
    final pkt = DumlPacket(
      senderType: DeviceType.app,
      receiverType: int.tryParse(_receiver.text.trim()) ?? DeviceType.remoteController,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: c.cmdSet,
      cmdId: c.cmdId,
      payload: payload,
    );
    _awaiting = key;
    setState(() {
      _status[i] = _Status.sent;
      _sentCount++;
    });
    try {
      await widget.session.transport.write(pkt.encode());
    } on Object catch (_) {
      // No device on this transport (sim/replay) or link not connected: shows as timeout.
    }
    // Reply window: the RC answers within one USB read (ms); 250 ms covers the relay hop.
    await Future<void>.delayed(const Duration(milliseconds: 250));
    final replied = _awaiting != key;
    if (!mounted) return;
    setState(() {
      _status[i] = replied ? _Status.replied : _Status.timeout;
      if (replied) _repliedCount++;
    });
  }

  Future<void> _sendTapped(int i) async {
    final payload = _payloadBytes();
    if (payload == null) {
      setState(() => _error = 'Payload must be hex bytes');
      return;
    }
    setState(() => _error = null);
    await _sendOne(i, payload);
  }

  Future<void> _runAll() async {
    setState(() {
      _running = true;
      _sentCount = 0;
      _repliedCount = 0;
      _status.clear();
      _error = null;
    });
    for (final i in _visible) {
      if (!_running) break;
      await _sendOne(i, Uint8List(0));
    }
    if (mounted) setState(() => _running = false);
  }

  void _stop() => setState(() => _running = false);

  @override
  Widget build(BuildContext context) {
    final cs = Theme.of(context).colorScheme;
    final visible = _visible;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 12, 12, 0),
          child: Row(
            children: [
              FilledButton.icon(
                onPressed: _running ? null : _runAll,
                icon: const Icon(Icons.play_arrow),
                label: Text('Run ${visible.length}'),
              ),
              const SizedBox(width: 8),
              if (_running)
                OutlinedButton.icon(
                  onPressed: _stop,
                  icon: const Icon(Icons.stop),
                  label: const Text('Stop'),
                ),
              const Spacer(),
              for (final f in _Filter.values)
                Padding(
                  padding: const EdgeInsets.only(left: 4),
                  child: ChoiceChip(
                    label: Text(f.name),
                    selected: _filter == f,
                    onSelected: _running ? null : (_) => setState(() => _filter = f),
                  ),
                ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(12, 8, 12, 0),
          child: Row(
            children: [
              SizedBox(
                width: 80,
                child: TextField(
                  controller: _receiver,
                  decoration: const InputDecoration(
                      labelText: 'Receiver', isDense: true, border: OutlineInputBorder()),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: TextField(
                  controller: _payload,
                  decoration: InputDecoration(
                      labelText: 'Payload hex (sent when you tap a row)',
                      errorText: _error,
                      isDense: true,
                      border: const OutlineInputBorder()),
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: const EdgeInsets.all(8),
          child: Align(
            alignment: Alignment.centerRight,
            child: Text('$_repliedCount/$_sentCount replied'),
          ),
        ),
        Expanded(
          child: ListView.builder(
            itemCount: visible.length,
            itemBuilder: (context, row) {
              final i = visible[row];
              final c = kCommandCatalog[i];
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
                onTap: () => _sendTapped(i),
              );
            },
          ),
        ),
      ],
    );
  }
}
