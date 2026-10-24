import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:flutter/material.dart';

import '../link/camera_commands.dart';
import '../link/link_session.dart';

/// Camera exposure control: AE lock toggle + EV compensation slider + exposure
/// mode selector (cmdset 0x02 "CAMERA"). Real payload layouts and UI call sites
/// this was reversed from: `link/camera_commands.dart`. Not yet tested against
/// hardware.
class CameraScreen extends StatefulWidget {
  const CameraScreen({super.key, required this.session});
  final LinkSession session;

  @override
  State<CameraScreen> createState() => _CameraScreenState();
}

class _CameraScreenState extends State<CameraScreen> {
  final _camera = CameraCommands(0x6c00);
  String? _lastAction;
  double? _pendingEv; // while the slider is being dragged, before it's sent

  Future<void> _send(Uint8List frame, String label, {Uint8List? andThen}) async {
    try {
      await widget.session.transport.write(frame);
      if (andThen != null) await widget.session.transport.write(andThen);
      setState(() => _lastAction = '$label: sent');
    } on Object catch (e) {
      setState(() => _lastAction = '$label: send failed ($e)');
    }
  }

  void _toggleAeLock(bool next) =>
      _send(_camera.setAeLock(next), 'SetAELock($next)', andThen: _camera.getAeLock());

  void _setEv(double ev) => _send(
        _camera.setExposureCompensation(ev),
        'SetExposureCompensation(${ev.toStringAsFixed(1)})',
        andThen: _camera.getExposureCompensation(),
      );

  void _setMode(CameraExposureMode mode) => _send(
        _camera.setExposureMode(mode),
        'SetExposureMode(${mode.name})',
        andThen: _camera.getExposureMode(),
      );

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.session,
      builder: (context, _) {
        final aeLock = widget.session.latestAeLock;
        final evState = widget.session.latestExposureCompensation;
        final modeState = widget.session.latestExposureMode;
        final sliderValue = (_pendingEv ?? evState?.ev ?? 0.0).clamp(-5.0, 5.0);

        return ListView(
          padding: const EdgeInsets.all(16),
          children: [
            SwitchListTile(
              title: const Text('AE lock'),
              subtitle: Text(aeLock == null
                  ? 'state unknown - no GetAELock reply yet'
                  : aeLock.locked
                      ? 'locked'
                      : 'unlocked'),
              value: aeLock?.locked ?? false,
              onChanged: _toggleAeLock,
            ),
            const SizedBox(height: 16),
            Text('Exposure compensation', style: Theme.of(context).textTheme.labelLarge),
            Row(
              children: [
                Expanded(
                  child: Slider(
                    min: -5.0,
                    max: 5.0,
                    // 31 raw steps (1..31), 1/3 EV apart - DataCameraSetEV's real range.
                    divisions: 30,
                    value: sliderValue,
                    label: '${sliderValue >= 0 ? '+' : ''}${sliderValue.toStringAsFixed(1)} EV',
                    onChanged: (v) => setState(() => _pendingEv = v),
                    onChangeEnd: (v) {
                      setState(() => _pendingEv = null);
                      _setEv(v);
                    },
                  ),
                ),
                SizedBox(
                  width: 56,
                  child: Text(
                    '${sliderValue >= 0 ? '+' : ''}${sliderValue.toStringAsFixed(1)}',
                    textAlign: TextAlign.center,
                  ),
                ),
              ],
            ),
            Align(
              alignment: Alignment.centerLeft,
              child: OutlinedButton(
                onPressed: () => _setEv(0.0),
                child: const Text('Reset EV to 0'),
              ),
            ),
            Text(
              evState == null
                  ? 'Last confirmed: - (no GetExposureCompensation reply yet)'
                  : 'Last confirmed: ${evState.ev >= 0 ? '+' : ''}${evState.ev.toStringAsFixed(1)} EV',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            Text('Exposure mode', style: Theme.of(context).textTheme.labelLarge),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final mode in const [
                  CameraExposureMode.auto,
                  CameraExposureMode.p,
                  CameraExposureMode.s,
                  CameraExposureMode.a,
                  CameraExposureMode.m,
                ])
                  ChoiceChip(
                    label: Text(mode.name.toUpperCase()),
                    selected: modeState?.mode == mode,
                    onSelected: (_) => _setMode(mode),
                  ),
              ],
            ),
            Text(
              modeState == null
                  ? 'Last confirmed: - (no GetExposureMode reply yet)'
                  : 'Last confirmed: ${modeState.mode.name.toUpperCase()}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(height: 16),
            if (_lastAction != null)
              Text(_lastAction!, style: Theme.of(context).textTheme.bodySmall),
            const Padding(
              padding: EdgeInsets.symmetric(vertical: 8),
              child: Text(
                'B (shutter-priority), SCN (scene) and C (custom) exist on the wire '
                '(DataCameraSetExposureMode.ExposureMode) but are not offered here: SCN '
                'needs a scene index this session did not reverse, and B/C were not seen '
                'driven by a traced P3-era UI path. GetAELock/GetExposureCompensation/'
                'GetExposureMode request payloads are inferred empty, by analogy with '
                'every other decompiled Get in this cmdset - no dedicated Get class was '
                'found for exposure mode or compensation. Not yet tested against hardware.',
                style: TextStyle(fontStyle: FontStyle.italic),
              ),
            ),
          ],
        );
      },
    );
  }
}
