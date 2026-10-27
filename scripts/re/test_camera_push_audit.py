"""Regression against a real protected capture, not manufactured wire bytes."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from camera_push_audit import audit
from relay_records import command_verdict

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'app/packages/duml/test/fixtures/captured_camera_pushes.json'


class CameraPushAuditTests(unittest.TestCase):
    def test_saved_fixture_reproduces_from_raw_command_channel(self):
        expected = json.loads(FIXTURE.read_text())
        result = audit(ROOT / 'captures/sessions/2026-10-23/aoa_relay_server.log')
        self.assertEqual(result, expected)
        messages = {m['cmd_id']: m for m in result['messages']}
        self.assertEqual(messages[0x80]['count'], 7)
        self.assertEqual(messages[0x81]['count'], 3)
        self.assertNotIn(0x82, messages)
        self.assertEqual(messages[0x83]['count'], 1)
        self.assertEqual(messages[0x80]['decoded_prefix'],
                         {'connected': True, 'camera_type': 4})
        self.assertEqual(messages[0x81]['decoded_prefix'],
                         {'resolution_code': 22, 'frame_rate_code': 1,
                          'container_code': 1})

    def test_captured_simple_frames_validate_and_corruption_is_rejected(self):
        for row in json.loads(FIXTURE.read_text())['messages']:
            wire = bytes.fromhex(row['first_wire'])
            decoded = command_verdict(wire)
            self.assertTrue(decoded['accepted'])
            self.assertEqual(decoded['protection'], 3)
            self.assertEqual(decoded['cmdId'], row['cmd_id'])
            self.assertEqual(decoded['payload'], row['payload'])
            corrupt = bytearray(wire)
            corrupt[15] ^= 1
            self.assertFalse(command_verdict(corrupt)['accepted'])


if __name__ == '__main__':
    unittest.main()
