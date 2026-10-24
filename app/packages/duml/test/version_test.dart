import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

void main() {
  group('CommonVersion', () {
    test('decodes hardware/firmware/loader strings and the info flags', () {
      final payload = Uint8List(30);
      final hw = 'P3X-HW'.codeUnits;
      payload.setRange(2, 2 + hw.length, hw); // offset 2..17, NUL-padded
      // firmware "01.02.03.04" -> bytes 22..25 = 1,2,3,4 (get(25)=1 highest digit pair)
      payload[22] = 4;
      payload[23] = 3;
      payload[24] = 2;
      payload[25] = 1;
      // loader "05.06.07.08" -> bytes 18..21
      payload[18] = 8;
      payload[19] = 7;
      payload[20] = 6;
      payload[21] = 5;
      final d = ByteData.sublistView(payload);
      d.setUint32(26, (1 << 31) | (1 << 30), Endian.little);

      final v = CommonVersion.fromPacket(DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        packetType: PacketType.response,
        sequence: 1,
        cmdSet: CommonVersion.cmdSet,
        cmdId: CommonVersion.cmdId,
        payload: payload,
      ))!;

      expect(v.hardwareVersion, 'P3X-HW');
      expect(v.firmwareVersion, '01.02.03.04');
      expect(v.loaderVersion, '05.06.07.08');
      expect(v.isProduction, isTrue);
      expect(v.isSupportSafeUpgrade, isTrue);
    });

    test('a too-short payload does not match', () {
      final p = DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        sequence: 1,
        cmdSet: CommonVersion.cmdSet,
        cmdId: CommonVersion.cmdId,
        payload: Uint8List(10),
      );
      expect(CommonVersion.fromPacket(p), isNull);
    });

    test('a different cmdset/cmdid does not match', () {
      final p = DumlPacket(
        senderType: DeviceType.flightController,
        receiverType: DeviceType.app,
        sequence: 1,
        cmdSet: CmdSet.flightController,
        cmdId: 0x43,
        payload: Uint8List(29),
      );
      expect(CommonVersion.fromPacket(p), isNull);
    });
  });
}
