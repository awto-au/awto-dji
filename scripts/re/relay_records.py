"""Phone relay v1 framing and independent DUML decoding (no device I/O).

Header: AWTO, version u8=1, kind u8, channel u16 LE, length u32 LE.
Kinds: 1=original AOA envelope, 2=discarded USB bytes.
"""
import struct

from aoa_mux import CHANNELS

ENVELOPE, DISCARDED = 1, 2
MAX_RECORD = 1024 * 1024 + 8


def encode_record(kind, channel, payload):
    return struct.pack('<4sBBHI', b'AWTO', 1, kind, channel, len(payload)) + payload


class RecordParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data):
        self.buf.extend(data)
        records = []
        offset = 0
        while len(self.buf) - offset >= 12:
            magic, version, kind, channel, size = struct.unpack_from('<4sBBHI', self.buf, offset)
            if magic != b'AWTO' or version != 1 or kind not in (1, 2) or size > MAX_RECORD:
                raise ValueError('invalid relay v1 header (use --input-format raw for an old app)')
            if kind == ENVELOPE and channel not in CHANNELS:
                raise ValueError('invalid relay channel')
            if kind == DISCARDED and channel != 0:
                raise ValueError('discard record must use channel zero')
            end = offset + 12 + size
            if end > len(self.buf):
                break
            payload = bytes(self.buf[offset + 12:end])
            if kind == ENVELOPE:
                if len(payload) < 8 or payload[:2] != b'\x55\xcc':
                    raise ValueError('missing original AOA header')
                inner_channel, inner_size = struct.unpack_from('<HI', payload, 2)
                if inner_channel != channel or inner_size != len(payload) - 8:
                    raise ValueError('phone record and original AOA header disagree')
            records.append((kind, channel, payload))
            offset = end
        del self.buf[:offset]
        return records

    def finish(self):
        if self.buf:
            raise ValueError(f'truncated relay record: {len(self.buf)} bytes')


def _crc(seed, polynomial, data):
    for value in data:
        seed ^= value
        for _ in range(8):
            seed = (seed >> 1) ^ (polynomial if seed & 1 else 0)
    return seed


def command_verdict(wire):
    """Independent of the phone codec; retain wire protection and plaintext fields."""
    rejected = {'wire': wire.hex(), 'accepted': False}
    if (len(wire) < 13 or wire[0] != 0x55
            or (int.from_bytes(wire[1:3], 'little') & 1023) != len(wire)
            or _crc(0x77, 0x8c, wire[:3]) != wire[3]
            or _crc(0x3692, 0x8408, wire[:-2]) != int.from_bytes(wire[-2:], 'little')
            or ((wire[8] >> 5) & 3) == 3):
        return rejected
    mode = wire[8] & 7
    if mode not in (0, 3):
        return rejected
    sequence = int.from_bytes(wire[6:8], 'little')
    body = bytearray(wire[9:-2])
    if mode == 3:
        table = bytes.fromhex('784f2433282d3240236c642a766941517e6978464500')
        cursor = 0
        for position in range(len(body)):
            cursor = (cursor + 1) ^ (position & 15)
            if cursor > 21:
                cursor = 0
            body[position] ^= table[cursor] ^ ((sequence >> (8 * (position % 2))) & 255)
    return {'wire': wire.hex(), 'accepted': True, 'sequence': sequence,
            'protection': mode, 'cmdSet': body[0], 'cmdId': body[1],
            'payload': body[2:].hex()}

