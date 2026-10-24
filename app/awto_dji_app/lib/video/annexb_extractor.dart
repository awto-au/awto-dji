import 'dart:typed_data';

/// Splits demultiplexed H.264 Annex-B bytes into NAL units without start codes.
/// Callers must remove AOA envelopes and other channels before adding bytes.
class AnnexBExtractor {
  final _buf = BytesBuilder(copy: true);

  void reset() => _buf.clear();

  /// Feed a chunk, get back every complete NAL unit (without its start code) found so far.
  /// Any trailing partial NAL is held until the next call.
  List<Uint8List> add(Uint8List chunk) {
    _buf.add(chunk);
    final data = _buf.toBytes();
    final starts = <(int, int)>[];
    var i = 0;
    while (i < data.length - 2) {
      if (i + 3 < data.length &&
          data[i] == 0 &&
          data[i + 1] == 0 &&
          data[i + 2] == 0 &&
          data[i + 3] == 1) {
        starts.add((i, 4));
        i += 4;
      } else if (data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1) {
        starts.add((i, 3));
        i += 3;
      } else {
        i++;
      }
    }
    if (starts.length < 2) {
      // Not enough start codes yet to bound even one complete NAL - keep buffering.
      // Bound buffering even if a start code is followed by an oversized NAL.
      if (data.length > 1 << 20) {
        _buf.clear();
        _buf.add(data.sublist(data.length - 3));
        return const [];
      }
      if (starts.isNotEmpty) {
        _buf.clear();
        _buf.add(data.sublist(starts.last.$1));
      }
      return const [];
    }
    final out = <Uint8List>[];
    for (var k = 0; k < starts.length - 1; k++) {
      final s = starts[k].$1 + starts[k].$2;
      var e = starts[k + 1].$1;
      while (e > s && data[e - 1] == 0) {
        e--;
      }
      if (s < e) out.add(Uint8List.fromList(data.sublist(s, e)));
    }
    // Keep from the last start code onward (its NAL isn't known-complete yet).
    _buf.clear();
    _buf.add(data.sublist(starts.last.$1));
    return out;
  }
}
