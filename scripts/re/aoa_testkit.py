#!/usr/bin/env python3
"""AOAT test frames, payload patterns, checkers and the test catalog. Pure Python, no
hardware, no app dependency: the same catalog drives the phone bench app (bench_host.py),
t600_rc_emulator.py, and later a Cynthion RISC-V port. Dart mirror:
app/awto_dji_app/lib/bench/aoat.dart (golden vectors: aoat_vectors.json, keep in sync).

AOAT frame (little endian), min 24 bytes:
  0  magic 'AOAT'   4  test_id u16   6  pattern u8   7  flags u8 (bit0 = last of run, bit1 = no CRC)
  8  run_seed u32  12  seq u32       16 total_len u32 (header+payload+crc)
  20 payload (total_len-24 bytes)    -4 crc32 over all preceding bytes (zlib crc32)
Transfers shorter than 24 bytes cannot hold a header: `short_transfer()` gives raw
address-pattern bytes, verified by length (and bytes if the receiver knows seed/seq).
"""
import dataclasses
import random
import struct
import zlib

MAGIC = b"AOAT"
HDR = 20
MIN_FRAME = 24
MASK = 0xFFFFFFFF
FLAG_LAST = 1
FLAG_NOCRC = 2  # crc field present (zero) but not checked: a sender with no CRC code (Cynthion RISC-V)

P_ADDR, P_COUNTER, P_RANDOM, P_ZEROS, P_ONES, P_ALT, P_PRBS, P_FIXED, P_RAMP = range(9)
PATTERN_NAMES = {"addr": P_ADDR, "counter": P_COUNTER, "random": P_RANDOM,
                 "zeros": P_ZEROS, "ones": P_ONES, "alt": P_ALT, "prbs": P_PRBS,
                 "fixed": P_FIXED, "ramp": P_RAMP}
P_LAST = P_RAMP

# Bulk max packet sizes: 64 = full speed, 512 = high speed (1024 = super speed).
MAX_PACKETS = (64, 512)

# Size sweep (transfer = whole frame bytes). Bounds: 0 = empty, 65536 = 1 pow-2 over the
# 16-bit limit, where length fields and 64 KiB buffers break.
SIZES = (0, 1, 2, 3, 7, 8, 15, 16, 31, 32, 63, 64, 65, 127, 128, 255, 256, 511, 512, 513,
         1023, 1024, 1025, 4095, 4096, 16383, 16384, 65535, 65536)


def zlp_sizes(max_packets=MAX_PACKETS):
    """Transfer sizes that are exact multiples of a bulk max packet: the host/device must
    end the transfer with a zero-length packet, else it 'never ends'."""
    return tuple(sorted({m * k for m in max_packets for k in (1, 2, 4, 32, 128)}))


def mix(seed, seq, test_id):
    return ((seq * 0x9E3779B1) ^ seed ^ (test_id << 16)) & MASK


def _xorshift_bytes(state, n):
    out = bytearray(n)
    state = state or 1
    for i in range(n):
        state ^= (state << 13) & MASK
        state ^= state >> 17
        state ^= (state << 5) & MASK
        out[i] = state & 0xFF
    return bytes(out)


def _prbs15_bytes(state, n):
    """PRBS15 (x^15+x^14+1), MSB-first bytes; state = seed-derived, never 0."""
    state = (state & 0x7FFF) or 1
    out = bytearray(n)
    for i in range(n):
        b = 0
        for _ in range(8):
            fb = ((state >> 14) ^ (state >> 13)) & 1
            state = ((state << 1) | fb) & 0x7FFF
            b = (b << 1) | fb
        out[i] = b
    return bytes(out)


def rand_size(lo, hi, seed, seq, test_id=0):
    """Deterministic frame size in [lo, hi] for frame `seq` (source `size_min`/`size_max`)."""
    x = mix(seed, seq, test_id) ^ 0xA5A5A5A5
    x ^= (x << 13) & MASK
    x ^= x >> 17
    x ^= (x << 5) & MASK
    return lo + x % (hi - lo + 1)


