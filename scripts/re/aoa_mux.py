"""Incremental AOA envelope parser, independently implemented from wire-format facts.

Wire format: 55 cc, channel u16 LE, payload length u32 LE, payload.
APK UsbAccessoryService and usb/P3/b.java corroborate channels 0x5749..0x574d.
USB/TCP reads need not align with envelope boundaries. No device I/O here.
"""
import struct
from collections import Counter
from typing import NamedTuple

COMMAND = 0x5749
CAMERA_VIDEO = 0x574A
FPV_VIDEO = 0x574B
CHANNELS = range(0x5749, 0x574E)


class MuxPacket(NamedTuple):
    channel: int
    payload: bytes


class AoaMux:
    def __init__(self, max_payload=1024 * 1024):
        if max_payload < 1:
            raise ValueError('max_payload must be positive')
        self.max_payload = max_payload
        self.buf = bytearray()
        self.discarded = 0
        self.packets = Counter()
        self.payload_bytes = Counter()

    def feed(self, data):
        self.buf.extend(data)
        result = []
        offset = 0
        while True:
            start = self.buf.find(b'\x55\xcc', offset)
            if start < 0:
                # Preserve a possible split magic prefix.
                keep = 1 if self.buf[offset:] and self.buf[-1] == 0x55 else 0
                end = len(self.buf) - keep
                self.discarded += end - offset
                offset = end
                break
            self.discarded += start - offset
            offset = start
            if len(self.buf) - offset < 8:
                break
            channel, size = struct.unpack_from('<HI', self.buf, offset + 2)
            if channel not in CHANNELS or size > self.max_payload:
                self.discarded += 1
                offset += 1
                continue
            end = offset + 8 + size
            if end > len(self.buf):
                break
            payload = bytes(self.buf[offset + 8:end])
            result.append(MuxPacket(channel, payload))
            self.packets[channel] += 1
            self.payload_bytes[channel] += size
            offset = end
        if offset:
            del self.buf[:offset]
        return result

    def finish(self):
        """Discard an incomplete envelope at a connection/capture boundary."""
        trailing = len(self.buf)
        self.discarded += trailing
        self.buf.clear()
        return trailing
