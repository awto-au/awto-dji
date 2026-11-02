import 'dart:async';
import 'dart:io';
import 'package:duml/duml.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import '../transport/aoa_identity.dart';
import '../transport/aoa_mux.dart';
import '../transport/aoa_transport.dart';
import 'bench_host_client.dart';
import 'bench_model.dart';
import 'bench_modes.dart';

/// Build tag shown in `hello`.
const benchBuild = '1.0.0+1';
const benchApp = 'awto-dji-bench';

/// AOA-device side of the bench: owns the accessory pump, stats, log ring and the host
/// link. Uses the existing [AoaMux], [AoaIdentity] and channel names unchanged; it does
/// not use AoaTransport because that hides envelope-level facts (channel, length, CRC)
/// the bench has to report.
///
/// Bounds (waits for / expected / multiplier / on expiry):
/// - tick 500 ms: poll USB + power and push `state` (2 Hz grid refresh, as specified).
/// - [streamingWindowMs] 2000: "streaming" = last envelope within 2 s; the RC link is
///   ~10s of msgs/s when live, so 2 s is well past 1 missed second; expiry -> "connected".
/// - accessory retry backoff 1 s, 2 s, 4 s, 8 s cap: AoaShim.connect fails in <= 3 s
///   (permission wait), the retry only needs to be ahead of a human tapping the dialog;
///   8 s cap bounds the wait after the dialog is answered. Resets on success.
/// - ping to host every 2 s: an RTT sample at 0.5 Hz is plenty for a WiFi link;
///   unanswered by the next ping -> RTT shown as unknown.
class BenchController extends ChangeNotifier {
  BenchController({
    MethodChannel? aoa,
    EventChannel? events,
    MethodChannel? bench,
    int Function()? nowMs,
    this.tick = const Duration(milliseconds: 500),
  }) : _aoa = aoa ?? const MethodChannel(AoaTransport.methodChannelName),
       _events = events ?? const EventChannel(AoaTransport.eventChannelName),
       _bench = bench ?? const MethodChannel('au.awto.dji/bench'),
       _sw = Stopwatch()..start() {
    _nowMs = nowMs ?? () => _sw.elapsedMilliseconds;
    _mux.onPacket = _onPacket;
    engine = ModeEngine(
      write: _write,
      nowMs: _nowMs,
      log: _log,
      onResult: (b) {
        _log('I', 'result ${b['mode']} test=${b['test']} pass=${b['pass']} frames=${b['frames']} bytes=${b['bytes']}');
        _hostClient?.send(ResultMsg(b));
      },
    );
  }

  static const logRing = 2000;
  static const streamingWindowMs = 2000;

  final MethodChannel _aoa, _bench;
  final EventChannel _events;
  final Duration tick;
  final Stopwatch _sw;
  late final int Function() _nowMs;
  final _mux = AoaMux();
  late final ModeEngine engine;
  int _maxChunk = 0;
  final _rate = RateWindow();
  final List<String> lines = [];

  /// What the screen draws: the same lines with elapsed time `mm:ss.mmm` since the
  /// controller started, so a line wraps less. The file and the host get the full ISO form.
  final List<String> display = [];
  final DateTime _t0 = DateTime.now();

  static String elapsed(Duration d) {
    String two(int v) => v.toString().padLeft(2, '0');
    return '${two(d.inMinutes)}:${two(d.inSeconds % 60)}.${(d.inMilliseconds % 1000).toString().padLeft(3, '0')}';
  }

  Timer? _timer;
  StreamSubscription<dynamic>? _sub;
  BenchHostClient? _hostClient;
  IOSink? _fileSink;

  bool _open = false;
  bool _connecting = false;
  bool _autoConnect = true;
  int _nextAttemptMs = 0;
  Duration _retryBackoff = const Duration(seconds: 1);
  String? _error;
  bool _echo = false;
  int _crcBad = 0;
  int _rxLogged = 0;
  int _pingId = 0;
  int? _pingSentMs;
  int _pendingPingId = -1;
  int? _rttMs;
  bool _hostUp = false;
  Map<Object?, Object?> _usb = const {};
  Map<Object?, Object?> _power = const {};
  BenchSnapshot snapshot = const BenchSnapshot();
  BenchSnapshot? _lastSent;
  int _lastStateSentMs = -1000;

  /// Test hook: bytes the "write" channel call would have sent.
  final List<Uint8List> written = [];

