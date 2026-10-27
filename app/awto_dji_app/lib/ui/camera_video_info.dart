import 'dart:async';

import 'package:flutter/material.dart';

import '../link/link_session.dart';

/// A small, independently refreshed label so stale settings disappear even when
/// transport bytes stop entirely. Does not rebuild or poll the video decoder.
class CameraVideoInfo extends StatefulWidget {
  const CameraVideoInfo({super.key, required this.session});
  final LinkSession session;

  @override
  State<CameraVideoInfo> createState() => _CameraVideoInfoState();
}

class _CameraVideoInfoState extends State<CameraVideoInfo> {
  late final Timer _timer;

  @override
  void initState() {
    super.initState();
    _timer = Timer.periodic(const Duration(seconds: 1), (_) => setState(() {}));
  }

  @override
  void dispose() {
    _timer.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => ListenableBuilder(
    listenable: widget.session,
    builder: (context, _) => Card(
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('Camera recording settings (DUML)'),
            Text(widget.session.cameraVideoDescription),
            const Text('Lightbridge preview may use a different format.'),
          ],
        ),
      ),
    ),
  );
}