def make_payload(pattern, n, seed, seq, test_id=0):
    """Deterministic payload; identical in Dart (aoat.dart makePayload)."""
    if pattern == P_ADDR:
        m = mix(seed, seq, test_id)
        words = (n + 3) // 4
        return b"".join(struct.pack("<I", ((4 * i) ^ m) & MASK) for i in range(words))[:n]
    if pattern == P_COUNTER:
        return bytes((i + seq) & 0xFF for i in range(n))
    if pattern == P_RANDOM:
        return _xorshift_bytes(mix(seed, seq, test_id), n)
    if pattern == P_ZEROS:
        return bytes(n)
    if pattern == P_ONES:
        return b"\xff" * n
    if pattern == P_ALT:
        return bytes(0xAA if i % 2 == 0 else 0x55 for i in range(n))
    if pattern == P_PRBS:
        return _prbs15_bytes(mix(seed, seq, test_id), n)
    if pattern == P_FIXED:  # byte value = seed low byte
        return bytes([seed & 0xFF]) * n
    if pattern == P_RAMP:  # starts at seed low byte, same every frame
        return bytes((seed + i) & 0xFF for i in range(n))
    raise ValueError(f"unknown pattern {pattern}")


def build_frame(total_len, pattern, seed, seq, test_id=0, flags=0):
    """AOAT frame of exactly total_len bytes (>= 24)."""
    if total_len < MIN_FRAME:
        raise ValueError(f"AOAT frame needs >= {MIN_FRAME} bytes, got {total_len}")
    body = make_payload(pattern, total_len - MIN_FRAME, seed, seq, test_id)
    head = MAGIC + struct.pack("<HBBIII", test_id, pattern, flags, seed, seq, total_len)
    pre = head + body
    return pre + struct.pack("<I", zlib.crc32(pre) & MASK)


def expected_source(count, size=64, seed=1, pattern="addr", test_id=0, size_min=None,
                    size_max=None, first_seq=0):
    """Transfers the app's source mode writes for the same mode params (the harness regenerates
    its expectation from the shared test_id/seed). size_min/size_max = random sizes."""
    pat = PATTERN_NAMES[pattern]
    lo = size_min if size_min is not None else size
    hi = size_max if size_max is not None else lo
    for seq in range(first_seq, first_seq + count):
        n = rand_size(lo, hi, seed, seq, test_id) if hi > lo else lo
        yield make_payload(P_ADDR, n, seed, seq, test_id) if n < MIN_FRAME else \
            build_frame(n, pat, seed, seq, test_id)


def short_transfer(n, seed, seq, test_id=0):
    """Transfers under 24 bytes: raw address-pattern bytes, no header."""
    return make_payload(P_ADDR, n, seed, seq, test_id)


@dataclasses.dataclass
class Mismatch:
    seq: int
    offset: int          # payload byte offset of the first differing byte
    got: bytes
    expected: bytes
    hint: str = ""       # for addr pattern: which offset the received word names

    def as_dict(self):
        return {"seq": self.seq, "offset": self.offset, "got": self.got.hex(),
                "expected": self.expected.hex(), "hint": self.hint}


def first_mismatch(got, expected, pattern=None, seed=0, seq=0, test_id=0):
    """Offset of the first differing byte, with the address hint for the addr pattern
    (received word XOR mix = the offset that word was generated for)."""
    n = min(len(got), len(expected))
    for i in range(n):
        if got[i] != expected[i]:
            hint = ""
            if pattern == P_ADDR:
                w = i & ~3
                if len(got) >= w + 4:
                    src = struct.unpack_from("<I", got, w)[0] ^ mix(seed, seq, test_id)
                    hint = f"word at {w} carries address {src}"
            return Mismatch(seq, i, bytes(got[i:i + 4]), bytes(expected[i:i + 4]), hint)
    if len(got) != len(expected):
        return Mismatch(seq, n, bytes(got[n:n + 4]), bytes(expected[n:n + 4]),
                        f"length got {len(got)} expected {len(expected)}")
    return None


