import 'package:flutter/material.dart';

import '../link/gimbal_commands.dart';
import '../link/link_session.dart';

/// Gimbal pitch/roll/yaw control, cmdset 0x04 / 0x0a. Frames come from [GimbalCommands]
/// (payload layout from the vendor app's own packing code). Sends immediately.
class GimbalScreen extends StatefulWidget {
  const GimbalScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<GimbalScreen> createState() => _GimbalScreenState();
}

class _GimbalScreenState extends State<GimbalScreen> {
  double _pitch = 0, _roll = 0, _yaw = 0;
  String? _lastResult;
  final _gimbal = GimbalCommands(0x6800);

  static String _hex(List<int> b) => b.map((x) => x.toRadixString(16).padLeft(2, '0')).join(' ');

  Future<void> _send() async {
    final permission = _gimbal.permissionRequest();
    final move = _gimbal.angle(pitch: _pitch, roll: _roll, yaw: _yaw);
    try {
      await widget.session.transport.write(permission);
      await widget.session.transport.write(move);
      setState(() => _lastResult = 'Sent.\n${_hex(permission)}\n${_hex(move)}');
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
          _slider('Pitch', _pitch, (v) => setState(() => _pitch = v)),
          _slider('Roll', _roll, (v) => setState(() => _roll = v)),
          _slider('Yaw', _yaw, (v) => setState(() => _yaw = v)),
          const SizedBox(height: 16),
          Row(children: [
            FilledButton.icon(
              onPressed: _send,
              icon: const Icon(Icons.send),
              label: const Text('Send'),
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
