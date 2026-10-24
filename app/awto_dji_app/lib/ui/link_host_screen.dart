import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../link/link_host.dart';
import 'home_shell.dart';

const _intents = MethodChannel('au.awto.dji/intents');

/// Shows the telemetry shell once a session exists, otherwise the host's status.
class LinkHostScreen extends StatefulWidget {
  const LinkHostScreen({super.key, required this.host});
  final LinkHost host;

  @override
  State<LinkHostScreen> createState() => _LinkHostScreenState();
}

class _LinkHostScreenState extends State<LinkHostScreen> {
  int _intentRevision = 0;
  @override
  void initState() {
    super.initState();
    _intents.setMethodCallHandler(_onNative);
    _startup();
  }

  @override
  void dispose() {
    _intents.setMethodCallHandler(null);
    super.dispose();
  }

  Future<void> _startup() async {
    final revision = _intentRevision;
    Map<Object?, Object?>? initial;
    try {
      initial = await _intents.invokeMapMethod<Object?, Object?>('get');
    } on Object {
      // Not on Android: no launch intent, so fall through to a plain connect.
    }
    if (revision == _intentRevision) await _dispatch(initial);
  }

  Future<void> _onNative(MethodCall call) async {
    if (call.method == 'onIntent') {
      _intentRevision++;
      await _dispatch(call.arguments as Map<Object?, Object?>?);
    }
  }

  Future<void> _dispatch(Map<Object?, Object?>? m) => widget.host.handle(
        m?['action'] as String?,
        {
          for (final e in ((m?['extras'] as Map?) ?? const {}).entries)
            e.key as String: (e.value as String?) ?? '',
        },
      );

  @override
  Widget build(BuildContext context) => ListenableBuilder(
        listenable: widget.host,
        builder: (context, _) {
          final s = widget.host.session;
          if (s != null) {
            return HomeShell(session: s, videoDecoder: widget.host.videoDecoder);
          }
          return Scaffold(
            appBar: AppBar(title: const Text('awto-dji')),
            body: Center(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(widget.host.status, textAlign: TextAlign.center),
              ),
            ),
          );
        },
      );
}
