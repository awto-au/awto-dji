import 'dart:typed_data';

import 'package:duml/duml.dart';
import 'package:test/test.dart';

void main() {
  group('CommonVersion', () {
    test('decodes hardware/firmware/loader strings and the info flags', () {
      final payload = Uint8List(29);
      final hw = 'P3X-HW'.codeUnits;
      payload.setRange(1, 1 + hw.length, hw); // offset 1..16, NUL-padded
      // firmware "01.02.03.04" -> bytes 21..24 = 1,2,3,4 (get(24)=1 highest digit pair)
      payload[21] = 4;
      payload[22] = 3;
      payload[23] = 2;
      payload[24] = 1;
      // loader "05.06.07.08" -> bytes 17..20
      payload[17] = 8;
      payload[18] = 7;
      payload[19] = 6;
      payload[20] = 5;
      final d = ByteData.sublistView(payload);
      d.setUint32(25, (1 << 31) | (1 << 30), Endian.little);

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
