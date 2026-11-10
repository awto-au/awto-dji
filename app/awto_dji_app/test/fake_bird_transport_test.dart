import 'dart:typed_data';

import 'package:awto_dji_app/transport/fake_bird_transport.dart';
import 'package:awto_dji_app/transport/link_transport.dart';
import 'package:duml/duml.dart';
import 'package:flutter_test/flutter_test.dart';

/// Command-responding fake bird (#102 full-system emulation, phase-0): the app sends a DUML
/// command, the emulated aircraft decodes it and replies — verified end to end.
void main() {
  test('answers GetVersion with a CommonVersion reply, as the flight controller', () async {
    final bird = FakeBirdTransport();
    await bird.connect();
    expect(bird.currentState, LinkState.connected);

    final replyBytes = bird.bytes.first; // listen before writing (broadcast stream)
    final request = DumlPacket(
      senderType: DeviceType.app,
      receiverType: DeviceType.flightController,
      sequence: 7,
      cmdSet: CmdSet.general,
      cmdId: 0x01,
    ).encode();
    await bird.write(request);

    final reply = DumlPacket.decode(await replyBytes);
    expect(reply.senderType, DeviceType.flightController); // reply identifies the device
    expect(reply.receiverType, DeviceType.app);
    expect(CommonVersion.matches(reply), isTrue);
    expect(CommonVersion.fromPayload(reply.payload).hardwareVersion, 'FakeBird');
  });

  test('ignores an unmodelled command (no reply, no crash)', () async {
    final bird = FakeBirdTransport();
    await bird.connect();
    var emitted = 0;
    final sub = bird.bytes.listen((_) => emitted++);
    await bird.write(DumlPacket(
      senderType: DeviceType.app,
      receiverType: DeviceType.flightController,
      sequence: 1,
      cmdSet: CmdSet.gimbal,
      cmdId: 0xFE, // not modelled
    ).encode());
    await Future<void>.delayed(Duration.zero);
    expect(emitted, 0);
    await sub.cancel();
  });

  test('on() registers additional responders', () {
    final bird = FakeBirdTransport();
    bird.on(CmdSet.gimbal, 0x05, (req) => Uint8List.fromList([1, 2, 3]));
    expect(bird.answered, contains((CmdSet.general, 0x01)));
    expect(bird.answered, contains((CmdSet.gimbal, 0x05)));
  });
}
