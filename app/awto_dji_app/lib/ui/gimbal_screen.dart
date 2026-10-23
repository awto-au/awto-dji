import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:flutter/material.dart';

import '../link/link_session.dart';

/// Gimbal pitch/roll/yaw control - cmdset 0x04 (Gimbal), cmdid 0x0a
/// ("gimbal_ext_ctrl_degree"). Payload layout from the public o-gs/dji-firmware-tools
/// dissector (dji-dumlv1-gimbal.lua), not guessed: 3x int16 angle (degrees*10, range
/// -180..180), int16 unknown6, uint8 flags, uint8 unknown9. Angle order (pitch/roll/yaw) and
/// the flags/unknown9 fields are the dissector's own best-effort labelling ("Unknown...") -
/// not independently confirmed against this project's own captures.
///
/// This is real physical actuation, unlike every other screen in this app. Every send goes
/// through an explicit confirmation dialog - there is no auto-send path.
class GimbalScreen extends StatefulWidget {
  const GimbalScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<GimbalScreen> createState() => _GimbalScreenState();
}

class _GimbalScreenState extends State<GimbalScreen> {
  double _pitch = 0, _roll = 0, _yaw = 0;
  String? _lastResult;
  var _seq = 0x6800;

  Uint8List _buildPacket() {
    final payload = ByteData(8);
    payload.setInt16(0, (_pitch * 10).round(), Endian.little);
    payload.setInt16(2, (_roll * 10).round(), Endian.little);
    payload.setInt16(4, (_yaw * 10).round(), Endian.little);
    payload.setUint8(6, 0); // flags - unconfirmed meaning, 0 = default
    payload.setUint8(7, 5); // unknown9 ("speed"? dissector range 1..10) - mid value
    final pkt = DumlPacket(
      senderType: DeviceType.pc,
      receiverType: DeviceType.gimbal,
      sequence: _seq++,
      ackType: AckType.afterExec,
      cmdSet: CmdSet.gimbal,
      cmdId: 0x0a,
      payload: payload.buffer.asUint8List(),
    );
    return pkt.encode();
  }

  Future<void> _confirmAndSend() async {
    final pkt = _buildPacket();
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Send gimbal command?'),
        content: Text(
          'This physically moves the gimbal.\n\n'
          'Pitch ${_pitch.toStringAsFixed(1)}°  Roll ${_roll.toStringAsFixed(1)}°  '
          'Yaw ${_yaw.toStringAsFixed(1)}°\n\n'
          'Packet: ${pkt.map((b) => b.toRadixString(16).padLeft(2, '0')).join(' ')}',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('Cancel')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('Send')),
        ],
      ),
    );
    if (ok != true || !mounted) return;
    try {
      await widget.session.transport.write(pkt);
      setState(() => _lastResult = 'Sent.');
    } on Object catch (e) {
      setState(() => _lastResult = 'Send failed: $e');
    }
  }

  Widget _slider(String label, double value, ValueChanged<double> onChanged) {
    return Row(children: [
      SizedBox(width: 56, child: Text(label)),
      Expanded(
        child: Slider(
          value: value,
          min: -45,
          max: 45,
          divisions: 180,
          label: '${value.toStringAsFixed(1)}°',
          onChanged: onChanged,
        ),
      ),
      SizedBox(width: 56, child: Text('${value.toStringAsFixed(1)}°')),
    ]);
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Card(
            color: Theme.of(context).colorScheme.errorContainer,
            child: const Padding(
              padding: EdgeInsets.all(12),
              child: Text(
                'This sends real control commands to the gimbal. Payload field meanings are '
                'from the public dissector, not independently confirmed. Every send requires '
                'confirmation - nothing here is automatic.',
              ),
            ),
          ),
          const SizedBox(height: 16),
          _slider('Pitch', _pitch, (v) => setState(() => _pitch = v)),
          _slider('Roll', _roll, (v) => setState(() => _roll = v)),
          _slider('Yaw', _yaw, (v) => setState(() => _yaw = v)),
          const SizedBox(height: 16),
          Row(children: [
            FilledButton.icon(
              onPressed: _confirmAndSend,
              icon: const Icon(Icons.send),
              label: const Text('Send (with confirmation)'),
            ),
            const SizedBox(width: 12),
            OutlinedButton(
              onPressed: () => setState(() {
                _pitch = 0;
                _roll = 0;
                _yaw = 0;
              }),
              child: const Text('Reset to 0'),
            ),
          ]),
          if (_lastResult != null) ...[
            const SizedBox(height: 12),
            Text(_lastResult!),
          ],
        ],
      ),
    );
  }
}