@dataclasses.dataclass
class Report:
    frames: int = 0
    bytes: int = 0
    bad_frames: int = 0
    crc_bad: int = 0
    seq_gaps: int = 0
    seq_dups: int = 0
    resync_bytes: int = 0
    short: int = 0
    zlp: int = 0
    first_mismatch: Mismatch | None = None

    @property
    def passed(self):
        return not (self.bad_frames or self.seq_gaps or self.seq_dups or self.resync_bytes)

    def as_dict(self):
        d = dataclasses.asdict(self)
        d["first_mismatch"] = self.first_mismatch.as_dict() if self.first_mismatch else None
        d["pass"] = self.passed
        return d


class Checker:
    """Stream parser + verifier for AOAT frames. feed() takes arbitrary chunking.
    Empty chunk = ZLP seen. Bad frames resync byte-by-byte on the magic."""

    def __init__(self, test_id=None, max_frame=1 << 23):
        self.test_id = test_id
        self.max_frame = max_frame
        self.buf = bytearray()
        self.report = Report()
        self._next_seq = None

    def feed(self, chunk):
        if len(chunk) == 0:
            self.report.zlp += 1
            return
        self.buf.extend(chunk)
        while True:
            i = self.buf.find(MAGIC)
            if i < 0:
                keep = 3  # a partial magic may straddle chunks
                drop = max(0, len(self.buf) - keep)
                self._lose(drop)
                return
            if i:
                self._lose(i)
            if len(self.buf) < HDR:
                return
            test_id, pattern, flags, seed, seq, total = struct.unpack_from("<HBBIII", self.buf, 4)
            if total < MIN_FRAME or total > self.max_frame or pattern > P_LAST:
                self._lose(1)
                continue
            if len(self.buf) < total:
                return
            frame = bytes(self.buf[:total])
            del self.buf[:total]
            self._check(frame, test_id, pattern, seed, seq, total)

    def _lose(self, n):
        if n:
            self.report.resync_bytes += n
            self.report.bad_frames += 1
            del self.buf[:n]

    def _check(self, frame, test_id, pattern, seed, seq, total):
        r = self.report
        if self.test_id is not None and test_id != self.test_id:
            r.bad_frames += 1
            return
        r.frames += 1
        r.bytes += total
        got = frame[HDR:-4]
        exp = make_payload(pattern, total - MIN_FRAME, seed, seq, test_id)
        crc_ok = bool(frame[7] & FLAG_NOCRC) or \
            zlib.crc32(frame[:-4]) & MASK == struct.unpack_from("<I", frame, total - 4)[0]
        mm = first_mismatch(got, exp, pattern, seed, seq, test_id)
        if not crc_ok:
            r.crc_bad += 1
        if not crc_ok or mm:
            r.bad_frames += 1
            if r.first_mismatch is None:
                r.first_mismatch = mm or Mismatch(seq, -1, b"", b"", "crc only (payload equal)")
        if self._next_seq is not None:
            if seq > self._next_seq:
                r.seq_gaps += 1
            elif seq < self._next_seq:
                r.seq_dups += 1
        self._next_seq = (seq + 1) & MASK


class SinkModel:
    """What the app's sink mode must report for a given chunk sequence (mirror of
    bench_modes.dart: headerless chunks < 24 B that are not AOAT fragments are counted as
    `short`, everything else goes to the Checker). Used by the fuzz suite as the oracle."""

    def __init__(self, test_id=None):
        self.checker = Checker(test_id)
        self.short = 0
        self.short_bytes = 0

    def feed(self, chunk):
        if chunk and len(chunk) < MIN_FRAME and not chunk.startswith(MAGIC) and not self.checker.buf:
            self.short += 1
            self.short_bytes += len(chunk)
        else:
            self.checker.feed(chunk)

    def report(self):
        r = self.checker.report
        d = r.as_dict()
        d["short"] = self.short
        d["bytes"] = r.bytes + self.short_bytes
        return d