  Future<void> start() async {
    try {
      final dir = await _bench.invokeMethod<String>('logDir');
      if (dir != null) {
        _fileSink = File('$dir/bench.log').openWrite(mode: FileMode.append);
      }
    } on Object catch (e) {
      debugPrint('[bench] no log file: $e');
    }
    _log('I', 'bench start $benchApp $benchBuild');
    _timer = Timer.periodic(tick, (_) => _onTick());
    _onTick();
  }

  // ---- intents ---------------------------------------------------------------

  /// CONNECT / BENCH carry host + port; DISCONNECT stops the accessory. Anything else
  /// (MAIN, USB_ACCESSORY_ATTACHED) just re-enables auto-connect.
  void handleIntent(String? action, Map<String, String> extras) {
    _log('I', 'intent ${action ?? 'null'} $extras');
    switch (action) {
      case 'au.awto.dji.action.CONNECT':
      case 'au.awto.dji.action.BENCH':
        final h = extras['host'], p = int.tryParse(extras['port'] ?? '');
        if (h != null && h.isNotEmpty && p != null) setHost(h, p);
        _autoConnect = true;
      case 'au.awto.dji.action.DISCONNECT':
        _autoConnect = false;
        unawaited(_closeAccessory('intent DISCONNECT'));
      default:
        _autoConnect = true;
    }
  }

  void setHost(String host, int port) {
    unawaited(_hostClient?.stop());
    _log('I', 'host target $host:$port');
    _hostClient = BenchHostClient(
      host: host,
      port: port,
      onCmd: _onHostCmd,
      onConnection: _onHostConnection,
      log: _log,
    )..start();
  }

  void _onHostConnection(bool up) {
    _hostUp = up;
    if (up) {
      _hostClient?.send(const HelloMsg(benchApp, benchBuild));
      // Replay the ring so a late-attaching script sees the history.
      for (final l in lines) {
        _hostClient?.send(_lineToMsg(l));
      }
      _lastSent = null;
    } else {
      _rttMs = null;
    }
    _refresh(force: true);
  }

  // ---- host commands -----------------------------------------------------------

  void _onHostCmd(HostCmd c) {
    switch (c) {
      case PingCmd(:final id):
        _hostClient?.send(PongMsg(id));
      case PongCmd(:final id):
        if (id == _pendingPingId && _pingSentMs != null) {
          _rttMs = _nowMs() - _pingSentMs!;
          _pingSentMs = null;
        }
      case SendCmd(:final bytes):
        _log('I', 'host send ${bytes.length}B');
        unawaited(_write(Uint8List.fromList(bytes)));
      case EchoCmd(:final on):
        _echo = on;
        _log('I', 'echo ${on ? 'on' : 'off'}');
      case ModeCmd():
        engine.setMode(c);
      case ResultCmd():
        engine.emitResult();
      case StatsResetCmd():
        _rate.reset();
        _maxChunk = 0;
        _crcBad = 0;
        _mux.discarded = 0;
        _rxLogged = 0;
        _log('I', 'stats reset');
      case DisconnectCmd():
        _autoConnect = false;
        unawaited(_closeAccessory('host disconnect'));
      case ReconnectCmd():
        _autoConnect = true;
        _retryBackoff = const Duration(seconds: 1);
        _nextAttemptMs = 0;
        unawaited(_closeAccessory('host reconnect').then((_) => _maybeConnect()));
    }
    _refresh(force: true);
  }

  // ---- accessory ---------------------------------------------------------------

  Future<void> _write(Uint8List data) async {
    written.add(data);
    try {
      await _aoa.invokeMethod<void>('write', data);
    } on PlatformException catch (e) {
      _log('E', 'write failed: ${e.code} ${e.message}');
    } on MissingPluginException {
      _log('E', 'write: not available on this platform');
    }
  }

  void _maybeConnect() {
    if (!_autoConnect || _open || _connecting) return;
    if (_usb['attached'] != true) return;
    if (_nowMs() < _nextAttemptMs) return;
    unawaited(_connectAccessory());
  }

