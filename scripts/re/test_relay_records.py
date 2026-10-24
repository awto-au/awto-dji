#!/usr/bin/env python3
"""Offline relay framing, SIMPLE decoding, and negative-case regressions."""
import json
import struct
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aoa_mux import COMMAND, CAMERA_VIDEO
from aoa_relay_server import StreamDemuxer
from relay_records import (RecordParser, command_verdict,
                           encode_record, ENVELOPE, DISCARDED)


class RecordTests(unittest.TestCase):
    def setUp(self):
        fixture = json.loads((Path(__file__).resolve().parents[2] /
            'app/packages/duml/test/fixtures/captured_simple_frame.json').read_text())
        self.fixture = fixture
        self.wire = bytes.fromhex(fixture['wire'])

    def test_independent_simple_decode_matches_capture_fixture(self):
        verdict = command_verdict(self.wire)
        self.assertTrue(verdict['accepted'])
        self.assertEqual(verdict['cmdSet'], 9)
        self.assertEqual(verdict['cmdId'], 10)
        self.assertEqual(verdict['sequence'], 15311)
        self.assertEqual(verdict['payload'], self.fixture['payload'])
        self.assertFalse(command_verdict(self.wire[:-1])['accepted'])

    def test_all_tcp_splits_preserve_channel_records_and_discarded_bytes(self):
        envelope = b'\x55\xcc' + struct.pack('<HI', COMMAND, len(self.wire)) + self.wire
        wire = (encode_record(DISCARDED, 0, b'noise') +
                encode_record(ENVELOPE, COMMAND, envelope))
        for size in range(1, len(wire) + 1):
            parser = RecordParser()
            demux = StreamDemuxer()
            received = []
            commands = []
            for offset in range(0, len(wire), size):
                for kind, channel, payload in parser.feed(wire[offset:offset+size]):
                    received.append((kind, channel, payload))
                    demux.feed(payload, commands.append)
            parser.finish()
            self.assertEqual(received, [(DISCARDED,0,b'noise'), (ENVELOPE,COMMAND,envelope)])
            self.assertEqual(len(commands), 1)
            self.assertIn('set=0x09 id=0x0a protection=3', commands[0])

    def test_invalid_header_envelope_and_truncation_rejected(self):
        for wire in [b'not a relay header',
                     struct.pack('<4sBBHI', b'AWTO',1,1,COMMAND,0xffffffff),
                     encode_record(ENVELOPE, COMMAND, b'\x55\xcc'+struct.pack('<HI',CAMERA_VIDEO,0)),
                     encode_record(ENVELOPE, COMMAND, b'\x55\xcc'+struct.pack('<HI',COMMAND,8))]:
            with self.assertRaises(ValueError):
                RecordParser().feed(wire)
        parser = RecordParser()
        parser.feed(encode_record(DISCARDED, 0, b'abc')[:-1])
        with self.assertRaises(ValueError):
            parser.finish()


if __name__ == '__main__':
    unittest.main()
