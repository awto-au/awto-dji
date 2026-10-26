"""Incremental AOA envelope parser, independently implemented from wire-format facts.

Wire format: 55 cc, channel u16 LE, payload length u32 LE, payload.
APK UsbAccessoryService and usb/P3/b.java corroborate channels 0x5749..0x574d.
USB/TCP reads need not align with envelope boundaries. No device I/O here.

Real captures (awto-dji#64) show not every byte on the command channel is `55 cc`-
enveloped: DUML frames sometimes arrive bare, with no envelope wrapper at all,
interleaved with properly-enveloped ones from the same sender. Confirmed by two
independent checks on live data: CRC8+CRC16 together give ~1-in-16.7M odds of a random
byte run passing both (expected ~0 accidental matches over the discarded bytes in that
capture; got thousands), and DUML sequence numbers across bare and enveloped frames from
one sender are continuous (53% of consecutive transitions exactly prev+1, far beyond
chance). So when envelope-matching fails at the current scan position, this also tries a
bare DUML frame before falling back to a true discard - mirrors
app/awto_dji_app/lib/transport/aoa_mux.dart, keep the two in sync.
"""
import struct
from collections import Counter
from typing import NamedTuple

from duml_proto import crc8, crc16

COMMAND = 0x5749
CAMERA_VIDEO = 0x574A
FPV_VIDEO = 0x574B
CHANNELS = range(0x5749, 0x574E)
MIN_DUML_FRAME = 13  # SOF+verlen+hdrcrc8+sender+receiver+seq+cmdtype+cmdset+cmdid+crc16


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

    def _bare_duml_length(self, offset):
        """Length of a CRC-valid bare DUML frame at offset, None if invalid, 0 if not
        enough buffered yet to tell (caller should wait, not conclude it's not a frame).

        Checks the 8-bit header CRC - cheap, only needs 4 bytes - before ever waiting for
        the rest of a declared-length frame, so a coincidental 0x55 whose next two bytes
        decode to a large length (e.g. the leftover bytes of a rejected, oversized-for-
        max_payload envelope header) can't stall resync waiting for bytes that will never
        validate.
        """
        if len(self.buf) - offset < 4:
            return 0
        length = (self.buf[offset + 1] | (self.buf[offset + 2] << 8)) & 0x3FF
        if length < MIN_DUML_FRAME:
            return None
        if crc8(0x77, self.buf[offset:offset + 3]) != self.buf[offset + 3]:
            return None
        if len(self.buf) - offset < length:
            return 0
        frame = self.buf[offset:offset + length]
        stored_crc = frame[-2] | (frame[-1] << 8)
        if crc16(0x3692, frame[:-2]) != stored_crc:
            return None
        return length

    def feed(self, data):
        self.buf.extend(data)
        result = []
        offset = 0
        n = len(self.buf)
        discard_start = 0
        while offset < n:
            if self.buf[offset] != 0x55:
                offset += 1
                continue
            if n - offset >= 2 and self.buf[offset + 1] == 0xCC and n - offset >= 8:
                channel, size = struct.unpack_from('<HI', self.buf, offset + 2)
                if channel in CHANNELS and size <= self.max_payload:
                    end = offset + 8 + size
                    if end > n:
                        break
                    # On the command channel, the sender's declared envelope
                    # length occasionally overstates the real DUML frame
                    # inside it, swallowing the next envelope's header into
                    # this payload (docs/aoa-live-test-2026-10-26.md). Trim to
                    # the actual CRC-valid DUML length when it's shorter, same
                    # check as the bare-frame path - keep in sync with
                    # aoa_mux.dart.
                    payload_end = end
                    if channel == COMMAND:
                        real_length = self._bare_duml_length(offset + 8)
                        if real_length and real_length < size:
                            payload_end = offset + 8 + real_length
                    self.discarded += offset - discard_start
                    payload = bytes(self.buf[offset + 8:payload_end])
                    packet = MuxPacket(channel, payload)
                    result.append(packet)
                    self.packets[channel] += 1
                    self.payload_bytes[channel] += len(payload)
                    offset = payload_end
                    discard_start = payload_end
                    continue
            elif n - offset >= 2 and self.buf[offset + 1] == 0xCC:
                break  # looks like an envelope start, not enough bytes for the header yet
            bare_length = self._bare_duml_length(offset)
            if bare_length == 0:
                break
            if bare_length is not None:
                self.discarded += offset - discard_start
                payload = bytes(self.buf[offset:offset + bare_length])
                packet = MuxPacket(COMMAND, payload)
                result.append(packet)
                self.packets[COMMAND] += 1
                self.payload_bytes[COMMAND] += bare_length
                offset += bare_length
                discard_start = offset
                continue
            offset += 1
        self.discarded += offset - discard_start
        if offset:
            del self.buf[:offset]
        return result

    def finish(self):
        """Discard an incomplete envelope at a connection/capture boundary."""
        trailing = len(self.buf)
        self.discarded += trailing
        self.buf.clear()
        return trailing
