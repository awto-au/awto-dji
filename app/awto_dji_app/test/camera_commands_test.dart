import 'package:awto_dji_app/link/camera_commands.dart';
import 'package:duml/duml.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('CameraCommands', () {
    test('setAeLock(true/false) packs a single 1/0 byte, APP->CAMERA', () {
      final camera = CameraCommands(0x6c00);
      for (final locked in [true, false]) {
        final p = DumlPacket.decode(camera.setAeLock(locked));
        expect(p.senderType, DeviceType.app);
        expect(p.receiverType, DeviceType.camera);
        expect(p.cmdSet, CmdSet.camera);
        expect(p.cmdId, 0x68);
        expect(p.payload, [locked ? 1 : 0]);
      }
    });

    test('getAeLock() is an empty-payload query', () {
      final p = DumlPacket.decode(CameraCommands().getAeLock());
      expect(p.cmdSet, CmdSet.camera);
      expect(p.cmdId, 0x69);
      expect(p.payload, isEmpty);
    });

    test('setExposureCompensation maps EV to the real 1..31 raw range', () {
      final camera = CameraCommands();
      expect(DumlPacket.decode(camera.setExposureCompensation(0.0)).payload, [16]);
      expect(DumlPacket.decode(camera.setExposureCompensation(-5.0)).payload, [1]);
      expect(DumlPacket.decode(camera.setExposureCompensation(5.0)).payload, [31]);
      // Out-of-range input is clamped to the real device's range, not rejected.
      expect(DumlPacket.decode(camera.setExposureCompensation(99.0)).payload, [31]);
      expect(DumlPacket.decode(camera.setExposureCompensation(-99.0)).payload, [1]);
    });

    test('setExposureCompensation rounds to the nearest 1/3-stop raw value', () {
      final p = DumlPacket.decode(CameraCommands().setExposureCompensation(1.0));
      expect(p.cmdSet, CmdSet.camera);
      expect(p.cmdId, 0x2e);
      expect(p.payload, [19]); // 16 + round(1.0*3)
    });

    test('getExposureCompensation() is an empty-payload query', () {
      final p = DumlPacket.decode(CameraCommands().getExposureCompensation());
      expect(p.cmdId, 0x2f);
      expect(p.payload, isEmpty);
    });

    test('setExposureMode packs mode and omits scene for non-SCN modes', () {
      final p = DumlPacket.decode(CameraCommands().setExposureMode(CameraExposureMode.m));
      expect(p.cmdSet, CmdSet.camera);
      expect(p.cmdId, 0x1e);
      expect(p.payload, [4, 0]);
    });

    test('setExposureMode packs the scene byte only for SCN', () {
      final p = DumlPacket.decode(
          CameraCommands().setExposureMode(CameraExposureMode.scn, scene: 3));
      expect(p.payload, [6, 3]);
    });

    test('getExposureMode() is an empty-payload query', () {
      final p = DumlPacket.decode(CameraCommands().getExposureMode());
      expect(p.cmdId, 0x1f);
      expect(p.payload, isEmpty);
    });

    test('sequence numbers increment across calls', () {
      final camera = CameraCommands(0x1000);
      final a = DumlPacket.decode(camera.setAeLock(true));
      final b = DumlPacket.decode(camera.setAeLock(false));
      expect(a.sequence, 0x1000);
      expect(b.sequence, 0x1001);
    });
  });
}