  Future<void> _connectAccessory() async {
    _connecting = true;
    _mux.reset();
    _log('I', 'connecting accessory ${AoaIdentity.manufacturer}/${AoaIdentity.model}');
    try {
      _sub = _events.receiveBroadcastStream().listen(
        ingest,
        onError: (Object e) {
          _log('E', 'accessory stream error: $e');
          _error = '$e';
          unawaited(_closeAccessory('stream error'));
        },
        onDone: () {
          _log('W', 'accessory stream ended');
          unawaited(_closeAccessory('stream ended'));
        },
      );
      await _aoa.invokeMethod<void>('connect', <String, String>{
        'manufacturer': AoaIdentity.manufacturer,
        'model': AoaIdentity.model,
      });
      _open = true;
      _error = null;
      _retryBackoff = const Duration(seconds: 1);
      _log('I', 'accessory open');
    } on PlatformException catch (e) {
      _error = '${e.code}: ${e.message}';
      _log('E', 'connect failed: $_error');
      await _sub?.cancel();
      _sub = null;
      _backoff();
    } on MissingPluginException {
      _error = 'not available on this platform';
      _log('E', _error!);
      await _sub?.cancel();
      _sub = null;
      _backoff();
    } finally {
      _connecting = false;
      _refresh(force: true);
    }
  }

  void _backoff() {
    _nextAttemptMs = _nowMs() + _retryBackoff.inMilliseconds;
    final next = _retryBackoff * 2;
    _retryBackoff = next > const Duration(seconds: 8) ? const Duration(seconds: 8) : next;
  }

  Future<void> _closeAccessory(String why) async {
    final was = _open;
    _open = false;
    await _sub?.cancel();
    _sub = null;
    _mux.finish();
    engine.reset();
    try {
      await _aoa.invokeMethod<void>('disconnect');
    } on Object {
      // already closed / not on Android
    }
    if (was) _log('I', 'accessory closed ($why)');
    if (why.contains('error') || why.contains('ended')) _backoff();
    _refresh(force: true);
  }

  /// Entry for raw accessory bytes (also the test hook).
  void ingest(dynamic chunk) {
    final b = chunk as Uint8List;
    if (b.length > _maxChunk) _maxChunk = b.length;
    // passive + duml go through the AOA envelope mux; echo/sink/source see raw chunks
    // (an empty chunk is a zero-length packet and only the raw modes count it).
    if (engine.mode == BenchMode.passive || engine.mode == BenchMode.duml) {
      if (b.isNotEmpty) _mux.add(b);
    } else {
      engine.onChunk(b);
    }
  }

  void _onPacket(AoaPacket p) {
    final now = _nowMs();
    final ok = p.channel != AoaMux.command || _dumlOk(p.payload);
    _rate.record(now, p.payload.length);
    if (!ok) _crcBad++;
    if (p.channel == AoaMux.command) engine.onDuml(p.payload, ok);
    _hostClient?.send(RxMsg(p.channel, p.payload.length, ok));
    if (_rxLogged < 20) {
      _rxLogged++;
      _log(
        ok ? 'I' : 'W',
        'rx ch=0x${p.channel.toRadixString(16)} len=${p.payload.length} crc_ok=$ok'
        '${_rxLogged == 20 ? ' (further rx not logged; see msgs/s)' : ''}',
      );
    }
    if (_echo) unawaited(_write(p.payload));
  }

  /// DUML CRC8 over the 3-byte header prefix and CRC16 over the frame.
  static bool _dumlOk(Uint8List b) {
    if (b.length < 13 || b[0] != 0x55) return false;
    final len = (b[1] | (b[2] << 8)) & 0x3FF;
    if (len < 13 || len > b.length) return false;
    if (headerCrc8(b.sublist(0, 3)) != b[3]) return false;
    final frame = b.sublist(0, len);
    return packetCrc16(frame, len) == (frame[len - 2] | (frame[len - 1] << 8));
  }

  // ---- periodic -------------------------------------------------------------------

  Future<void> _onTick() async {
    try {
      _usb = await _bench.invokeMapMethod<Object?, Object?>('usbInfo') ?? const {};
      _power = await _bench.invokeMapMethod<Object?, Object?>('power') ?? const {};
    } on Object {
      // not on Android: leave the grid at defaults
    }
    if (_usb['attached'] != true && _open) unawaited(_closeAccessory('detached'));
    _maybeConnect();
    _pingHost();
    _refresh();
  }

  void _pingHost() {
    if (!_hostUp) return;
    final now = _nowMs();
    if (_pingSentMs != null && now - _pingSentMs! >= 2000) _rttMs = null;
    if (_pingSentMs != null && now - _pingSentMs! < 2000) return;
    _pendingPingId = ++_pingId;
    _pingSentMs = now;
    _hostClient?.send(AppPingMsg(_pendingPingId));
  }

