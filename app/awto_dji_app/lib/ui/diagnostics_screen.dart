import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:flutter/material.dart';

import '../link/diagnostics_commands.dart';
import '../link/gimbal_commands.dart';
import '../link/link_session.dart';

/// Version/firmware info, motor-arming interlock + IMU/compass/gimbal-health status,
/// and self-test triggers - the subset of DJI GO 4 / DJI GO's own diagnostics screen
/// we have real decompiled source for. See `docs/known-telemetry-and-commands.md` for
/// what's V (verified byte-for-byte against the decompile) vs I/U (inferred/unknown).
///
/// Motor test and camera test buttons are deliberately NOT here: no matching
/// `Data*Test*.java` class or catalog name was found for either in the dji.go.v4/
/// dji.pilot decompiles searched this session - adding a trigger for them would be a
/// guess, not a confirmed command.
class DiagnosticsScreen extends StatefulWidget {
  const DiagnosticsScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<DiagnosticsScreen> createState() => _DiagnosticsScreenState();
}

class _DiagnosticsScreenState extends State<DiagnosticsScreen> {
  final _gimbal = GimbalCommands(0x7900);
  final _diag = DiagnosticsCommands();
  String? _lastAction;

  static const _versionTargets = [
    (DeviceType.flightController, 'Flight controller'),
    (DeviceType.gimbal, 'Gimbal'),
    (DeviceType.camera, 'Camera'),
    (DeviceType.remoteController, 'RC'),
  ];

  Future<void> _send(Uint8List frame, String label) async {
    try {
      await widget.session.transport.write(frame);
      setState(() => _lastAction = '$label: sent');
    } on Object catch (e) {
      setState(() => _lastAction = '$label: send failed ($e)');
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.session,
      builder: (context, _) {
        final osd = widget.session.latestOsd;
        return ListView(
          padding: const EdgeInsets.all(12),
          children: [
            _card('Motor arming interlock', [
              _row('Blocked', osd?.motorBlocked == null ? '-' : osd!.motorBlocked! ? 'YES' : 'no'),
              _row('Motor up', osd?.motorUp == null ? '-' : osd!.motorUp! ? 'YES' : 'no'),
              _row('Cause', osd?.motorFailedCause == null ? '-' : osd!.motorFailedCause!.name),
              _row('FC protocol version', osd?.flycVersion == null ? '-' : '${osd!.flycVersion}'),
            ]),
            _card('Compass / IMU', [
              _row('Compass error', osd?.compassError == null ? '-' : osd!.compassError! ? 'YES' : 'no'),
              _row('IMU preheated', osd?.imuPreheated == null ? '-' : osd!.imuPreheated! ? 'yes' : 'NO'),
              _row('IMU init/cal reason',
                  osd?.imuInitFailReason == null ? '-' : osd!.imuInitFailReason!.name),
            ]),
            _card('Gimbal health', [
              _row('Status', _gimbalHealth(osd?.motorFailedCause)),
            ]),
            _card('Firmware / hardware version', [
              for (final (deviceType, label) in _versionTargets)
                _row(label, _versionText(widget.session.latestVersions[deviceType])),
            ]),
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final (deviceType, label) in _versionTargets)
                    OutlinedButton(
                      onPressed: () => _send(_diag.getVersion(receiverType: deviceType),
                          'GetVersion($label)'),
                      child: Text('Request $label version'),
                    ),
                  FilledButton.icon(
                    onPressed: () =>
                        _send(_gimbal.autoCalibration(), 'Gimbal auto-calibration'),
                    icon: const Icon(Icons.science),
                    label: const Text('Gimbal self-test / auto-calibration'),
                  ),
                ],
              ),
            ),
            if (_lastAction != null)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: 4),
                child: Text(_lastAction!, style: Theme.of(context).textTheme.bodySmall),
              ),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'Motor test and camera test triggers are not included: no matching '
                'command was found in the decompiled vendor app source. Gimbal '
                'self-test above is confirmed (AutoCalibration, cmdset 0x04/0x08) - '
                'real pitch movement + mode change observed against hardware.',
                style: TextStyle(fontStyle: FontStyle.italic),
              ),
            ),
          ],
        );
      },
    );
  }

  static String _gimbalHealth(MotorStartFailedCause? cause) {
    if (cause == null) return '-';
    const gimbalCauses = {
      MotorStartFailedCause.gimbalGyroAbnormal,
      MotorStartFailedCause.gimbalEscPitchNonData,
      MotorStartFailedCause.gimbalEscRollNonData,
      MotorStartFailedCause.gimbalEscYawNonData,
      MotorStartFailedCause.gimbalFirmIsUpdating,
      MotorStartFailedCause.gimbalDisorder,
      MotorStartFailedCause.gimbalPitchShock,
      MotorStartFailedCause.gimbalRollShock,
      MotorStartFailedCause.gimbalYawShock,
      MotorStartFailedCause.gimbalIsCalibrating,
    };
    if (gimbalCauses.contains(cause)) return cause.name;
    return cause == MotorStartFailedCause.none ? 'OK' : '-';
  }

  static String _versionText(CommonVersion? v) {
    if (v == null) return '-';
    return 'fw ${v.firmwareVersion} / loader ${v.loaderVersion} '
        '(${v.hardwareVersion.isEmpty ? "?" : v.hardwareVersion})';
  }
}

Widget _row(String k, String v) => Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(k),
          Flexible(
            child: Text(v, textAlign: TextAlign.right, overflow: TextOverflow.ellipsis),
          ),
        ],
      ),
    );

Widget _card(String title, List<Widget> rows) => Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 4),
            ...rows,
          ],
        ),
      ),
    );
