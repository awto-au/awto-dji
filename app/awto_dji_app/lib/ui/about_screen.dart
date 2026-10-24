import 'package:flutter/material.dart';

import '../link/link_session.dart';
import '../transport/aoa_identity.dart';

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
