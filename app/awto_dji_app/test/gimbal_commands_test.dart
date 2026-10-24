import 'dart:typed_data';

import 'package:awto_dji_app/link/gimbal_commands.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('autoCalibration() reproduces the real confirmed-working wire frame', () {
    // Real capture, awto-dji#16: 550e046602040074200408008c2f - sequence 0x7400.
    final gimbal = GimbalCommands(0x7400);
    final frame = gimbal.autoCalibration();
    expect(
      frame,
      equals(Uint8List.fromList([
        0x55, 0x0e, 0x04, 0x66, 0x02, 0x04, 0x00, 0x74, 0x20, 0x04, 0x08, 0x00, 0x8c, 0x2f,
      ])),
    );
  });
}
