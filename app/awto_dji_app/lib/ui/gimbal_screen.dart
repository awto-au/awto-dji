import 'dart:async';

import 'package:duml/duml.dart';
import 'package:flutter/material.dart';

import '../link/link_session.dart';

/// Gimbal speed control (cmdset 0x04 / 0x0c), confirmed 2026-10-24 against real
/// dji.pilot decompile as the command the app's own FPV gimbal UI actually sends -
/// continuously on a 40ms timer while a direction button is held, permission bit
/// embedded in the same packet. Not yet tested against hardware.
class GimbalScreen extends StatefulWidget {
  const GimbalScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<GimbalScreen> createState() => _GimbalScreenState();
}

class _GimbalScreenState extends State<GimbalScreen> {
  int _seq = 0x6800;
  Timer? _holdTimer;
  String? _lastError;

  // Real UI's own speed constant is a raw 270; our encode is deg/s*10, so 27 deg/s.
  static const _speedDegPerSec = 27.0;
  static const _holdPeriod = Duration(milliseconds: 40); // matches the real app's Timer

  void _startHold({double pitch = 0, double yaw = 0}) {
    _holdTimer?.cancel();
    void send() {
      final frame = GimbalSpeedControl(
        pitch: pitch,
        yaw: yaw,
        takeControl: true,
      ).encode(receiverType: DeviceType.gimbal, sequence: _seq++);
      widget.session.transport.write(frame).catchError((Object e) {
        setState(() => _lastError = 'Send failed: $e');
      });
    }

    send(); // one immediately, then every 40ms while held
    _holdTimer = Timer.periodic(_holdPeriod, (_) => send());
  }

  void _endHold() {
    _holdTimer?.cancel();
    _holdTimer = null;
    // release, matches real app
    final frame = GimbalSpeedControl(takeControl: false)
        .encode(receiverType: DeviceType.gimbal, sequence: _seq++);
    widget.session.transport.write(frame).catchError((Object e) {
      setState(() => _lastError = 'Release send failed: $e');
    });
  }

  @override
  void dispose() {
    _holdTimer?.cancel();
    super.dispose();
  }

  Widget _holdButton(IconData icon, {double pitch = 0, double yaw = 0}) {
    return GestureDetector(
      onTapDown: (_) => _startHold(pitch: pitch, yaw: yaw),
      onTapUp: (_) => _endHold(),
      onTapCancel: _endHold,
      child: Container(
        width: 64,
        height: 64,
        decoration: BoxDecoration(
          color: Theme.of(context).colorScheme.surfaceContainerHighest,
          shape: BoxShape.circle,
        ),
        child: Icon(icon, size: 32),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Pitch', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _holdButton(Icons.keyboard_arrow_up, pitch: _speedDegPerSec),
              const SizedBox(width: 24),
              _holdButton(Icons.keyboard_arrow_down, pitch: -_speedDegPerSec),
            ],
          ),
          const SizedBox(height: 24),
          Text('Yaw', style: Theme.of(context).textTheme.labelLarge),
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _holdButton(Icons.keyboard_arrow_left, yaw: -_speedDegPerSec),
              const SizedBox(width: 24),
              _holdButton(Icons.keyboard_arrow_right, yaw: _speedDegPerSec),
            ],
          ),
          const SizedBox(height: 16),
          Text(
            'Hold a button to move the gimbal; release to stop. Roll is not '
            'interactively controlled on the Phantom 3.',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          if (_lastError != null) ...[
            const SizedBox(height: 12),
            Text(_lastError!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ],
        ],
      ),
    );
  }
}