  PortState _portState() {
    final attached = _usb['attached'] == true;
    if (_open) {
      final since = _rate.secondsSinceLast(_nowMs());
      return since != null && since * 1000 <= streamingWindowMs
          ? PortState.streaming
          : PortState.connected;
    }
    if (_error != null && attached) {
      return _error!.startsWith('permission') ? PortState.permission : PortState.failed;
    }
    if (!attached) return PortState.idle;
    return _usb['permission'] == true ? PortState.attached : PortState.permission;
  }

  void _refresh({bool force = false}) {
    final now = _nowMs();
    final g = engine.grid();
    final s = BenchSnapshot(
      usbAttached: _usb['attached'] == true,
      manufacturer: _usb['manufacturer'] as String?,
      model: _usb['model'] as String?,
      description: _usb['description'] as String?,
      version: _usb['version'] as String?,
      uri: _usb['uri'] as String?,
      serial: _usb['serial'] as String?,
      permission: _usb['permission'] == true,
      maxPacket: _usb['maxPacket'] as int?,
      udcSpeed: _usb['udcSpeed'] as String?,
      maxChunk: _maxChunk,
      plugged: _power['plugged'] as String? ?? 'none',
      charging: _power['charging'] as String? ?? 'unknown',
      voltageMv: _power['voltageMv'] as int?,
      currentUa: _power['currentUa'] as int?,
      msgsPerSec1: _rate.msgsPerSec(now, 1000),
      msgsPerSec10: _rate.msgsPerSec(now, 10000),
      bytesPerSec1: _rate.bytesPerSec(now, 1000),
      bytesPerSec10: _rate.bytesPerSec(now, 10000),
      totalMsgs: _rate.total,
      totalBytes: _rate.totalBytes,
      secSinceLast: _rate.secondsSinceLast(now),
      crcBad: _crcBad,
      discardedBytes: _mux.discarded,
      port: _portState(),
      lastError: _error,
      hostConnected: _hostUp,
      hostRttMs: _rttMs,
      echo: _echo,
      mode: engine.mode.name,
      testId: engine.testId,
      testFrames: g.frames,
      testBytes: g.bytes,
      testBad: g.bad,
      firstMismatchOffset: g.firstOffset,
      testPass: g.pass,
    );
    final changed = _lastSent == null || !s.sameDiscrete(_lastSent!);
    if (snapshot.port != s.port) {
      _log('I', 'port ${snapshot.port.name} -> ${s.port.name}');
    }
    snapshot = s;
    // Immediate push on discrete change, otherwise at the 500 ms tick (>= tick - 50 ms
    // guard so a forced refresh right after a tick does not double up).
    if (changed || force || now - _lastStateSentMs >= tick.inMilliseconds - 50) {
      _hostClient?.send(StateMsg(s));
      _lastSent = s;
      _lastStateSentMs = now;
    }
    notifyListeners();
  }

  // ---- log ------------------------------------------------------------------------

  static String isoNow() {
    final n = DateTime.now();
    final o = n.timeZoneOffset;
    String two(int v) => v.abs().toString().padLeft(2, '0');
    final off = '${o.isNegative ? '-' : '+'}${two(o.inHours)}:${two(o.inMinutes % 60)}';
    final ms = n.millisecond.toString().padLeft(3, '0');
    return '${n.year}-${two(n.month)}-${two(n.day)}T${two(n.hour)}:${two(n.minute)}:${two(n.second)}.$ms$off';
  }

  void _log(String lvl, String msg) {
    final ts = isoNow();
    final line = '$ts $lvl $msg';
    lines.add(line);
    if (lines.length > logRing) lines.removeRange(0, lines.length - logRing);
    display.add('${elapsed(DateTime.now().difference(_t0))} $lvl $msg');
    if (display.length > logRing) display.removeRange(0, display.length - logRing);
    _fileSink?.writeln(line);
    _hostClient?.send(LogMsg(ts, lvl, msg));
    debugPrint('[bench] $line');
    notifyListeners();
  }

  LogMsg _lineToMsg(String l) {
    final i = l.indexOf(' ');
    final j = l.indexOf(' ', i + 1);
    if (i < 0 || j < 0) return LogMsg('', 'I', l);
    return LogMsg(l.substring(0, i), l.substring(i + 1, j), l.substring(j + 1));
  }

  @override
  void dispose() {
    _timer?.cancel();
    unawaited(_hostClient?.stop());
    unawaited(_sub?.cancel());
    unawaited(_fileSink?.close());
    super.dispose();
  }
}