# ---- DUML generator (changeable addresses, fake data) ------------------------------

def duml_frame(sender=10, receiver=2, cmd_set=0x02, cmd_id=0x10, seq=1, payload_len=16,
               seed=0, ack=2, bad_hdr_crc=False, bad_crc=False, test_id=0):
    """DUML v1 request with a fake address-pattern payload. Bad variants flip one CRC."""
    from duml_proto import build_frame as duml_build
    payload = make_payload(P_ADDR, payload_len, seed, seq, test_id)
    f = bytearray(duml_build(sender, receiver, seq, ack, cmd_set, cmd_id, payload))
    if bad_hdr_crc:
        f[3] ^= 0xFF
    if bad_crc:
        f[-1] ^= 0xFF
    return bytes(f)


def duml_envelope(frame, channel=0x5749):
    """AOA envelope as aoa_mux.py parses it: 55 cc, channel u16, length u32."""
    return b"\x55\xcc" + struct.pack("<HI", channel, len(frame)) + frame


# ---- catalog ------------------------------------------------------------------------

THROUGHPUT_WINDOW_S = 2.0   # bytes/s per window; see bench_host.py for the reason
THROUGHPUT_SIZES = (64, 512, 4096, 16384, 65536)


def fuzz_plan(seed, steps=200, max_size=70000):
    """Replayable fuzz: same seed -> same plan. Each step is a dict the runner executes:
    kind frame|truncated|oversized|duml_bad_crc|duml_bad_hdr|zlp, size, pattern, gap_ms."""
    rng = random.Random(seed)
    plan = []
    for seq in range(steps):
        kind = rng.choices(
            ["frame", "truncated", "oversized", "duml_bad_crc", "duml_bad_hdr", "zlp"],
            weights=[70, 8, 4, 8, 6, 4])[0]
        size = max(MIN_FRAME, int(rng.choice([rng.randint(24, 600), rng.randint(24, max_size),
                                              rng.choice(SIZES + zlp_sizes())])))
        plan.append({"seq": seq, "kind": kind, "size": size,
                     "pattern": rng.randrange(P_ALT + 1), "gap_ms": rng.choice([0, 0, 0, 1, 5, 20]),
                     "cut": rng.randint(1, max(1, size - 1))})
    return plan


def fuzz_wire(step, seed, test_id):
    """Bytes for one fuzz step, and whether a correct receiver must count it good."""
    k, seq = step["kind"], step["seq"]
    if k == "frame":
        return build_frame(step["size"], step["pattern"], seed, seq, test_id), True
    if k == "truncated":
        return build_frame(step["size"], step["pattern"], seed, seq, test_id)[:step["cut"]], False
    if k == "oversized":
        f = bytearray(build_frame(step["size"], step["pattern"], seed, seq, test_id))
        struct.pack_into("<I", f, 16, 0x7FFFFFFF)
        return bytes(f), False
    if k in ("duml_bad_crc", "duml_bad_hdr"):
        return duml_envelope(duml_frame(seq=seq, seed=seed, bad_crc=k == "duml_bad_crc",
                                        bad_hdr_crc=k == "duml_bad_hdr")), False
    return b"", False  # zlp


def golden_vectors():
    """Cross-language vectors; written to aoat_vectors.json, read by the Dart tests."""
    out = []
    for pat in range(P_LAST + 1):
        for n in (24, 25, 37, 64):
            f = build_frame(n, pat, 0xC0FFEE, 7, 5)
            out.append({"pattern": pat, "total": n, "seed": 0xC0FFEE, "seq": 7, "test": 5,
                        "hex": f.hex()})
    return out
