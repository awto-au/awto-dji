import 'dart:typed_data';

/// MediaCodec consumes whole pictures, rather than one buffer per H.264 slice.
/// Input is Annex-B-stripped NALs; output restores start codes around each NAL.
class H264AccessUnits {
  final _bytes = BytesBuilder();
  bool _hasPicture = false;

  void reset() {
    _bytes.clear();
    _hasPicture = false;
  }

  List<Uint8List> add(Uint8List nal) {
    if (nal.isEmpty) return const [];
    final type = nal[0] & 31;
    final picture = type == 1 || type == 5;
    // first_mb_in_slice is unsigned Exp-Golomb: its first bit is 1 for zero.
    final firstSlice = picture && nal.length > 1 && (nal[1] & 128) != 0;
    final boundary =
        type == 9 ||
        (_hasPicture && (firstSlice || type == 7 || type == 8 || type == 6));
    final result = <Uint8List>[];
    if (boundary && _bytes.isNotEmpty) {
      if (_hasPicture) {
        result.add(_bytes.takeBytes());
      }
      // Keep standalone SPS/PPS preceding the first AUD with that picture.
      _hasPicture = false;
    }
    _bytes.add(const [0, 0, 0, 1]);
    _bytes.add(nal);
    _hasPicture = _hasPicture || picture;
    if (_bytes.length > 4 * 1024 * 1024) reset();
    return result;
  }
}
