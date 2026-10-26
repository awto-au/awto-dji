#!/usr/bin/env python3
"""Reconstruct the true raw accessory byte stream from aoa_relay_server.py's
"RAWUDP seq=N +MB <hex>" log lines, per TCP connection, then feed each segment
through the real aoa_mux.AoaMux parser as ONE continuous buffer (no chunk
boundaries at all, since a chunking bug would be the first suspect otherwise).

Must segment by connection: UdpRawRelay's seq counter resets to 0 on every
AoaTransport.connect() call (same code path that opens a fresh TCP connection),
so concatenating raw chunks across connections by seq number alone silently
collides two unrelated byte streams - this cost one wrong 15KB-discard "finding"
before the bug was caught (see git log for scripts/re/analyze_raw_capture.py).

Usage: python3 -I scripts/re/analyze_raw_capture.py <path-to-aoa_relay_server.log>
"""
import os
import re
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aoa_mux import AoaMux  # noqa: E402

LINE_RE = re.compile(r"RAWUDP seq=(\d+) \+(\d+)B ([0-9a-f]+)")
CONNECTION_RE = re.compile(r"=== connection from ")
PRINT_DISCARD_THRESHOLD = 32  # bytes - small discards (a few noise bytes) are routine; print only the notable ones


def load_segments(path):
    segments = [{}]
    with open(path) as f:
        for line in f:
            if CONNECTION_RE.search(line) and segments[-1]:
                segments.append({})
            m = LINE_RE.search(line)
            if not m:
                continue
            seq, length, hexstr = m.groups()
            seq = int(seq)
            data = bytes.fromhex(hexstr)
            if len(data) != int(length):
                print(f"WARN seq={seq}: logged length {length} != hex byte count {len(data)}")
            segments[-1][seq] = data
    return [s for s in segments if s]


def analyze_segment(chunks, label):
    print(f"\n=== segment {label} ===")
    seqs = sorted(chunks)
    print(f"{len(seqs)} UDP chunks, seq range {seqs[0]}..{seqs[-1]}")
    gaps = [b for a, b in zip(seqs, seqs[1:]) if b != a + 1]
    if gaps:
        print(f"sequence gaps (missing/reordered datagrams): {gaps}")

    full = bytearray()
    offsets = []  # (start_offset_in_full_stream, length, seq), sorted by start
    for seq in seqs:
        offsets.append((len(full), len(chunks[seq]), seq))
        full.extend(chunks[seq])
    print(f"total reconstructed stream: {len(full)} bytes")

    def chunk_at(pos):
        for start, length, seq in offsets:
            if start <= pos < start + length:
                return seq, pos - start
        return None, None

    mux = AoaMux()
    packets = mux.feed(bytes(full))
    pct = 100 * mux.discarded / len(full) if full else 0
    print(f"parsed {len(packets)} complete envelopes in one pass, "
          f"discarded={mux.discarded} bytes ({pct:.1f}%), buf remaining={len(mux.buf)}")

    pos = 0
    n = len(full)
    envelope_n = 0
    discard_n = 0
    discard_total = 0
    while pos < n:
        start = full.find(b"\x55\xcc", pos)
        if start < 0:
            print(f"end of stream: {n - pos} trailing undecodable bytes from pos={pos}")
            break
        if start > pos:
            discard_n += 1
            discard_total += start - pos
            if start - pos >= PRINT_DISCARD_THRESHOLD:
                seq, local = chunk_at(pos)
                print(f"DISCARD {start - pos}B at stream-pos {pos} (chunk seq={seq} "
                      f"local-offset={local}): {full[pos:start].hex()}")
        if n - start < 8:
            print(f"end of stream: incomplete header at pos={start}")
            break
        channel, size = struct.unpack_from("<HI", full, start + 2)
        if channel < 0x5749 or channel > 0x574D or size > mux.max_payload:
            pos = start + 1
            continue
        end = start + 8 + size
        envelope_n += 1
        complete = end <= n
        if not complete:
            seq, local = chunk_at(start)
            print(f"ENVELOPE #{envelope_n} at stream-pos={start} (chunk seq={seq} "
                  f"local-offset={local}) channel={channel:#06x} declared_len={size} "
                  f"INCOMPLETE (need {end - n} more bytes) - end of segment")
            break
        pos = end

    print(f"second pass: {envelope_n} envelopes, {discard_n} discard runs "
          f"totalling {discard_total}B (threshold for detail: {PRINT_DISCARD_THRESHOLD}B)")


def main():
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <aoa_relay_server.log>")
        sys.exit(1)
    segments = load_segments(sys.argv[1])
    print(f"{len(segments)} connection segment(s)")
    for i, chunks in enumerate(segments):
        analyze_segment(chunks, i)


if __name__ == "__main__":
    main()
