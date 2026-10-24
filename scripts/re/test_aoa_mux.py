#!/usr/bin/env python3
"""Regression tests for AOA boundaries, channel isolation and capture replay."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aoa_mux import AoaMux, CAMERA_VIDEO, COMMAND
from aoa_relay_server import StreamDemuxer
from duml_proto import build_frame
from pc_video import extract


def envelope(channel, payload):
    return b'\x55\xcc' + struct.pack('<HI', channel, len(payload)) + payload


class MuxTests(unittest.TestCase):
    def test_all_chunk_sizes_preserve_headers_and_payload_markers(self):
        video = b'\0\0\0\1\x67abc' + envelope(COMMAND, b'fake nested packet')
        wire = envelope(CAMERA_VIDEO, video) + envelope(COMMAND, b'commands')
        for size in range(1, len(wire) + 1):
            mux = AoaMux()
            packets = []
            for offset in range(0, len(wire), size):
                packets.extend(mux.feed(wire[offset:offset + size]))
            self.assertEqual(packets, [(CAMERA_VIDEO, video), (COMMAND, b'commands')])
            self.assertEqual(mux.discarded, 0)
            self.assertEqual(mux.finish(), 0)

    def test_noise_and_oversized_header_resynchronize(self):
        mux = AoaMux(max_payload=64)
        bad = b'noise' + b'\x55\xcc' + struct.pack('<HI', CAMERA_VIDEO, 65)
        packets = mux.feed(bad + envelope(CAMERA_VIDEO, b'good'))
        self.assertEqual(packets, [(CAMERA_VIDEO, b'good')])
        self.assertEqual(mux.discarded, len(bad))

    def test_connection_boundary_discards_partial_frame(self):
        mux = AoaMux()
        self.assertEqual(mux.feed(envelope(COMMAND, b'hello')[:-1]), [])
        self.assertEqual(mux.finish(), 12)
        self.assertEqual(mux.feed(envelope(CAMERA_VIDEO, b'next')), [(CAMERA_VIDEO, b'next')])

    def test_noise_buffer_is_bounded(self):
        mux = AoaMux()
        mux.feed(b'x' * 100000 + b'\x55')
        self.assertEqual(bytes(mux.buf), b'\x55')

    def test_command_packets_inside_video_are_not_telemetry(self):
        frame = build_frame(10, 14, 5, 2, 0, 1, b'')
        videos, commands = [], []
        demux = StreamDemuxer(on_video=videos.append)
        wire = envelope(CAMERA_VIDEO, frame) + envelope(COMMAND, frame[:6]) + envelope(COMMAND, frame[6:])
        for byte in wire:
            demux.feed(bytes([byte]), commands.append)
        self.assertEqual(videos, [frame])
        self.assertEqual(len(commands), 1)
        self.assertEqual(demux.duml_bytes, len(frame))
        self.assertEqual(demux.video_bytes, len(frame))

    def test_relay_replay_ignores_tx_and_resets_partial_connections(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, output = root / 'capture.log', root / 'video.h264'
            partial = envelope(CAMERA_VIDEO, b'incomplete')[:-4]
            complete = envelope(CAMERA_VIDEO, b'\0\0\1\x67sps\0\0\1\x68pps\0\0\1\x65idr')
            source.write_text(
                f'2026-10-24T12:00:00 +{len(partial)}B {partial.hex()}\n'
                '=== connection from new phone ===\n'
                f'2026-10-24T12:00:01 TX {len(complete)}B {complete.hex()}\n'
                f'2026-10-24T12:00:02 +{len(complete)}B {complete.hex()}\n')
            report = extract(source, output, log_format=True)
            self.assertEqual(output.read_bytes(), complete[8:])
            self.assertEqual(report['missing_for_independent_decode'], [])
            self.assertEqual(report['discarded_bytes'], len(partial))


if __name__ == '__main__':
    unittest.main()
