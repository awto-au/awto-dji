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

    def test_rejected_envelope_header_does_not_stall_as_bare_frame_candidate(self):
        # Regression (awto-dji#64): an early version of the bare-frame fallback checked
        # only the declared length before deciding to wait for a full frame to arrive, so
        # a rejected (oversized-for-max_payload) envelope header's own bytes - misread as
        # a DUML length field - could make the scanner stall waiting for a frame that
        # would never complete, instead of resyncing immediately within the same feed().
        # The fix (header CRC8 checked first, cheaply, before ever waiting) must hold.
        mux = AoaMux(max_payload=64)
        bad = b'\x55\xcc' + struct.pack('<HI', CAMERA_VIDEO, 65)  # rejected: 65 > max_payload
        packets = mux.feed(bad + envelope(CAMERA_VIDEO, b'good'))
        self.assertEqual(packets, [(CAMERA_VIDEO, b'good')])
        self.assertEqual(mux.discarded, len(bad))

    def test_back_to_back_correctly_declared_envelopes_never_leak(self):
        # Proves AoaMux's own slicing arithmetic is correct given an honest
        # length field - mirrors aoa_mux_test.dart.
        first = build_frame(2, 14, 1, 2, 0x09, 0x16, b'\x01\x02\x03')
        second = build_frame(2, 14, 2, 2, 0x09, 0x16, b'\x04\x05')
        mux = AoaMux()
        packets = mux.feed(envelope(COMMAND, first) + envelope(COMMAND, second))
        self.assertEqual(packets, [(COMMAND, first), (COMMAND, second)])
        self.assertEqual(mux.discarded, 0)

    def test_command_envelope_with_overstated_length_is_trimmed(self):
        # Reproduces the live symptom (docs/aoa-live-test-2026-10-26.md):
        # LinkSession saw literal `55 cc <channel>` bytes inside what should
        # have been pure DUML payload - the declared length was 8 bytes too
        # long, exactly the size of the next envelope's header, so a naive
        # full-length slice swallowed it. Mirrors aoa_mux_test.dart.
        real_frame = build_frame(2, 14, 1, 2, 0x09, 0x16, b'\x01\x02\x03')
        second = envelope(COMMAND, build_frame(2, 14, 2, 2, 0x09, 0x16, b'\x09'))
        overstated_header = b'\x55\xcc' + struct.pack(
            '<HI', COMMAND, len(real_frame) + len(second))
        mux = AoaMux()
        packets = mux.feed(overstated_header + real_frame + second)
        self.assertEqual(len(packets), 2,
                          'the leaked envelope must be recovered as its own packet')
        self.assertEqual(packets[0], (COMMAND, real_frame))
        self.assertEqual(packets[1][0], COMMAND)
        self.assertEqual(mux.discarded, 0)

    def test_bare_duml_frame_recovered_without_envelope(self):
        bare = build_frame(2, 14, 7, 2, 0x09, 0x08, b'\x01\x02')
        wire = envelope(COMMAND, b'first') + bare + envelope(COMMAND, b'second')
        mux = AoaMux()
        packets = mux.feed(wire)
        self.assertEqual(packets, [(COMMAND, b'first'), (COMMAND, bare), (COMMAND, b'second')])
        self.assertEqual(mux.discarded, 0)
        self.assertEqual(mux.packets[COMMAND], 3)

    def test_bare_candidate_with_bad_full_crc_is_rejected_not_stalled(self):
        good = build_frame(2, 14, 7, 2, 0x09, 0x08, b'\x01\x02')
        # Flip a payload byte: header CRC8 (bytes 0-2 only) still matches, so this
        # passes the cheap first gate, but the full-frame CRC16 must then reject it.
        corrupted = bytearray(good)
        corrupted[-3] ^= 0xFF
        wire = bytes(corrupted) + envelope(CAMERA_VIDEO, b'next')
        mux = AoaMux()
        packets = mux.feed(wire)
        self.assertEqual(packets, [(CAMERA_VIDEO, b'next')])
        self.assertEqual(mux.discarded, len(corrupted))

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
