import 'dart:async';
import 'dart:typed_data';

import 'package:duml/duml.dart';

import 'link_transport.dart';

/// A **command-responding** software fake aircraft (awto-dji #102, full-system emulation).
///
/// Unlike [SimulatedAircraftTransport] (which only pushes telemetry and rejects writes),
/// this decodes the DUML commands the app `write()`s and emits plausible replies — so the app
/// runs end-to-end against an emulated bird with no hardware. Responders are a
/// `(cmdSet, cmdId) -> reply` map; register more as they are modelled (from the canonical
/// catalog `docs/data/duml-catalog.json` and the capture corpus, #77). Ideal link, behavioral
/// device — the mixed-fidelity phase-0 of the full emulation; swap for the gate-level FPGA /
/// Renode later behind this same [LinkTransport] interface.
class FakeBirdTransport extends BaseTransport {
  FakeBirdTransport({this.deviceType = DeviceType.flightController}) {
    on(CmdSet.general, CommonVersion.cmdId, _getVersionReply);
  }

  /// Which device this bird answers as (its replies carry this `senderType`).
  final int deviceType;

  final Map<int, Uint8List Function(DumlPacket req)> _responders = {};

  @override
  String get name => 'fake-bird';

  static int _key(int cmdSet, int cmdId) => (cmdSet << 8) | cmdId;

  /// Register (or replace) the reply for one command. The function returns the encoded reply
  /// bytes, or null to answer nothing (a real device may stay silent on an unmodelled command).
  void on(int cmdSet, int cmdId, Uint8List? Function(DumlPacket req) reply) {
    _responders[_key(cmdSet, cmdId)] = (r) => reply(r) ?? Uint8List(0);
  }

  /// Commands this bird currently answers, as (cmdSet, cmdId) pairs — for tests / diagnostics.
  Iterable<(int, int)> get answered =>
      _responders.keys.map((k) => ((k >> 8) & 0xFF, k & 0xFF));

  @override
  Future<void> connect() async => setState(LinkState.connected);

  @override
  Future<void> disconnect() async => setState(LinkState.disconnected);

  /// The app sends a command here; decode it and emit the modelled reply (if any).
  @override
  Future<void> write(Uint8List data) async {
    final DumlPacket req;
    try {
      req = DumlPacket.decode(data);
    } catch (_) {
      return; // not a complete/valid frame — a real bird would ignore it
    }
    final reply = _responders[_key(req.cmdSet, req.cmdId)];
    if (reply != null) {
      final bytes = reply(req);
      if (bytes.isNotEmpty) emit(bytes);
    }
  }

  /// GetVersion (0x00/0x01): reply as [deviceType] with a [CommonVersion]-shaped payload.
  /// Round-trips through the real decoder; hardware string is the only field we set precisely.
  Uint8List _getVersionReply(DumlPacket req) {
    final payload = Uint8List(30); // >=30: the info int32 ends at offset 29
    final hw = 'FakeBird'.codeUnits;
    payload.setRange(2, 2 + hw.length, hw); // hw string at offset 2 (CommonVersion.fromPayload)
    return DumlPacket(
      senderType: deviceType,
      receiverType: DeviceType.app,
      sequence: req.sequence,
      packetType: PacketType.response,
      cmdSet: CmdSet.general,
      cmdId: CommonVersion.cmdId,
      payload: payload,
    ).encode();
  }
}
