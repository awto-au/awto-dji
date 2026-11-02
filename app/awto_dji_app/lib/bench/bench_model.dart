import 'dart:convert';

/// Pure-Dart state model + wire protocol of the AOA bench app (no Flutter imports).
/// Protocol: docs/phone-bridge-operator-guide.md "AOA bench app"; host side
/// scripts/re/bench_host.py.

/// Port state of the AOA device side. Derived from the transport's LinkState
/// (connecting/connected/failed) plus accessory presence and permission.
enum PortState { idle, attached, permission, connected, streaming, failed }

/// Bulk endpoint max packet -> USB speed. Android does not expose the speed to apps;
/// 512 = high speed, 64 = full speed. Always a guess, so the label says so.
String inferSpeed(int? maxPacket) => switch (maxPacket) {
  512 => 'high-speed 480M (inferred)',
  64 => 'full-speed 12M (inferred)',
  1024 => 'super-speed 5G (inferred)',
  null => 'unknown (no max packet)',
  final v => 'unknown (max packet $v)',
};

/// Sliding-window event counter. Time is passed in (monotonic ms) so tests need no clock.
class RateWindow {
  RateWindow({this.maxWindowMs = 10000});
  final int maxWindowMs;
  final List<(int, int)> _events = []; // (atMs, bytes)
  int total = 0;
  int totalBytes = 0;
  int? lastAtMs;

  void record(int nowMs, int bytes) {
    _events.add((nowMs, bytes));
    total++;
    totalBytes += bytes;
    lastAtMs = nowMs;
    _trim(nowMs);
  }

  void _trim(int nowMs) {
    var drop = 0;
    while (drop < _events.length && _events[drop].$1 <= nowMs - maxWindowMs) {
      drop++;
    }
    if (drop > 0) _events.removeRange(0, drop);
  }

  /// Messages per second over the last [windowMs] (<= maxWindowMs).
  double msgsPerSec(int nowMs, int windowMs) {
    _trim(nowMs);
    final n = _events.where((e) => e.$1 > nowMs - windowMs).length;
    return n * 1000 / windowMs;
  }

  double bytesPerSec(int nowMs, int windowMs) {
    _trim(nowMs);
    final n = _events
        .where((e) => e.$1 > nowMs - windowMs)
        .fold<int>(0, (a, e) => a + e.$2);
    return n * 1000 / windowMs;
  }

  /// Seconds since the last message, null if none yet.
  double? secondsSinceLast(int nowMs) =>
      lastAtMs == null ? null : (nowMs - lastAtMs!) / 1000;

  void reset() {
    _events.clear();
    total = 0;
    totalBytes = 0;
    lastAtMs = null;
  }
}

/// Everything the heads-up grid shows. [toJson] is the `state` message body.
class BenchSnapshot {
  const BenchSnapshot({
    this.usbAttached = false,
    this.manufacturer,
    this.model,
    this.description,
    this.version,
    this.uri,
    this.serial,
    this.permission = false,
    this.maxPacket,
    this.udcSpeed,
    this.maxChunk = 0,
    this.plugged = 'none',
    this.charging = 'unknown',
    this.voltageMv,
    this.currentUa,
    this.msgsPerSec1 = 0,
    this.msgsPerSec10 = 0,
    this.bytesPerSec1 = 0,
    this.bytesPerSec10 = 0,
    this.totalMsgs = 0,
    this.totalBytes = 0,
    this.secSinceLast,
    this.crcBad = 0,
    this.discardedBytes = 0,
    this.port = PortState.idle,
    this.lastError,
    this.hostConnected = false,
    this.hostRttMs,
    this.echo = false,
    this.mode = 'passive',
    this.testId = 0,
    this.testFrames = 0,
    this.testBytes = 0,
    this.testBad = 0,
    this.firstMismatchOffset,
    this.testPass,
  });

  final bool usbAttached;
  final String? manufacturer, model, description, version, uri, serial;
  final bool permission;
  final int? maxPacket;

  /// /sys/class/udc/*/current_speed when readable (best effort), else null.
  final String? udcSpeed;

