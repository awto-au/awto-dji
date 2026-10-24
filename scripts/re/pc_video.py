#!/usr/bin/env python3
"""Extract and inspect H.264 from a saved raw AOA capture or relay hex log.

No device I/O or command sending. With --preview, starts ffplay only when SPS/PPS
and an IDR are present. Missing headers cannot be reconstructed from P-slices.
"""
import argparse
import collections
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log
from aoa_mux import AoaMux, CAMERA_VIDEO

RX_LINE = re.compile(r'^\S+ \+(\d+)B ([0-9a-fA-F]+)$')
START_CODE = re.compile(b'\x00\x00\x00?\x01')


def extract(source, destination, channel=CAMERA_VIDEO, log_format=False, bootstrap=None):
    mux = AoaMux()
    raw_bytes = 0
    resets = 0
    seed = bootstrap.read_bytes() if bootstrap else b''
    with source.open('rb') as stream, destination.open('wb') as output:
        output.write(seed)
        if log_format:
            def chunks():
                nonlocal resets
                for line in stream:
                    text = line.decode('ascii', 'strict').strip()
                    if text.startswith('=== connection from') or text.startswith('=== listening on') or text.endswith('disconnected ==='):
                        mux.finish()
                        resets += 1
                    match = RX_LINE.fullmatch(text)
                    if match:
                        data = bytes.fromhex(match[2])
                        if len(data) != int(match[1]):
                            raise ValueError('Relay log RX length does not match hex bytes')
                        yield data
        else:
            def chunks():
                while data := stream.read(64 * 1024):
                    yield data
        for data in chunks():
            raw_bytes += len(data)
            for packet in mux.feed(data):
                if packet.channel == channel:
                    output.write(packet.payload)
        trailing = mux.finish()
    video = destination.read_bytes()
    nal_types = collections.Counter(video[m.end()] & 31 for m in START_CODE.finditer(video) if m.end() < len(video))
    missing = [name for number, name in [(7, 'SPS'), (8, 'PPS'), (5, 'IDR')] if not nal_types[number]]
    return {
        'source': str(source), 'output': str(destination), 'channel': hex(channel),
        'input_bytes': raw_bytes, 'video_bytes': len(video) - len(seed),
        'bootstrap': ({'source': str(bootstrap), 'bytes': len(seed),
                       'sha256': hashlib.sha256(seed).hexdigest(),
                       'note': 'External decoder-start picture; not captured aircraft footage'}
                      if bootstrap else None),
        'channel_packets': {hex(k): v for k, v in sorted(mux.packets.items())},
        'channel_payload_bytes': {hex(k): v for k, v in sorted(mux.payload_bytes.items())},
        'discarded_bytes': mux.discarded, 'final_incomplete_bytes': trailing,
        'connection_boundaries': resets,
        'nal_types': dict(sorted(nal_types.items())), 'missing_for_independent_decode': missing,
    }


def decode_check(path):
    if not shutil.which('ffprobe'):
        raise RuntimeError('ffprobe is required for --check')
    run = subprocess.run(['ffprobe', '-v', 'error', '-f', 'h264', '-count_frames',
                          '-show_entries', 'stream=codec_name,width,height,nb_read_frames',
                          '-of', 'json', str(path)], capture_output=True, text=True)
    info = json.loads(run.stdout or '{}')
    streams = info.get('streams', [])
    frames = sum(int(s.get('nb_read_frames', '0')) for s in streams if str(s.get('nb_read_frames', '0')).isdigit())
    return {'decoded_frames': frames, 'streams': streams, 'returncode': run.returncode,
            'diagnostics': list(dict.fromkeys(re.sub(r'0x[0-9a-f]+', '<address>', line) for line in run.stderr.splitlines()))[:12]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--format', choices=['raw', 'relay-log'], default='relay-log')
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--channel', type=lambda s: int(s, 0), default=CAMERA_VIDEO)
    parser.add_argument('--check', action='store_true', help='count decoded frames with ffprobe')
    parser.add_argument('--preview', action='store_true', help='play extracted video with ffplay')
    parser.add_argument('--bootstrap', type=Path,
                        help='prepend an explicitly supplied compatible decoder-start H.264 picture')
    args = parser.parse_args()
    if args.capture.resolve() == args.output.resolve():
        parser.error('Capture and extracted output must be different files')
    if args.report and args.report.resolve() in {args.capture.resolve(), args.output.resolve()}:
        parser.error('Report must be separate from capture and output')
    if args.bootstrap and args.bootstrap.resolve() == args.output.resolve():
        parser.error('Bootstrap and output must be different files')
    result = extract(args.capture, args.output, args.channel, args.format == 'relay-log',
                     bootstrap=args.bootstrap)
    if args.check:
        result['decode'] = decode_check(args.output)
        if args.bootstrap:
            result['decode']['frames_beyond_bootstrap'] = max(
                0, result['decode']['decoded_frames'] - 1)
    report = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.write_text(report)
    print(report, end='')
    log(f"extracted {args.output} (report on stdout{', ' + str(args.report) if args.report else ''})")
    if args.preview:
        if result['missing_for_independent_decode']:
            print('Cannot preview independently: missing ' + ', '.join(result['missing_for_independent_decode']), file=sys.stderr)
            return 2
        if not shutil.which('ffplay'):
            parser.error('ffplay is required for --preview')
        return subprocess.run(['ffplay', '-autoexit', '-window_title', 'DJI camera capture',
                               '-f', 'h264', str(args.output)]).returncode
    if args.check and not result['decode'].get('frames_beyond_bootstrap',
                                             result['decode']['decoded_frames']):
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
