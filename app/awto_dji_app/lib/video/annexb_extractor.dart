import 'dart:typed_data';

/// Splits a raw byte stream into H.264 Annex-B NAL units (start-code delimited), tolerating
/// chunk boundaries that fall mid-NAL. The same raw AOA byte stream also carries DUML frames
/// interleaved with no demux header (see docs/aoa-live-test-2026-10-23.md) - this extractor
/// only looks for 00 00 01 / 00 00 00 01 start codes and ignores everything else; DUML framing
/// runs independently on the same bytes via LinkSession.
class AnnexBExtractor {
  final _buf = BytesBuilder(copy: true);

  /// Feed a chunk, get back every complete NAL unit (without its start code) found so far.
  /// Any trailing partial NAL is held until the next call.
  List<Uint8List> add(Uint8List chunk) {
    _buf.add(chunk);
    final data = _buf.toBytes();
    final starts = <int>[];
    var i = 0;
    while (i < data.length - 2) {
      if (data[i] == 0 && data[i + 1] == 0 && data[i + 2] == 1) {
        starts.add(i);
        i += 3;
      } else {
        i++;
      }
    }
    if (starts.length < 2) {
      // Not enough start codes yet to bound even one complete NAL - keep buffering.
      // Cap growth so a long run of non-NAL (DUML) bytes doesn't buffer forever.
      if (data.length > 1 << 20) _buf.clear();
      if (starts.isNotEmpty) {
        _buf.clear();
        _buf.add(data.sublist(starts.last));
      }
      return const [];
    }
    final out = <Uint8List>[];
    for (var k = 0; k < starts.length - 1; k++) {
      var s = starts[k] + 3;
      var e = starts[k + 1];
      // Strip a trailing zero byte if this was actually a 4-byte start code (00 00 00 01).
      if (e > s && data[e - 1] == 0) {
        // the next start code's leading zero already accounted for; nothing to trim here,
        // 4-vs-3-byte start codes are distinguished by the byte *before* each start index.
      }
      if (s < e) out.add(Uint8List.fromList(data.sublist(s, e)));
    }
    // Keep from the last start code onward (its NAL isn't known-complete yet).
    _buf.clear();
    _buf.add(data.sublist(starts.last));
    return out;
  }
}
