/// DUML checksums, reverse-engineered by the community and verified against the
/// o-gs/dji-firmware-tools reference and a captured Phantom/RC packet.
///
///  * header CRC-8: reflected, polynomial 0x8C, seed 0x77, over the first 3 bytes
///  * packet CRC-16: reflected, polynomial 0x8408, seed 0x3692, over all but the
///    trailing 2 checksum bytes
library;

int _crc8(int seed, List<int> data, int length) {
  var crc = seed & 0xFF;
  for (var i = 0; i < length; i++) {
    crc ^= data[i] & 0xFF;
    for (var b = 0; b < 8; b++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0x8C : crc >> 1;
    }
  }
  return crc & 0xFF;
}

int _crc16(int seed, List<int> data, int length) {
  var crc = seed & 0xFFFF;
  for (var i = 0; i < length; i++) {
    crc ^= data[i] & 0xFF;
    for (var b = 0; b < 8; b++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0x8408 : crc >> 1;
    }
  }
  return crc & 0xFFFF;
}

/// Header checksum over the first 3 bytes (SOF + length/version), seed 0x77.
int headerCrc8(List<int> packet) => _crc8(0x77, packet, 3);

/// Whole-packet checksum over `packet[0 .. length-2]`, seed 0x3692.
int packetCrc16(List<int> packet, int length) =>
    _crc16(0x3692, packet, length - 2);
