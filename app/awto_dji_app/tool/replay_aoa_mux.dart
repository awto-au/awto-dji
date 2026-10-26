// Feeds real captured accessory bytes through the ACTUAL AoaMux + video-NAL Dart
// classes shipped in the app (not reimplementations) - verifies the Dart-side
// bare-DUML-frame fix (awto-dji#64) and the AnnexB/access-unit pipeline against
// real data without a phone rebuild+install cycle. Stops at the Dart/native
// boundary: MediaCodec itself (awto-dji#67) is a real Android platform API and
// cannot run here - this only covers what's pure Dart upstream of it.
//
// Reads "RAWUDP seq=N +MB <hex>" lines from aoa_relay_server.py's log (the same
// true-pre-AoaMux ground truth scripts/re/analyze_raw_capture.py uses on the Python
// side), splits on "=== connection from" markers the same way, and reports discard
// and NAL/access-unit stats per segment. Plain `dart run` - no Flutter engine
// needed (none of aoa_mux.dart/annexb_extractor.dart/h264_access_units.dart have
// Flutter imports).
//
// With --play, also writes the real H264AccessUnits output (Annex-B start codes
// already included by that class) to a temp file and launches ffplay on it - lets
// you SEE whether the actual Dart NAL/access-unit pipeline decodes correctly,
// entirely on the PC, bypassing the Android MediaCodec crash (awto-dji#67) for
// inspection purposes. Needs at least one SPS+PPS+IDR in the segment to be
// decodable at all - P-slices alone can't reconstruct missing headers.
//
// Usage: dart run tool/replay_aoa_mux.dart <path-to-aoa_relay_server.log> [--play]

import 'dart:io';
import 'dart:typed_data';

import '../lib/transport/aoa_mux.dart';
import '../lib/video/annexb_extractor.dart';
import '../lib/video/h264_access_units.dart';

final _rawLine = RegExp(r'RAWUDP seq=(\d+) \+(\d+)B ([0-9a-f]+)');
final _connectionMarker = RegExp(r'=== connection from ');

List<Map<int, Uint8List>> _loadSegments(String path) {
  final segments = <Map<int, Uint8List>>[<int, Uint8List>{}];
  for (final line in File(path).readAsLinesSync()) {
    if (_connectionMarker.hasMatch(line) && segments.last.isNotEmpty) {
      segments.add(<int, Uint8List>{});
    }
    final m = _rawLine.firstMatch(line);
    if (m == null) continue;
    final seq = int.parse(m.group(1)!);
    final hex = m.group(3)!;
    final bytes = Uint8List(hex.length ~/ 2);
    for (var i = 0; i < bytes.length; i++) {
      bytes[i] = int.parse(hex.substring(i * 2, i * 2 + 2), radix: 16);
    }
    segments.last[seq] = bytes;
  }
  return segments.where((s) => s.isNotEmpty).toList();
}

void main(List<String> args) {
  if (args.isEmpty) {
    stderr.writeln('usage: dart run tool/replay_aoa_mux.dart <aoa_relay_server.log> [--play]');
    exit(1);
  }
  final play = args.contains('--play');
  final segments = _loadSegments(args[0]);
  print('${segments.length} connection segment(s)');
  var bestSegment = -1;
  var bestIdrCount = 0;
  final outputs = <int, File>{};
  for (var i = 0; i < segments.length; i++) {
    final chunks = segments[i];
    final seqs = chunks.keys.toList()..sort();
    final full = BytesBuilder();
    for (final s in seqs) {
      full.add(chunks[s]!);
    }
    final bytes = full.toBytes();
    final mux = AoaMux();
    final nals = AnnexBExtractor();
    final accessUnits = H264AccessUnits();
    final byChannel = <int, int>{};
    var nalCount = 0;
    var pictureCount = 0;
    final nalTypeCounts = <int, int>{};
    IOSink? sink;
    if (play) {
      final f = File('${Directory.systemTemp.path}/aoa_replay_segment_$i.h264');
      outputs[i] = f;
      sink = f.openWrite();
    }
    mux.onPacket = (p) {
      byChannel[p.channel] = (byChannel[p.channel] ?? 0) + 1;
      if (p.channel == AoaMux.cameraVideo) {
        for (final nal in nals.add(p.payload)) {
          nalCount++;
          if (nal.isNotEmpty) {
            final type = nal[0] & 31;
            nalTypeCounts[type] = (nalTypeCounts[type] ?? 0) + 1;
          }
          for (final accessUnit in accessUnits.add(nal)) {
            sink?.add(accessUnit); // already has its own Annex-B start code
          }
        }
      }
    };
    mux.add(bytes);
    mux.finish();
    sink?.close();
    pictureCount = nalTypeCounts[1] ?? 0; // non-IDR slices, close enough for a count
    final idrCount = nalTypeCounts[5] ?? 0;
    final pct = bytes.isEmpty ? 0.0 : 100 * mux.discarded / bytes.length;
    print('segment $i: ${bytes.length}B total, discarded=${mux.discarded} '
        '(${pct.toStringAsFixed(1)}%), packets by channel: '
        '${byChannel.map((k, v) => MapEntry('0x${k.toRadixString(16)}', v))}');
    if (nalCount > 0) {
      print('  video: $nalCount NALs, ~$pictureCount access units, '
          'types: ${nalTypeCounts.map((k, v) => MapEntry('$k', v))} '
          '(7=SPS 8=PPS 5=IDR 1=non-IDR slice 6=SEI 9=AUD)');
    }
    if (idrCount > bestIdrCount) {
      bestIdrCount = idrCount;
      bestSegment = i;
    }
  }
  if (!play) return;
  if (bestSegment < 0 || bestIdrCount == 0) {
    print('\n--play given but no segment has an IDR frame - nothing is decodable '
        '(P-slices alone can\'t reconstruct missing SPS/PPS/IDR).');
    return;
  }
  final path = outputs[bestSegment]!.path;
  print('\nPlaying segment $bestSegment ($bestIdrCount IDR frame(s)): $path');
  Process.start('ffplay', ['-autoexit', '-loglevel', 'warning', path],
      mode: ProcessStartMode.inheritStdio);
}
