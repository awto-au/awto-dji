import 'dart:typed_data';

import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:awto_dji_app/ui/camera_screen.dart';
import 'package:duml/duml.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

/// Transport that emits whatever bytes a test feeds it and records writes -
/// diagnostics_screen_test.dart's fixture doesn't need the write side, but
/// confirming a button press actually sends a frame does.
class _FakeTransport extends BaseTransport {
  final List<Uint8List> written = [];

  @override
  String get name => 'fake';
  @override
  Future<void> connect() async => setState(LinkState.connected);
  @override
  Future<void> disconnect() async => setState(LinkState.disconnected);
  @override
  Future<void> write(Uint8List data) async => written.add(data);
}

Uint8List _aeLockReply(bool locked) => DumlPacket(
      senderType: DeviceType.camera,
      receiverType: DeviceType.app,
      packetType: PacketType.response,
      sequence: 1,
      cmdSet: CameraAeLock.cmdSet,
      cmdId: CameraAeLock.cmdId,
      payload: Uint8List.fromList([locked ? 1 : 0]),
    ).encode();

Uint8List _exposureCompensationReply(int rawStep) => DumlPacket(
      senderType: DeviceType.camera,
      receiverType: DeviceType.app,
      packetType: PacketType.response,
      sequence: 2,
      cmdSet: CameraExposureCompensation.cmdSet,
      cmdId: CameraExposureCompensation.cmdId,
      payload: Uint8List.fromList([rawStep]),
    ).encode();

void main() {
  testWidgets('shows decoded AE-lock and EV compensation replies', (tester) async {
    final transport = _FakeTransport();
    final session = LinkSession(transport);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: CameraScreen(session: session))),
    );

    await tester.runAsync(() async {
      await session.start();
      transport.emit(_aeLockReply(true));
      transport.emit(_exposureCompensationReply(19)); // +1.0 EV
      await Future<void>.delayed(Duration.zero);
    });
    await tester.pump();

    expect(find.text('locked'), findsOneWidget);
    expect(find.textContaining('+1.0 EV'), findsWidgets);

    await tester.runAsync(() async {
      await session.stop();
    });
    session.dispose();
  });

  testWidgets('tapping the AE-lock switch sends SetAELock then GetAELock', (tester) async {
    final transport = _FakeTransport();
    final session = LinkSession(transport);
    await tester.pumpWidget(
      MaterialApp(home: Scaffold(body: CameraScreen(session: session))),
    );

    await tester.runAsync(() async {
      await session.start();
    });
    await tester.pump();

    await tester.tap(find.byType(Switch));
    await tester.pumpAndSettle();

    expect(find.textContaining('SetAELock(true): sent'), findsOneWidget);
    expect(transport.written, hasLength(2)); // SetAELock, then the confirming GetAELock
    final set = DumlPacket.decode(transport.written[0]);
    expect(set.cmdId, 0x68);
    expect(set.payload, [1]);
    final get = DumlPacket.decode(transport.written[1]);
    expect(get.cmdId, 0x69);

    await tester.runAsync(() async {
      await session.stop();
    });
    session.dispose();
  });
}
