import 'package:duml/duml.dart';

String deviceName(int type) {
  switch (type) {
    case DeviceType.any:
      return 'any';
    case DeviceType.camera:
      return 'camera';
    case DeviceType.app:
      return 'app';
    case DeviceType.flightController:
      return 'FC';
    case DeviceType.gimbal:
      return 'gimbal';
    case DeviceType.centerBoard:
      return 'center';
    case DeviceType.remoteController:
      return 'RC';
    case DeviceType.pc:
      return 'pc';
    default:
      return 'dev$type';
  }
}

String hex2(int v) => v.toRadixString(16).padLeft(2, '0');

String hexBytes(List<int> b) => b.map(hex2).join(' ');

String messageLabel(int set, int id) {
  final n = knownMessageName(set, id);
  return '0x${hex2(set)}/0x${hex2(id)} ${n ?? cmdSetName(set)}';
}

String hms(DateTime t) =>
    '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}:'
    '${t.second.toString().padLeft(2, '0')}.${t.millisecond.toString().padLeft(3, '0')}';
