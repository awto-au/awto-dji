import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../transport/aoa_identity.dart';
import '../transport/aoa_transport.dart';

class AboutScreen extends StatelessWidget {
  const AboutScreen({super.key, required this.session});
  final LinkSession session;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: session,
      builder: (context, _) => ListView(
        padding: const EdgeInsets.all(16),
        children: [
          const ListTile(
            leading: Icon(Icons.tune),
            title: Text('Control enabled'),
            subtitle: Text(
                'The gimbal screen and the CONNECT / DISCONNECT / GIMBAL intents write to '
                'the link. Simulated and replay transports reject writes.'),
          ),
          ListTile(
            title: const Text('Transport'),
            subtitle: Text('${session.transport.name}: ${session.linkState.name}'),
          ),
          ListTile(
            title: const Text('Bytes / packets / CRC errors'),
            subtitle: Text(
                '${session.bytesReceived} / ${session.packetCount} / ${session.crcErrorCount}'),
          ),
          ..._channelTiles(session.transport),
          ListTile(
            title: const Text('AOA identity (manufacturer / model)'),
            subtitle: Text('${AoaIdentity.manufacturer} / ${AoaIdentity.model} '
                '— confirmed against DJI GO 4\'s own match logic'),
          ),
          const ListTile(
            title: Text('Geofence'),
            subtitle: Text(
                'Safety gate only; adds restrictions, has no override. Zones shown are samples.'),
          ),
        ],
      ),
    );
  }
}

/// What's actually flowing over which wire right now - not just the transport name.
List<Widget> _channelTiles(Object transport) {
  if (transport is! AoaTransport) {
    return [
      ListTile(
        title: const Text('Channels'),
        subtitle: Text('${transport.runtimeType}: no PC-side debug channels (accessory-only transports don\'t have them)'),
      ),
    ];
  }
  final tiles = [
    const ListTile(
      dense: true,
      title: Text('Accessory (AOA, USB)'),
      subtitle: Text('Bidirectional: DUML command bytes + camera video'),
    ),
  ];
  final host = transport.relayHost;
  final port = transport.relayPort;
  if (host == null || port == null) {
    tiles.add(const ListTile(
      dense: true,
      title: Text('PC debug relay'),
      subtitle: Text('Not configured (no relay host/port set)'),
    ));
  } else {
    tiles.add(ListTile(
      dense: true,
      title: Text('Debug relay (TCP $host:$port)'),
      subtitle: Text(
          'Out: AoaMux\'s own envelope/discard records${transport.relayVideo ? " + video" : " (video suppressed)"}. '
          'In: command injection from a PC script straight to the accessory.'),
    ));
    tiles.add(ListTile(
      dense: true,
      title: Text('Raw ground truth (UDP $host:${port + 1})'),
      subtitle: const Text('Out only: every accessory byte chunk, verbatim, before AoaMux touches it.'),
    ));
  }
  return tiles;
}
