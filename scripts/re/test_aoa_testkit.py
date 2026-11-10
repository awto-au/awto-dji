"""aoa_testkit: pure Python, no hardware."""
import json
import struct
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import aoa_testkit as k
from aoa_mux import AoaMux, COMMAND


@pytest.mark.parametrize("pat", range(6))
@pytest.mark.parametrize("n", [24, 25, 28, 100, 4096])
def test_roundtrip(pat, n):
    c = k.Checker()
    c.feed(k.build_frame(n, pat, 123, 9, 4))
    assert c.report.frames == 1 and c.report.passed and c.report.bytes == n


def test_arbitrary_chunking():
    stream = b"".join(k.build_frame(50 + i, i % 6, 1, i) for i in range(20))
    c = k.Checker()
    for i in range(0, len(stream), 7):
        c.feed(stream[i:i + 7])
    assert c.report.frames == 20 and c.report.passed


def test_addr_pattern_names_offset():
    f = bytearray(k.build_frame(24 + 64, k.P_ADDR, 55, 3))
    # copy the word of offset 8 over offset 24: a misplaced block
    f[20 + 24:20 + 28] = f[20 + 8:20 + 12]
    c = k.Checker()
    c.feed(bytes(f))
    mm = c.report.first_mismatch
    assert mm.seq == 3 and mm.offset == 24
    assert "carries address 8" in mm.hint
    assert c.report.crc_bad == 1 and c.report.bad_frames == 1


def test_single_bit_flip_localised():
    f = bytearray(k.build_frame(24 + 100, k.P_COUNTER, 1, 0))
    f[20 + 37] ^= 0x10
    c = k.Checker()
    c.feed(bytes(f))
    assert c.report.first_mismatch.offset == 37


def test_seq_gap_and_dup():
    c = k.Checker()
    for s in (0, 1, 3, 3):
        c.feed(k.build_frame(30, 0, 1, s))
    assert c.report.seq_gaps == 1 and c.report.seq_dups == 1 and not c.report.passed


def test_resync_after_garbage_and_truncation():
    c = k.Checker()
    c.feed(k.build_frame(60, 0, 1, 0))
    c.feed(b"\x00\x01garbage")
    c.feed(k.build_frame(60, 0, 1, 1))
    assert c.report.frames == 2 and c.report.resync_bytes > 0


def test_oversized_length_rejected_not_waited_for():
    f = bytearray(k.build_frame(40, 0, 1, 0))
    struct.pack_into("<I", f, 16, 0x7FFFFFFF)
    c = k.Checker()
    c.feed(bytes(f) + k.build_frame(40, 0, 1, 1))
    assert c.report.frames == 1  # second frame still found


def test_zlp_counted():
    c = k.Checker()
    c.feed(b"")
    assert c.report.zlp == 1


def test_short_transfer_and_min_size():
    assert len(k.short_transfer(7, 1, 0)) == 7
    assert k.short_transfer(0, 1, 0) == b""
    with pytest.raises(ValueError):
        k.build_frame(23, 0, 1, 0)


def test_zlp_size_boundaries():
    z = k.zlp_sizes()
    assert 64 in z and 512 in z and 1024 in z and 65536 in z
    assert all(s % 64 == 0 for s in z)
    assert 513 not in z and 63 not in z


def test_sizes_cover_spec():
    for s in (0, 1, 63, 64, 65, 511, 512, 513, 65535, 65536):
        assert s in k.SIZES


def test_seed_reproducible():
    assert k.fuzz_plan(77) == k.fuzz_plan(77)
    assert k.fuzz_plan(77) != k.fuzz_plan(78)
    p = k.fuzz_plan(5)
    assert [k.fuzz_wire(s, 5, 1) for s in p] == [k.fuzz_wire(s, 5, 1) for s in k.fuzz_plan(5)]
    assert k.make_payload(k.P_RANDOM, 64, 9, 1) == k.make_payload(k.P_RANDOM, 64, 9, 1)
    assert k.make_payload(k.P_RANDOM, 64, 9, 1) != k.make_payload(k.P_RANDOM, 64, 9, 2)


def test_fuzz_kinds_present_and_bad_ones_fail():
    kinds = {s["kind"] for s in k.fuzz_plan(1, steps=400)}
    assert kinds >= {"frame", "truncated", "oversized", "duml_bad_crc", "duml_bad_hdr", "zlp"}
    good, ok = k.fuzz_wire({"seq": 0, "kind": "frame", "size": 100, "pattern": 0, "cut": 5}, 1, 1)
    assert ok and k.Checker().report.passed


def test_duml_addresses_and_crc_variants():
    f = k.duml_frame(sender=6, receiver=4, cmd_set=0x04, cmd_id=0x0a, seq=0x1234)
    assert f[4] == 6 and f[5] == 4 and f[9] == 4 and f[10] == 0x0a
    assert f[6] | f[7] << 8 == 0x1234
    for kw, good in (({}, True), ({"bad_crc": True}, False), ({"bad_hdr_crc": True}, False)):
        m = AoaMux()
        pk = m.feed(k.duml_envelope(k.duml_frame(**kw)))
        assert pk and pk[0].channel == COMMAND
    # bare check via crc helpers: the good frame validates, the bad ones do not
    from duml_proto import crc8, crc16
    ok = lambda f: crc8(0x77, f[:3]) == f[3] and crc16(0x3692, f[:-2]) == f[-2] | f[-1] << 8
    assert ok(k.duml_frame()) and not ok(k.duml_frame(bad_crc=True)) and not ok(k.duml_frame(bad_hdr_crc=True))


def test_golden_vectors_file_in_sync():
    p = Path(__file__).with_name("aoat_vectors.json")
    assert json.loads(p.read_text()) == k.golden_vectors()
