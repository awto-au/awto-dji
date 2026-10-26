#!/usr/bin/env python3
"""Structural relationships between AOA envelopes, USB read chunks and the DUML
frames found outside any envelope ("bare"), from aoa_relay_server.py's RAWUDP log.
Companion to analyze_raw_capture.py; context in awto-dji#64.

Usage: python3 -I scripts/re/analyze_bare_frames.py <aoa_relay_server.log>
Log: tmp/logs/analyze_bare_frames.log
"""
import os
import re
import struct
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aoa_mux import AoaMux, CHANNELS  # noqa: E402

LINE_RE = re.compile(r"RAWUDP seq=(\d+) \+(\d+)B ([0-9a-f]+)")
CONNECTION_RE = re.compile(r"=== connection from ")


def crc8(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8C if seed & 1 else seed >> 1
    return seed & 0xFF


def crc16(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8408 if seed & 1 else seed >> 1
    return seed & 0xFFFF


def duml_frames(buf):
    """(offset, frame) for every CRC-valid DUML frame in buf, plus trailing tail length."""
    out = []
    i = 0
    n = len(buf)
    last_end = 0
    while i < n:
        if buf[i] == 0x55 and i + 4 <= n:
            length = buf[i + 1] | ((buf[i + 2] & 0x03) << 8)
            if length >= 13 and i + length <= n and crc8(0x77, buf[i:i + 3]) == buf[i + 3]:
                frame = bytes(buf[i:i + length])
                if crc16(0x3692, frame[:-2]) == int.from_bytes(frame[-2:], "little"):
                    out.append((i, frame))
                    i += length
                    last_end = i
                    continue
        i += 1
    return out, n - last_end


def load_segments(path):
    segments = [[]]
    with open(path) as f:
        for line in f:
            if CONNECTION_RE.search(line) and segments[-1]:
                segments.append([])
            m = LINE_RE.search(line)
            if m:
                segments[-1].append((int(m.group(1)), bytes.fromhex(m.group(3))))
    return [sorted(s) for s in segments if s]


def analyze(chunks, label):
    print(f"\n=== segment {label}: {len(chunks)} chunks ===")
    full = bytearray()
    bounds = []  # chunk start offsets
    for _, data in chunks:
        bounds.append(len(full))
        full.extend(data)
    full = bytes(full)
    bounds.append(len(full))
    starts = set(bounds)

    def chunk_index(pos):
        lo, hi = 0, len(bounds) - 2
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if bounds[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        return lo

    sizes = Counter(len(d) for _, d in chunks)
    print("chunk sizes (top 8):", sizes.most_common(8))
    print("chunks starting with 55cc:", sum(d[:2] == b"\x55\xcc" for _, d in chunks), "/", len(chunks))

    envelopes = []  # (start, size)
    runs = []  # (start, end) discarded
    pos = 0
    n = len(full)
    while pos < n:
        s = full.find(b"\x55\xcc", pos)
        if s < 0:
            s = n
        if s > pos:
            runs.append((pos, s))
        if s >= n or n - s < 8:
            break
        channel, size = struct.unpack_from("<HI", full, s + 2)
        if channel not in CHANNELS or size > 1024 * 1024 or s + 8 + size > n:
            pos = s + 1
            continue
        envelopes.append((s, size))
        pos = s + 8 + size

    # A. envelope at chunk start: how does declared size compare to the chunk?
    slack = Counter()
    at_chunk_start = 0
    for s, size in envelopes:
        if s in starts:
            at_chunk_start += 1
            ci = chunk_index(s)
            chunk_len = bounds[ci + 1] - bounds[ci]
            slack[chunk_len - 8 - size] += 1
    print(f"envelopes: {len(envelopes)}, starting exactly at a chunk start: {at_chunk_start}")
    print("  chunk_len - 8 - declared_size for those (0 = envelope is exactly the chunk):",
          slack.most_common(10))

    # B. where do envelopes end, and where do discard runs begin?
    end_at_chunk_end = sum((s + 8 + size) in starts for s, size in envelopes)
    print(f"envelopes ending exactly on a chunk boundary: {end_at_chunk_end}/{len(envelopes)}")
    run_at_chunk_start = sum(a in starts for a, _ in runs)
    print(f"discard runs: {len(runs)}, beginning exactly at a chunk start: {run_at_chunk_start}")
    run_spans_chunks = sum(chunk_index(a) != chunk_index(b - 1) for a, b in runs if b > a)
    print(f"discard runs spanning a chunk boundary: {run_spans_chunks}")

    # D. do envelope payloads end mid-frame (tail bytes after last complete DUML frame)?
    tails = Counter()
    env_frames = []
    for s, size in envelopes:
        frames, tail = duml_frames(full[s + 8:s + 8 + size])
        tails[tail] += 1
        env_frames.extend(f for _, f in frames)
    print("envelope payload tail after last complete DUML frame (0 = ends cleanly), top 10:",
          tails.most_common(10))

    # C. are bare frames duplicates of enveloped frames?
    bare = []
    heads = Counter()  # leading bytes of a run before its first frame
    for a, b in runs:
        frames, _ = duml_frames(full[a:b])
        if frames:
            heads[frames[0][0]] += 1
        bare.extend(f for _, f in frames)
    env_set = set(env_frames)
    dup = sum(f in env_set for f in bare)
    print(f"bare frames: {len(bare)}, byte-identical to some enveloped frame: {dup}")
    print("bytes preceding first bare frame in a run (0 = run starts with the frame), top 8:",
          heads.most_common(8))

    # E. per-field "same as previous frame?" rates, bare vs enveloped, in stream order.
    ordered = []
    for s, size in envelopes:
        for off, f in duml_frames(full[s + 8:s + 8 + size])[0]:
            ordered.append((s + 8 + off, "env", f))
    for a, b in runs:
        for off, f in duml_frames(full[a:b])[0]:
            ordered.append((a + off, "bare", f))
    ordered.sort()
    fields = {
        "sender": lambda f: f[4], "receiver": lambda f: f[5],
        "cmd_type": lambda f: f[8], "protection": lambda f: f[8] & 7,
        "ack": lambda f: (f[8] >> 5) & 3, "cmdset_raw": lambda f: f[9],
        "cmdid_raw": lambda f: f[10], "length": lambda f: len(f),
    }
    same = {k: Counter() for k in fields}
    total = Counter()
    prev = None
    for _, origin, f in ordered:
        if prev is not None:
            total[origin] += 1
            for k, fn in fields.items():
                if fn(f) == fn(prev):
                    same[k][origin] += 1
        prev = f
    print("P(field same as previous frame):  field  bare  enveloped")
    for k in fields:
        pb = same[k]["bare"] / total["bare"] if total["bare"] else 0
        pe = same[k]["env"] / total["env"] if total["env"] else 0
        print(f"  {k:<12} {pb:6.1%} {pe:9.1%}")
    # Previous frame's origin: does bare follow bare?
    trans = Counter()
    prev_o = None
    for _, origin, _ in ordered:
        if prev_o is not None:
            trans[(prev_o, origin)] += 1
        prev_o = origin
    print("origin transitions (prev -> this):", dict(trans))

    # F. lag test: does the declared size equal a neighbouring read's payload length?
    lens = [len(d) for _, d in chunks]
    declared = {}
    for s, size in envelopes:
        declared[chunk_index(s)] = size
    lag_hits = Counter()
    tested = 0
    for ci, size in declared.items():
        tested += 1
        for lag in (-3, -2, -1, 0, 1, 2, 3):
            j = ci + lag
            if 0 <= j < len(lens) and lens[j] - 8 == size:
                lag_hits[lag] += 1
    print(f"declared size == (read_len - 8) of read k+lag, over {tested} envelopes:",
          {lag: lag_hits[lag] for lag in (-3, -2, -1, 0, 1, 2, 3)})
    # Exact-permutation check: multiset of declared sizes vs multiset of payload lengths.
    print("multiset(declared sizes) == multiset(read_len-8)?",
          Counter(declared.values()) == Counter(l - 8 for l in lens))
    # Declared sizes seen on the 16384-byte reads (kernel-capped) and what preceded them.
    for ci, size in declared.items():
        if lens[ci] >= 16384:
            print(f"  16K read #{ci}: declared={size}, prev read len={lens[ci - 1] if ci else None}, "
                  f"next read len={lens[ci + 1] if ci + 1 < len(lens) else None}")

    # G. in reads with a bare tail: does the first tail frame continue the sequence?
    cont = Counter()
    for s, size in envelopes:
        ci = chunk_index(s)
        chunk_end = bounds[ci + 1]
        env_end = s + 8 + size
        if env_end >= chunk_end:
            continue
        ef, _ = duml_frames(full[s + 8:env_end])
        bf, _ = duml_frames(full[env_end:chunk_end])
        if not ef or not bf:
            continue
        last = ef[-1][1]
        first = bf[0][1]
        if last[4] != first[4]:
            cont["different sender"] += 1
            continue
        d = ((first[6] | first[7] << 8) - (last[6] | last[7] << 8)) & 0xFFFF
        cont[f"seq delta {d}" if d <= 3 else "seq delta >3"] += 1
    print("first bare-tail frame vs last enveloped frame in the same read:", dict(cont))

    # H. raw per-read table + tail provenance.
    def seq_of(f):
        return f[6] | f[7] << 8

    seen = set()
    dup_bare = dup_env = n_bare = n_env = 0
    signed = Counter()
    prev_left = None
    decl_eq_prev_left = decl_eq_prev_len = 0
    rows = []
    for ci in range(len(lens)):
        s = bounds[ci]
        if ci not in declared:
            continue
        size = declared[ci]
        env_end = min(s + 8 + size, bounds[ci + 1])
        ef, mid = duml_frames(full[s + 8:env_end])
        bf, _ = duml_frames(full[env_end:bounds[ci + 1]])
        for _, f in ef:
            n_env += 1
            if f in seen:
                dup_env += 1
            seen.add(f)
        for _, f in bf:
            n_bare += 1
            if f in seen:
                dup_bare += 1
            seen.add(f)
        if ef and bf and ef[-1][1][4] == bf[0][1][4]:
            d = seq_of(bf[0][1]) - seq_of(ef[-1][1])
            if d > 32768:
                d -= 65536
            if d < -32768:
                d += 65536
            signed[max(-50, min(50, d))] += 1
        left = lens[ci] - 8 - size
        if prev_left is not None and size == prev_left:
            decl_eq_prev_left += 1
        if ci and size == lens[ci - 1] - 8:
            decl_eq_prev_len += 1
        prev_left = left
        if len(rows) < 40:
            rows.append(f"  #{ci:<4} len={lens[ci]:<5} decl={size:<5} slack={left:<5} midframe_tail={mid:<3} "
                        f"decl=[{' '.join(f'{f[4]:02x}:{seq_of(f)}/{len(f)}' for _, f in ef)}] "
                        f"tail=[{' '.join(f'{f[4]:02x}:{seq_of(f)}/{len(f)}' for _, f in bf)}]")
    print(f"frames identical to an earlier frame anywhere: bare {dup_bare}/{n_bare}, enveloped {dup_env}/{n_env}")
    print("signed seq offset, first tail frame - last declared frame (same sender), clamped +-50:",
          sorted(signed.items()))
    print(f"declared_k == leftover_(k-1): {decl_eq_prev_left}; declared_k == len_(k-1)-8: {decl_eq_prev_len}")
    print("first 40 reads (sender:seq/len):")
    print("\n".join(rows))

    # I. header-direct per-read model, independent of AoaMux. Tests:
    #   straddle: fragment at the end of read k + payload of read k+1 (header skipped)
    #   CRC-validates as one DUML frame.
    internal_headers = sum(d.count(b"\x55\xcc\x49\x57", 1) for _, d in chunks)
    print(f"55cc4957 occurrences inside reads (offset>0): {internal_headers}")
    reads = []
    for _, d in chunks:
        if d[:2] != b"\x55\xcc":
            reads.append(None)
            continue
        ch, size = struct.unpack_from("<HI", d, 2)
        reads.append((ch, size, d[8:]))
    straddle_ok = straddle_fail = 0
    deficit_eq_next = 0
    short_reads = 0
    for k in range(len(reads) - 1):
        r, nxt = reads[k], reads[k + 1]
        if r is None or nxt is None:
            continue
        ch, size, payload = r
        if size <= len(payload):
            continue
        short_reads += 1
        deficit = size - len(payload)
        if deficit == len(nxt[2]) or deficit == nxt[1]:
            deficit_eq_next += 1
        frames, frag = duml_frames(payload)
        if frag == 0:
            continue
        joined = payload[len(payload) - frag:] + nxt[2]
        jf, _ = duml_frames(joined)
        if jf and jf[0][0] == 0:
            straddle_ok += 1
        else:
            straddle_fail += 1
    print(f"reads with declared > actual payload: {short_reads}; deficit == next read's payload or "
          f"declared size: {deficit_eq_next}; fragment+next payload forms a valid frame: "
          f"{straddle_ok} ok / {straddle_fail} fail")
    for k in range(min(10, len(reads))):
        if reads[k] is None:
            print(f"  read#{k}: no 55cc header")
            continue
        ch, size, payload = reads[k]
        print(f"  read#{k}: len={len(payload) + 8} ch={ch:#06x} declared={size} payload={payload.hex()}")

    # Sample: first 3 runs with context.
    for a, b in runs[:3]:
        ci = chunk_index(a)
        print(f"  run @{a}-{b} ({b - a}B) chunk#{ci} local={a - bounds[ci]} "
              f"chunk_len={bounds[ci + 1] - bounds[ci]} head={full[a:a + 16].hex()}")


def main():
    segments = load_segments(sys.argv[1])
    for i, chunks in enumerate(segments):
        analyze(chunks, i)


if __name__ == "__main__":
    main()