  /// Largest single read seen on the accessory (bytes); a hint only, reads may coalesce.
  final int maxChunk;
  final String plugged; // usb / ac / wireless / none
  final String charging; // charging / discharging / full / not_charging / unknown
  final int? voltageMv, currentUa;
  final double msgsPerSec1, msgsPerSec10, bytesPerSec1, bytesPerSec10;
  final int totalMsgs, totalBytes, crcBad, discardedBytes;
  final double? secSinceLast;
  final PortState port;
  final String? lastError;
  final bool hostConnected;
  final int? hostRttMs;
  final bool echo;

  /// Test mode (passive/echo/sink/source/duml) and its running verdict.
  final String mode;
  final int testId, testFrames, testBytes, testBad;
  final int? firstMismatchOffset;
  final bool? testPass;

  String get speed => inferSpeed(maxPacket);

  Map<String, Object?> toJson() => {
    't': 'state',
    'usb': {
      'attached': usbAttached,
      'manufacturer': manufacturer,
      'model': model,
      'description': description,
      'version': version,
      'uri': uri,
      'serial': serial,
      'permission': permission,
      'max_packet': maxPacket,
    },
    'power': {
      'plugged': plugged,
      'charging': charging,
      'voltage_mv': voltageMv,
      'current_ua': currentUa,
    },
    'speed': {'label': speed, 'max_packet': maxPacket, 'udc': udcSpeed, 'max_chunk': maxChunk},
    'msgs': {
      'per_s_1': msgsPerSec1,
      'per_s_10': msgsPerSec10,
      'bytes_per_s_1': bytesPerSec1,
      'bytes_per_s_10': bytesPerSec10,
      'total': totalMsgs,
      'total_bytes': totalBytes,
      'sec_since_last': secSinceLast,
      'crc_bad': crcBad,
      'discarded_bytes': discardedBytes,
    },
    'port': {'state': port.name, 'last_error': lastError},
    'host': {'connected': hostConnected, 'rtt_ms': hostRttMs},
    'echo': echo,
    'mode': {
      'm': mode,
      'test': testId,
      'frames': testFrames,
      'bytes': testBytes,
      'bad': testBad,
      'first_mismatch': firstMismatchOffset,
      'pass': testPass,
    },
  };

  /// Inverse of [toJson]; unknown/missing fields fall back to defaults.
  factory BenchSnapshot.fromJson(Map<String, Object?> j) {
    Map<String, Object?> sub(String k) =>
        (j[k] as Map?)?.cast<String, Object?>() ?? const {};
    final usb = sub('usb'), power = sub('power'), speed = sub('speed');
    final msgs = sub('msgs'), port = sub('port'), host = sub('host');
    final mode = sub('mode');
    double d(Object? v) => (v as num?)?.toDouble() ?? 0;
    return BenchSnapshot(
      usbAttached: usb['attached'] as bool? ?? false,
      manufacturer: usb['manufacturer'] as String?,
      model: usb['model'] as String?,
      description: usb['description'] as String?,
      version: usb['version'] as String?,
      uri: usb['uri'] as String?,
      serial: usb['serial'] as String?,
      permission: usb['permission'] as bool? ?? false,
      maxPacket: (usb['max_packet'] as num?)?.toInt(),
      udcSpeed: speed['udc'] as String?,
      maxChunk: (speed['max_chunk'] as num?)?.toInt() ?? 0,
      plugged: power['plugged'] as String? ?? 'none',
      charging: power['charging'] as String? ?? 'unknown',
      voltageMv: (power['voltage_mv'] as num?)?.toInt(),
      currentUa: (power['current_ua'] as num?)?.toInt(),
      msgsPerSec1: d(msgs['per_s_1']),
      msgsPerSec10: d(msgs['per_s_10']),
      bytesPerSec1: d(msgs['bytes_per_s_1']),
      bytesPerSec10: d(msgs['bytes_per_s_10']),
      totalMsgs: (msgs['total'] as num?)?.toInt() ?? 0,
      totalBytes: (msgs['total_bytes'] as num?)?.toInt() ?? 0,
      secSinceLast: (msgs['sec_since_last'] as num?)?.toDouble(),
      crcBad: (msgs['crc_bad'] as num?)?.toInt() ?? 0,
      discardedBytes: (msgs['discarded_bytes'] as num?)?.toInt() ?? 0,
      port: PortState.values.firstWhere(
        (p) => p.name == port['state'],
        orElse: () => PortState.idle,
      ),
      lastError: port['last_error'] as String?,
      hostConnected: host['connected'] as bool? ?? false,
      hostRttMs: (host['rtt_ms'] as num?)?.toInt(),
      echo: j['echo'] as bool? ?? false,
      mode: mode['m'] as String? ?? 'passive',
      testId: (mode['test'] as num?)?.toInt() ?? 0,
      testFrames: (mode['frames'] as num?)?.toInt() ?? 0,
      testBytes: (mode['bytes'] as num?)?.toInt() ?? 0,
      testBad: (mode['bad'] as num?)?.toInt() ?? 0,
      firstMismatchOffset: (mode['first_mismatch'] as num?)?.toInt(),
      testPass: mode['pass'] as bool?,
    );
  }

