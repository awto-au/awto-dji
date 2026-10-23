import 'package:flutter/material.dart';

import '../link/link_session.dart';
import 'names.dart';

class PacketLogScreen extends StatefulWidget {
  const PacketLogScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<PacketLogScreen> createState() => _PacketLogScreenState();
}

class _PacketLogScreenState extends State<PacketLogScreen> {
  String _filter = '';

  /// Filter matches the rendered row text (names, hex ids, device names, hex).
  static String _text(PacketLogEntry e) {
    final p = e.packet;
    if (p == null) return 'crc error ${e.error} ${hexBytes(e.raw)}'.toLowerCase();
    return '${hms(e.time)} ${deviceName(p.senderType)} ${deviceName(p.receiverType)} '
            '${messageLabel(p.cmdSet, p.cmdId)} ${hexBytes(e.raw)}'
        .toLowerCase();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(8),
          child: TextField(
            decoration: const InputDecoration(
              prefixIcon: Icon(Icons.search),
              hintText: 'Filter: name, 0x03/0x43, FC, crc ...',
              border: OutlineInputBorder(),
              isDense: true,
            ),
            onChanged: (v) => setState(() => _filter = v.trim().toLowerCase()),
          ),
        ),
        Expanded(
          child: ListenableBuilder(
            listenable: widget.session,
            builder: (context, _) {
              final all = widget.session.log;
              final shown = _filter.isEmpty
                  ? all
                  : all.where((e) => _text(e).contains(_filter)).toList();
              return ListView.builder(
                itemCount: shown.length,
                itemBuilder: (context, i) => _Row(entry: shown[shown.length - 1 - i]),
              );
            },
          ),
        ),
      ],
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.entry});
  final PacketLogEntry entry;

  @override
  Widget build(BuildContext context) {
    final p = entry.packet;
    final cs = Theme.of(context).colorScheme;
    const mono = TextStyle(fontFamily: 'monospace', fontSize: 11);
    return ListTile(
      dense: true,
      leading: Icon(entry.crcOk ? Icons.check_circle : Icons.error,
          color: entry.crcOk ? Colors.green : cs.error, size: 18),
      title: Text(p == null
          ? 'CRC/format error: ${entry.error}'
          : '${deviceName(p.senderType)} -> ${deviceName(p.receiverType)}  '
              '${messageLabel(p.cmdSet, p.cmdId)}'),
      subtitle: Text(
        '${hms(entry.time)}  ${entry.raw.length} B\n${hexBytes(entry.raw)}',
        style: mono,
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
      ),
      isThreeLine: true,
    );
  }
}
