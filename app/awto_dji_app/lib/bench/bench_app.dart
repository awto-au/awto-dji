import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'bench_controller.dart';
import 'bench_model.dart';

const _intents = MethodChannel('au.awto.dji/intents');

/// Generic AOA test app (device side). Top half: status grid; bottom half: activity log.
/// Imports no DJI GUI screens. Driven by intents (host/port extras) and host commands.
class BenchApp extends StatefulWidget {
  const BenchApp({super.key, this.controller});
  final BenchController? controller;

  @override
  State<BenchApp> createState() => _BenchAppState();
}

class _BenchAppState extends State<BenchApp> {
  late final BenchController _c = widget.controller ?? BenchController();
  final _scroll = ScrollController();
  int _intentRevision = 0;

  @override
  void initState() {
    super.initState();
    _intents.setMethodCallHandler((call) async {
      if (call.method == 'onIntent') {
        _intentRevision++;
        _dispatch(call.arguments as Map<Object?, Object?>?);
      }
    });
    _c.addListener(_follow);
    _boot();
  }

  Future<void> _boot() async {
    await _c.start();
    final rev = _intentRevision;
    Map<Object?, Object?>? initial;
    try {
      initial = await _intents.invokeMapMethod<Object?, Object?>('get');
    } on Object {
      // not on Android
    }
    if (rev == _intentRevision) _dispatch(initial);
  }

  void _dispatch(Map<Object?, Object?>? m) => _c.handleIntent(m?['action'] as String?, {
    for (final e in ((m?['extras'] as Map?) ?? const {}).entries)
      e.key as String: (e.value as String?) ?? '',
  });

  // Auto-follow: newest line at the bottom, always.
  void _follow() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  @override
  void dispose() {
    _intents.setMethodCallHandler(null);
    _c.removeListener(_follow);
    _scroll.dispose();
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => MaterialApp(
    title: 'awto-dji bench',
    debugShowCheckedModeBanner: false,
    theme: ThemeData.dark(useMaterial3: true).copyWith(scaffoldBackgroundColor: Colors.black),
    home: Scaffold(
      body: SafeArea(
        child: ListenableBuilder(
          listenable: _c,
          builder: (context, _) => Column(
            children: [
              Expanded(child: _Grid(s: _c.snapshot)),
              const Divider(height: 1, color: Colors.white24),
              Expanded(
                child: ListView.builder(
                  controller: _scroll,
                  padding: const EdgeInsets.all(4),
                  itemCount: _c.display.length,
                  itemBuilder: (_, i) => Text(_c.display[i], style: _mono(10, _lineColor(_c.display[i]))),
                ),
              ),
            ],
          ),
        ),
      ),
    ),
  );
}

TextStyle _mono(double size, [Color? c]) =>
    TextStyle(fontFamily: 'monospace', fontSize: size, color: c ?? Colors.white, height: 1.15);

Color _lineColor(String l) {
  final lvl = l.split(' ').elementAtOrNull(1);
  return switch (lvl) { 'E' => Colors.redAccent, 'W' => Colors.amber, _ => Colors.white70 };
}

class _Grid extends StatelessWidget {
  const _Grid({required this.s});
  final BenchSnapshot s;

  static String _n(num? v, [int d = 0]) => v == null ? '-' : v.toStringAsFixed(d);

  @override
  Widget build(BuildContext context) {
    final rows = <(String, String, Color?)>[
      ('PORT', '${s.port.name}${s.lastError != null ? '  ${s.lastError}' : ''}', _portColor(s.port)),
      ('USB', s.usbAttached ? 'attached  perm=${s.permission ? 'yes' : 'NO'}' : 'detached',
          s.usbAttached ? Colors.greenAccent : Colors.grey),
      ('  acc', '${s.manufacturer ?? '-'} / ${s.model ?? '-'} / ${s.description ?? '-'}', null),
      ('  acc', 'v=${s.version ?? '-'} uri=${s.uri ?? '-'} sn=${s.serial ?? '-'}', null),
      ('POWER', '${s.plugged} ${s.charging} ${_n(s.voltageMv)}mV ${_n(s.currentUa)}uA',
          s.plugged == 'none' ? Colors.grey : Colors.greenAccent),
      ('SPEED', '${s.speed}  udc=${s.udcSpeed ?? '-'}  maxpkt=${s.maxPacket ?? '-'} chunk=${s.maxChunk}', null),
      ('MSGS', '${_n(s.msgsPerSec1, 1)}/s 1s  ${_n(s.msgsPerSec10, 1)}/s 10s  ${_n(s.bytesPerSec1)}B/s', null),
      ('  tot', '${s.totalMsgs} msgs ${s.totalBytes}B  last ${_n(s.secSinceLast, 1)}s ago', null),
      ('  bad', 'crc=${s.crcBad} discarded=${s.discardedBytes}B', s.crcBad > 0 ? Colors.amber : null),
      ('MODE', '${s.mode} test=${s.testId} frames=${s.testFrames} ${s.testBytes}B bad=${s.testBad}'
          '${s.firstMismatchOffset != null ? ' first@${s.firstMismatchOffset}' : ''}'
          '${s.testPass == null ? '' : s.testPass! ? '  PASS' : '  FAIL'}',
          s.testPass == false ? Colors.redAccent : s.testPass == true ? Colors.greenAccent : null),
      ('HOST', s.hostConnected ? 'connected rtt=${_n(s.hostRttMs)}ms' : 'not connected',
          s.hostConnected ? Colors.greenAccent : Colors.grey),
    ];
    return ListView(
      padding: const EdgeInsets.all(6),
      physics: const NeverScrollableScrollPhysics(),
      children: [
        for (final (k, v, c) in rows)
          Text.rich(TextSpan(children: [
            TextSpan(text: '${k.padRight(6)} ', style: _mono(13, Colors.white54)),
            TextSpan(text: v, style: _mono(13, c)),
          ])),
      ],
    );
  }

  static Color? _portColor(PortState p) => switch (p) {
    PortState.streaming => Colors.greenAccent,
    PortState.connected => Colors.lightGreen,
    PortState.failed => Colors.redAccent,
    PortState.permission => Colors.amber,
    PortState.attached => Colors.lightBlueAccent,
    PortState.idle => Colors.grey,
  };
}