  /// Equality ignoring the always-changing rate/age fields: "changed" for the
  /// immediate-state-on-change push.
  bool sameDiscrete(BenchSnapshot o) =>
      usbAttached == o.usbAttached &&
      manufacturer == o.manufacturer &&
      model == o.model &&
      description == o.description &&
      version == o.version &&
      uri == o.uri &&
      serial == o.serial &&
      permission == o.permission &&
      maxPacket == o.maxPacket &&
      plugged == o.plugged &&
      charging == o.charging &&
      port == o.port &&
      lastError == o.lastError &&
      hostConnected == o.hostConnected &&
      echo == o.echo &&
      mode == o.mode &&
      testPass == o.testPass &&
      firstMismatchOffset == o.firstMismatchOffset;
}

// ---- app -> host messages ---------------------------------------------------

sealed class AppMsg {
  const AppMsg();
  Map<String, Object?> toJson();
  String encode() => jsonEncode(toJson());

  static AppMsg? decode(String line) {
    final Object? j;
    try {
      j = jsonDecode(line);
    } on FormatException {
      return null;
    }
    if (j is! Map<String, Object?>) return null;
    switch (j['t']) {
      case 'hello':
        return HelloMsg(j['app'] as String? ?? '', j['build'] as String? ?? '');
      case 'state':
        return StateMsg(BenchSnapshot.fromJson(j));
      case 'log':
        return LogMsg(
          j['ts'] as String? ?? '',
          j['lvl'] as String? ?? 'I',
          j['msg'] as String? ?? '',
        );
      case 'rx':
        return RxMsg(
          (j['ch'] as num?)?.toInt() ?? 0,
          (j['len'] as num?)?.toInt() ?? 0,
          j['crc_ok'] as bool? ?? false,
        );
      case 'result':
        return ResultMsg(Map.of(j)..remove('t'));
      case 'pong':
        return PongMsg((j['id'] as num?)?.toInt() ?? 0);
      case 'ping':
        return AppPingMsg((j['id'] as num?)?.toInt() ?? 0);
    }
    return null;
  }
}

class HelloMsg extends AppMsg {
  const HelloMsg(this.app, this.build);
  final String app, build;
  @override
  Map<String, Object?> toJson() => {'t': 'hello', 'app': app, 'build': build};
}

class StateMsg extends AppMsg {
  const StateMsg(this.snapshot);
  final BenchSnapshot snapshot;
  @override
  Map<String, Object?> toJson() => snapshot.toJson();
}

class LogMsg extends AppMsg {
  const LogMsg(this.ts, this.lvl, this.msg);
  final String ts, lvl, msg;
  @override
  Map<String, Object?> toJson() => {
    't': 'log',
    'ts': ts,
    'lvl': lvl,
    'msg': msg,
  };
}

class RxMsg extends AppMsg {
  const RxMsg(this.ch, this.len, this.crcOk);
  final int ch, len;
  final bool crcOk;
  @override
  Map<String, Object?> toJson() => {
    't': 'rx',
    'ch': ch,
    'len': len,
    'crc_ok': crcOk,
  };
}

/// Per-test verdict: `{t:result, test, mode, frames, bytes, bad_frames, first_mismatch,
/// pass, ...}`. Body keys are free-form beyond those.
class ResultMsg extends AppMsg {
  const ResultMsg(this.body);
  final Map<String, Object?> body;
  @override
  Map<String, Object?> toJson() => {'t': 'result', ...body};
}

