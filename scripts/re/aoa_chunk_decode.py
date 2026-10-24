#!/usr/bin/env python3
"""Demultiplex a raw RC->phone AOA byte stream into FX3 chunks and decode the DUML inside.

The ground FX3 (m1601, docs/ground-fx3-m1601.md) prefixes every RC->phone USB chunk with
  55 CC <u16 type LE> <u32 length LE> <payload>
type 0x5749 = DUML (frames from the FX3 UART, back to back), 0x574A = video (one FPGA buffer,
H.264 Annex-B). This tool reads aoa_relay_server.py logs ("+<n>B <hex>" lines) or a raw .bin,
walks the chunks, CRC-checks (CRC8 seed 0x77, CRC16 seed 0x3692) every DUML frame, and
reports chunk counts and DUML sender/receiver device types.

Usage:  python3 scripts/re/aoa_chunk_decode.py captures/sessions/2026-10-23/aoa_relay_server.log
"""
import collections
import re
import sys

TYPE_DUML, TYPE_VIDEO = 0x5749, 0x574A


def crc8(b, c=0x77):
    for x in b:
        c ^= x
        for _ in range(8):
            c = (c >> 1) ^ 0x8C if c & 1 else c >> 1
    return c


def crc16(b, c=0x3692):
    for x in b:
        c ^= x
        for _ in range(8):
            c = (c >> 1) ^ 0x8408 if c & 1 else c >> 1
    return c


def read_stream(path):
    if path.endswith(".bin"):
        return open(path, "rb").read()
    blob = bytearray()
    for line in open(path, errors="replace"):
        m = re.search(r"\+\d+B ([0-9a-f]+)", line)
        if m:
            h = m.group(1)
            blob += bytes.fromhex(h[:len(h) // 2 * 2])
    return bytes(blob)


def duml_frames(p):
    j = 0
    while j + 13 <= len(p):
        n = int.from_bytes(p[j + 1:j + 3], "little") & 0x3FF
        if (p[j] == 0x55 and 13 <= n and j + n <= len(p) and crc8(p[j:j + 3]) == p[j + 3]
                and crc16(p[j:j + n - 2]) == int.from_bytes(p[j + n - 2:j + n], "little")):
            yield p[j:j + n]
            j += n
        else:
            j += 1


def main():
    s = read_stream(sys.argv[1])
    kinds, senders, flows = collections.Counter(), collections.Counter(), collections.Counter()
    in_video, i = 0, 0
    while (i := s.find(b"\x55\xcc", i)) != -1 and i + 8 <= len(s):
        t, n = int.from_bytes(s[i + 2:i + 4], "little"), int.from_bytes(s[i + 4:i + 8], "little")
        if t not in (TYPE_DUML, TYPE_VIDEO) or n > 0x1000:
            i += 1
            continue
        p = s[i + 8:i + 8 + n]
        kinds["DUML" if t == TYPE_DUML else "video"] += 1
        for f in duml_frames(p):
            if t == TYPE_DUML:
                senders[f[4] & 0x1F] += 1
                flows[(f[4] & 0x1F, f[5] & 0x1F)] += 1
            else:
                in_video += 1
        i += 8 + len(p)
    print(f"{len(s)} bytes; chunks {dict(kinds)}")
    print(f"CRC-valid DUML frames in DUML chunks: {sum(senders.values())}; inside video chunks: {in_video}")
    print("DUML senders (device type: frames):", dict(senders.most_common()))
    print("sender->receiver:", {f"{a}->{b}": c for (a, b), c in flows.most_common()})


if __name__ == "__main__":
    main()
