import 'dart:typed_data';

import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:awto_dji_app/ui/diagnostics_screen.dart';
import 'package:duml/duml.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Minimal transport that just emits whatever bytes a test feeds it - no connect
/// logic, no write support (writes are exercised separately, in
/// gimbal_commands_test.dart / diagnostics_commands' own byte-shape, not here).
class _FakeTransport extends BaseTransport {
  @override
  String get name => 'fake';
  @override
  Future<void> connect() async => setState(LinkState.connected);
  @override
  Future<void> disconnect() async => setState(LinkState.disconnected);
}

Uint8List _osdWithMotorBlock() {
  final payload = Uint8List(60);
  final d = ByteData.sublistView(payload);
  d.setUint32(32, 1 << 27, Endian.little); // motorBlocked
  d.setUint8(38, 89); // MotorStartFailedCause.gimbalDisorder
  d.setUint8(47, 26); // flycVersion >= 26
  return DumlPacket(
    senderType: DeviceType.flightController,
    receiverType: DeviceType.app,
    sequence: 1,
    cmdSet: OsdGeneral.cmdSet,
    cmdId: OsdGeneral.cmdId,
    payload: payload,
  ).encode();
}

Uint8List _versionReply() {
  final payload = Uint8List(29);
  payload.setRange(1, 1 + 'FC-HW'.length, 'FC-HW'.codeUnits);
  payload[24] = 1; // firmware "01.00.00.00" (byte24 is the first printed digit pair)
  return DumlPacket(
    senderType: DeviceType.flightController,
    receiverType: DeviceType.app,
    packetType: PacketType.response,
    sequence: 2,
    cmdSet: CommonVersion.cmdSet,
    cmdId: CommonVersion.cmdId,
    payload: payload,
  ).encode();
}

void main() {
  testWidgets('shows motor-block/cause and a decoded version reply', (tester) async {
    final transport = _FakeTransport();
    final session = LinkSession(transport);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: DiagnosticsScreen(session: session))),
    );

    await tester.runAsync(() async {
      await session.start();
      transport.emit(_osdWithMotorBlock());
      transport.emit(_versionReply());
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(find.text('YES'), findsOneWidget); // motor blocked
    expect(find.textContaining('gimbalDisorder'), findsWidgets);
    expect(find.textContaining('fw 01.00.00.00'), findsOneWidget);
    expect(find.text('Gimbal self-test / auto-calibration'), findsOneWidget);

    await tester.runAsync(() async {
      await session.stop();
    });
    session.dispose();
  });
}
