import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:awto_dji_app/link/link_session.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:awto_dji_app/ui/video_screen.dart';
import 'package:duml/duml.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class _Transport extends BaseTransport {
  final written = <Uint8List>[];
  @override
  String get name => 'camera-fixture';
  @override
  Future<void> connect() async => setState(LinkState.connected);
  @override
  Future<void> disconnect() async => setState(LinkState.disconnected);
  @override
  Future<void> write(Uint8List data) async => written.add(data);
}

Uint8List _hex(String s) => Uint8List.fromList([
  for (var i = 0; i < s.length; i += 2)
    int.parse(s.substring(i, i + 2), radix: 16),
]);

void main() {
  final rows =
      (jsonDecode(
            File('../packages/duml/test/fixtures/captured_camera_pushes.json')
                .readAsStringSync(),
          ) as Map<String, dynamic>)['messages']
          as List<dynamic>;
  Uint8List wire(int id) => _hex(
    rows.firstWhere((row) => row['cmd_id'] == id)['first_wire'] as String,
  );
  Future<void> settle() => Future<void>.delayed(Duration.zero);

  test('fragmented captured pushes update settings without sending queries', () async {
    final transport = _Transport();
    var now = DateTime(2026, 10, 26);
    final session = LinkSession(transport, clock: () => now);
    await session.start();
    // Shot can precede identity; both CRC-checked messages are needed to display.
    for (final b in wire(0x81)) {
      transport.emit(Uint8List.fromList([b]));
    }
    await settle();
    expect(
      session.cameraVideoDescription,
      contains('Waiting for camera identity'),
    );
    transport.emit(wire(0x80));
    await settle();
    expect(session.cameraVideoDescription, contains('4096 × 2160'));
    expect(session.cameraVideoDescription, contains('H.264'));
    expect(transport.written, isEmpty);
    now = now.add(const Duration(seconds: 4));
    // Fresh unrelated traffic and even state alone cannot refresh a stale shot.
    transport.emit(wire(0x83));
    transport.emit(wire(0x80));
    await settle();
    expect(session.cameraVideoDescription, contains('stale'));
    transport.emit(wire(0x81));
    await settle();
    expect(session.cameraVideoDescription, contains('4096 × 2160'));
    await session.stop();
    expect(session.latestCameraRecording, isNull);
    await session.start();
    transport.emit(wire(0x81));
    await settle();
    expect(
      session.cameraVideoDescription,
      contains('Waiting for camera identity'),
    );
    await session.stop();
    session.dispose();
    await transport.dispose();
  });

  test(
    'camera disconnect/model change and CRC corruption cannot retain a display',
    () async {
      final transport = _Transport();
      final session = LinkSession(transport);
      await session.start();
      transport.emit(wire(0x80));
      final bad = wire(0x81)..[15] ^= 1;
      transport.emit(bad);
      await settle();
      expect(session.latestCameraRecording, isNull);
      // Resynchronising may also reject a false header inside the corrupt frame.
      expect(session.crcErrorCount, greaterThanOrEqualTo(1));
      transport.emit(wire(0x81));
      await settle();
      final state = DumlPacket.decode(wire(0x80));
      state.payload[0] &= 0xfe;
      transport.emit(state.encode());
      await settle();
      expect(session.cameraVideoDescription, 'Camera reports disconnected');
      expect(session.latestCameraRecording, isNull);
      state.payload[0] |= 1;
      state.payload[33] = 3; // FC300S, not this verified FC300X interpretation.
      transport.emit(state.encode());
      transport.emit(wire(0x81));
      await settle();
      expect(
        session.cameraVideoDescription,
        contains('unverified camera type 3'),
      );
      await session.stop();
      session.dispose();
      await transport.dispose();
    },
  );

  testWidgets(
    'video page labels recording settings and expires during silence',
    (tester) async {
      final transport = _Transport();
      var now = DateTime(2026, 10, 26);
      final session = LinkSession(transport, clock: () => now);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: VideoScreen(decoder: null, session: session)),
        ),
      );
      await tester.runAsync(() async {
        await session.start();
        transport.emit(wire(0x80));
        transport.emit(wire(0x81));
        await settle();
      });
      await tester.pump();
      expect(find.text('Camera recording settings (DUML)'), findsOneWidget);
      expect(find.textContaining('4096 × 2160'), findsOneWidget);
      expect(
        find.text('Lightbridge preview may use a different format.'),
        findsOneWidget,
      );
      now = now.add(const Duration(seconds: 4));
      await tester.pump(const Duration(seconds: 4));
      expect(find.textContaining('stale'), findsOneWidget);
      expect(find.textContaining('4096 × 2160'), findsNothing);
      await tester.pumpWidget(const SizedBox()); // cancels the label timer
      await tester.runAsync(() async => session.stop());
      session.dispose();
      await transport.dispose();
    },
  );
}
