import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

Uint8List hex(String s) => Uint8List.fromList([
      for (var i = 0; i < s.length; i += 2)
        int.parse(s.substring(i, i + 2), radix: 16),
    ]);

DumlPacket push(int id, List<int> data,
        {int sender = DeviceType.camera,
        int senderIndex = 0,
        int receiver = DeviceType.app,
        PacketType type = PacketType.request,
        AckType ack = AckType.none}) =>
    DumlPacket(
      senderType: sender,
      senderIndex: senderIndex,
      receiverType: receiver,
      sequence: 1,
      packetType: type,
      ackType: ack,
      cmdSet: CmdSet.camera,
      cmdId: id,
      payload: Uint8List.fromList(data),
    );

void main() {
  final fixture = jsonDecode(
    File('test/fixtures/captured_camera_pushes.json').readAsStringSync(),
  ) as Map<String, dynamic>;
  final rows = fixture['messages'] as List<dynamic>;
  final stateRow = rows.firstWhere((r) => r['cmd_id'] == 0x80);
  final shotRow = rows.firstWhere((r) => r['cmd_id'] == 0x81);
  final statePayload = hex(stateRow['payload'] as String);
  final shotPayload = hex(shotRow['payload'] as String);

  test('real protected state and shot pushes decode to classic GO settings',
      () {
    final state = CameraStateInfo.fromPacket(
      DumlPacket.decode(hex(stateRow['first_wire'] as String)),
    )!;
    expect(state.isPhantom3Professional, isTrue);
    expect(state.raw.connected, isTrue);
    expect(state.raw.protocolVersion, 2);
    final shot = CameraRecordingSettings.fromPacket(
      DumlPacket.decode(hex(shotRow['first_wire'] as String)),
    )!;
    expect(shot.resolution, (4096, 2160));
    expect(shot.nominalFrameRate, 24);
    expect(shot.raw.videoStandard, 0);
    expect(shot.primaryEncodingCode, 0);
    expect(shot.secondaryEncodingCode, 0);
    expect(shot.description, '4096 × 2160 · 24 fps (nominal) · H.264 · MP4');
  });

  test('every prefix is bounded; absent extension never becomes H.264', () {
    for (var length = 0; length <= shotPayload.length; length++) {
      final shot = CameraRecordingSettings.fromPacket(
        push(0x81, shotPayload.sublist(0, length)),
      );
      if (length < 20) {
        expect(shot, isNull);
      } else {
        expect(shot!.resolution, (4096, 2160));
        expect(shot.raw.videoStandard, length >= 56 ? 0 : null);
        expect(shot.primaryEncodingCode, length >= 70 ? 0 : null);
        expect(shot.primaryEncodingLabel,
            length >= 70 ? 'H.264' : 'encoding unavailable');
      }
    }
    for (var length = 0; length <= statePayload.length; length++) {
      final state = CameraStateInfo.fromPacket(
        push(0x80, statePayload.sublist(0, length)),
      );
      if (length < 34) {
        expect(state, isNull);
      } else {
        expect(state!.raw.cameraType, 4);
        expect(state.raw.protocolVersion, length >= 37 ? 2 : null);
      }
    }
  });

  test(
      'rejects other senders, camera indexes, destinations, ACKs and query errors',
      () {
    final wrongPackets = [
      push(0x81, shotPayload, sender: DeviceType.gimbal),
      push(0x81, shotPayload, senderIndex: 1),
      push(0x81, shotPayload, receiver: DeviceType.pc),
      push(0x81, shotPayload, type: PacketType.response),
      push(0x81, shotPayload, ack: AckType.afterExec),
      push(0x80, shotPayload),
      push(0x82, shotPayload),
      push(0x92, [0xe4, ...List.filled(12, 0)], type: PacketType.response),
    ];
    for (final p in wrongPackets) {
      expect(CameraRecordingSettings.fromPacket(p), isNull);
    }
    expect(
        CameraStateInfo.fromPacket(
            push(0x80, statePayload, type: PacketType.response)),
        isNull);
  });

  test('unknown enum values are retained; primary and secondary are separate',
      () {
    final changed = Uint8List.fromList(shotPayload)
      ..[13] = 0xfe
      ..[14] = 0xfd
      ..[19] = 0xfc
      ..[69] = 0x10;
    var shot = CameraRecordingSettings.fromPacket(push(0x81, changed))!;
    expect(shot.raw.resolutionCode, 0xfe);
    expect(shot.resolution, isNull);
    expect(shot.nominalFrameRate, isNull);
    expect(shot.description, contains('unknown (0xfe)'));
    expect(shot.description, contains('unknown (0xfd)'));
    expect(shot.description, contains('unknown (0xfc)'));
    expect(shot.primaryEncodingLabel, 'H.264');
    expect(shot.secondaryEncodingCode, 1);
    changed[69] = 0x01;
    shot = CameraRecordingSettings.fromPacket(push(0x81, changed))!;
    expect(shot.primaryEncodingLabel, 'H.265');
    expect(shot.secondaryEncodingCode, 0);
    changed[69] = 0x0f;
    expect(
        CameraRecordingSettings.fromPacket(push(0x81, changed))!
            .primaryEncodingLabel,
        'encoding unknown (0x0f)');
  });

  test('classic GO nominal fps codes are not public SDK enum ordinals', () {
    for (var code = 1; code <= 6; code++) {
      final changed = Uint8List.fromList(shotPayload)..[14] = code;
      expect(
          CameraRecordingSettings.fromPacket(push(0x81, changed))!
              .nominalFrameRate,
          [24, 25, 30, 48, 50, 60][code - 1]);
    }
    final changed = Uint8List.fromList(shotPayload)..[14] = 0;
    expect(
        CameraRecordingSettings.fromPacket(push(0x81, changed))!
            .nominalFrameRate,
        isNull);
  });
}
