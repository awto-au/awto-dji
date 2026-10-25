import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

DumlPacket _packet(int cmdId, List<int> payload) => DumlPacket(
      senderType: DeviceType.camera,
      receiverType: DeviceType.app,
      packetType: PacketType.response,
      sequence: 1,
      cmdSet: CmdSet.camera,
      cmdId: cmdId,
      payload: Uint8List.fromList(payload),
    );

void main() {
  group('CameraAeLock', () {
    test('decodes locked and unlocked', () {
      expect(CameraAeLock.fromPacket(_packet(0x69, [1]))!.locked, isTrue);
      expect(CameraAeLock.fromPacket(_packet(0x69, [0]))!.locked, isFalse);
    });

    test('rejects empty payload and wrong cmdId', () {
      expect(CameraAeLock.fromPacket(_packet(0x69, [])), isNull);
      expect(CameraAeLock.fromPacket(_packet(0x68, [1])), isNull);
    });
  });

  group('CameraExposureCompensation', () {
    test('center raw value (16) is 0.0 EV', () {
      final ev = CameraExposureCompensation.fromPacket(_packet(0x2f, [16]))!;
      expect(ev.rawStep, 16);
      expect(ev.ev, 0.0);
    });

    test('min/max raw values map to +-5.0 EV', () {
      expect(
          CameraExposureCompensation.fromPacket(_packet(0x2f, [1]))!.ev, -5.0);
      expect(
          CameraExposureCompensation.fromPacket(_packet(0x2f, [31]))!.ev, 5.0);
    });

    test('one step above center is +1/3 EV', () {
      final ev = CameraExposureCompensation.fromPacket(_packet(0x2f, [17]))!;
      expect(ev.ev, closeTo(1 / 3, 1e-9));
    });

    test('rejects wrong cmdId', () {
      expect(
          CameraExposureCompensation.fromPacket(_packet(0x2e, [16])), isNull);
    });
  });

  group('CameraExposureModeState', () {
    test('decodes a non-scene mode with scene byte ignored', () {
      final s = CameraExposureModeState.fromPacket(_packet(0x1f, [4, 0]))!; // M
      expect(s.mode, CameraExposureMode.m);
      expect(s.scene, 0);
    });

    test('decodes SCN with its scene index', () {
      final s =
          CameraExposureModeState.fromPacket(_packet(0x1f, [6, 3]))!; // SCN
      expect(s.mode, CameraExposureMode.scn);
      expect(s.scene, 3);
    });

    test('unknown raw mode value maps to other', () {
      final s = CameraExposureModeState.fromPacket(_packet(0x1f, [42, 0]))!;
      expect(s.mode, CameraExposureMode.other);
    });

    test('rejects a too-short payload', () {
      expect(CameraExposureModeState.fromPacket(_packet(0x1f, [4])), isNull);
    });
  });
}
