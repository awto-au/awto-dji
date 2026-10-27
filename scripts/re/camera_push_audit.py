#!/usr/bin/env python3
"""Offline camera-push evidence from raw AOA .bin or +<n>B <hex> relay logs.

Only the command channel is scanned, with both CRCs validated before SIMPLE
decoding. Connection boundaries reset both envelope and DUML accumulation. Output
retains wire bytes and raw values; it does not pretend to observe a DJI GO screen.
Usage: python3 scripts/re/camera_push_audit.py CAPTURE [--out REPORT.json]
"""
import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aoa_chunk_decode import duml_frames
from aoa_mux import AoaMux, COMMAND
from duml_generated import camera_push_state, camera_shot_params
from relay_records import command_verdict


def raw_sessions(path):
    if path.suffix == '.bin':
        yield path.read_bytes()
        return
    raw = bytearray()
    for line in path.read_text(errors='replace').splitlines():
        if line.startswith('=== connection from') and raw:
            yield bytes(raw)
            raw.clear()
        match = re.search(r'\+(\d+)B ([0-9a-fA-F]+)', line)
        if match:
            chunk = bytes.fromhex(match[2])
            if len(chunk) != int(match[1]):
                raise ValueError('truncated raw log line; full AOA bytes required')
            raw.extend(chunk)
    if raw:
        yield bytes(raw)


def audit(path):
    path = Path(path)
    messages = {}
    channels = collections.Counter()
    discarded = trailing = valid = sessions = 0
    for stream in raw_sessions(path):
        sessions += 1
        mux = AoaMux()
        commands = b''.join(p.payload for p in mux.feed(stream) if p.channel == COMMAND)
        channels.update(mux.packets)
        discarded += mux.discarded
        trailing += mux.finish()
        for wire in duml_frames(commands):
            valid += 1
            verdict = command_verdict(wire)
            if not verdict['accepted'] or verdict['cmdSet'] != 2:
                continue
            cid = verdict['cmdId']
            if cid not in (0x80, 0x81, 0x82, 0x83):
                continue
            # Exactly camera index 0 -> app index 0, push (not response/ACK).
            if wire[4:6] != b'\x01\x02' or wire[8] & 0xe0:
                continue
            payload = bytes.fromhex(verdict['payload'])
            key = (cid, payload.hex())
            if key in messages:
                messages[key]['count'] += 1
                continue
            decoder = {0x80: camera_push_state.decode,
                       0x81: camera_shot_params.decode}.get(cid)
            messages[key] = {
                'cmd_id': cid, 'count': 1, 'payload_length': len(payload),
                'payload': payload.hex(), 'first_wire': wire.hex(),
                'decoded_prefix': decoder(payload) if decoder else None,
            }
    return {
        'source_name': path.name,
        'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'scope': 'Wire values observed; labels require classic GO interpretation. '
                 'No simultaneous camera-setting screen or recorded-file check.',
        'sessions': sessions,
        'channel_envelopes': {f'0x{k:04x}': v for k, v in sorted(channels.items())},
        'discarded_bytes': discarded,
        'trailing_bytes': trailing,
        'crc_valid_command_frames': valid,
        'messages': [messages[k] for k in sorted(messages)],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    output = json.dumps(audit(args.capture), indent=2) + '\n'
    if args.out:
        args.out.write_text(output)
    else:
        print(output, end='')


if __name__ == '__main__':
    main()