/// Answer to a host `ping` command.
class PongMsg extends AppMsg {
  const PongMsg(this.id);
  final int id;
  @override
  Map<String, Object?> toJson() => {'t': 'pong', 'id': id};
}

/// App-initiated ping; the host answers with `{"cmd":"pong","id":N}` so the app
/// can show a round-trip time in the grid.
class AppPingMsg extends AppMsg {
  const AppPingMsg(this.id);
  final int id;
  @override
  Map<String, Object?> toJson() => {'t': 'ping', 'id': id};
}

// ---- host -> app commands ---------------------------------------------------

sealed class HostCmd {
  const HostCmd();
  Map<String, Object?> toJson();
  String encode() => jsonEncode(toJson());

  /// Null for malformed lines or unknown commands (caller logs them).
  static HostCmd? decode(String line) {
    final Object? j;
    try {
      j = jsonDecode(line);
    } on FormatException {
      return null;
    }
    if (j is! Map<String, Object?>) return null;
    switch (j['cmd']) {
      case 'ping':
        return PingCmd((j['id'] as num?)?.toInt() ?? 0);
      case 'pong':
        return PongCmd((j['id'] as num?)?.toInt() ?? 0);
      case 'send':
        final bytes = decodeHex(j['hex'] as String? ?? '');
        return bytes == null ? null : SendCmd(bytes);
      case 'echo':
        return EchoCmd(j['on'] as bool? ?? false);
      case 'mode':
        return j['m'] is String ? ModeCmd(Map.of(j)..remove('cmd')) : null;
      case 'result':
        return const ResultCmd();
      case 'stats_reset':
        return const StatsResetCmd();
      case 'disconnect':
        return const DisconnectCmd();
      case 'reconnect':
        return const ReconnectCmd();
    }
    return null;
  }
}

class PingCmd extends HostCmd {
  const PingCmd(this.id);
  final int id;
  @override
  Map<String, Object?> toJson() => {'cmd': 'ping', 'id': id};
}

class PongCmd extends HostCmd {
  const PongCmd(this.id);
  final int id;
  @override
  Map<String, Object?> toJson() => {'cmd': 'pong', 'id': id};
}

class SendCmd extends HostCmd {
  const SendCmd(this.bytes);
  final List<int> bytes;
  @override
  Map<String, Object?> toJson() => {'cmd': 'send', 'hex': encodeHex(bytes)};
}

class EchoCmd extends HostCmd {
  const EchoCmd(this.on);
  final bool on;
  @override
  Map<String, Object?> toJson() => {'cmd': 'echo', 'on': on};
}

/// `{cmd:mode, m:echo|sink|source|duml|passive, ...params}`; params in docs.
class ModeCmd extends HostCmd {
  const ModeCmd(this.params);
  final Map<String, Object?> params;
  String get m => params['m'] as String;
  @override
  Map<String, Object?> toJson() => {'cmd': 'mode', ...params};
}

/// Ask the app to emit a `result` now (the test keeps running).
class ResultCmd extends HostCmd {
  const ResultCmd();
  @override
  Map<String, Object?> toJson() => {'cmd': 'result'};
}

class StatsResetCmd extends HostCmd {
  const StatsResetCmd();
  @override
  Map<String, Object?> toJson() => {'cmd': 'stats_reset'};
}

class DisconnectCmd extends HostCmd {
  const DisconnectCmd();
  @override
  Map<String, Object?> toJson() => {'cmd': 'disconnect'};
}

class ReconnectCmd extends HostCmd {
  const ReconnectCmd();
  @override
  Map<String, Object?> toJson() => {'cmd': 'reconnect'};
}

String encodeHex(List<int> b) =>
    b.map((v) => v.toRadixString(16).padLeft(2, '0')).join();

/// Hex (whitespace allowed) -> bytes; null if odd length or non-hex.
List<int>? decodeHex(String s) {
  final h = s.replaceAll(RegExp(r'\s'), '');
  if (h.length.isOdd || !RegExp(r'^[0-9a-fA-F]*$').hasMatch(h)) return null;
  return [for (var i = 0; i < h.length; i += 2) int.parse(h.substring(i, i + 2), radix: 16)];
}
