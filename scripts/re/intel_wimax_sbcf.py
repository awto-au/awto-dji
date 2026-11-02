#!/usr/bin/env python3
"""Parse an Intel i2400m/i6050 SBCF boot image (format: Linux i2400m fw.c / i2400m.h, v5.10).
Static only. Prints BCF header, boot-command records, merged load segments, jump target,
checksum verification. With --out DIR writes one flat file per load segment (to ./tmp/, never committed)
and a segments.tsv. Log: ./tmp/logs/intel_wimax_sbcf.log
Usage: intel_wimax_sbcf.py <image.sbcf> [--out tmp/intel-wimax]
"""
import argparse, struct, sys
from pathlib import Path

OPC = {1: "READ", 2: "WRITE", 3: "JUMP", 8: "SIGNED_JUMP", 9: "HASH_PAYLOAD_ONLY"}
BCF_FIELDS = ("module_type", "header_len", "header_version", "module_id",
              "module_vendor", "date", "size", "key_size", "modulus_size", "exponent_size")


def parse(b):
    h = dict(zip(BCF_FIELDS, struct.unpack_from("<10I", b)))
    assert h["module_type"] == 6 and h["module_vendor"] == 0x8086
    hl, total = h["header_len"] * 4, h["size"] * 4
    recs, pos, jump = [], hl, None
    while pos + 16 <= total:
        cmd, addr, n, ck = struct.unpack_from("<4I", b, pos)
        assert cmd >> 16 == 0xCBBC, hex(pos)
        op = cmd & 15
        if op in (3, 8):
            jump = dict(off=pos, op=OPC[op], addr=addr, size=n, cmd=cmd)
            break
        data = b[pos + 16:pos + 16 + n]
        ok = None
        if cmd & 0x100:  # USE_CHECKSUM: sum(payload dwords)+cmd+addr+size
            s = sum(struct.unpack("<%dI" % (n // 4), data)) + cmd + addr + n
            ok = (s & 0xFFFFFFFF) == ck
        recs.append(dict(off=pos, cmd=cmd, addr=addr, size=n, ck=ck, ck_ok=ok, data=data))
        pos = (pos + 16 + n + 3) & ~3
    return h, recs, jump, pos


def merge(recs):
    """Merge consecutive WRITEs to contiguous addresses into load segments (boot order kept)."""
    segs = []
    for r in recs:
        if segs and segs[-1]["addr"] + len(segs[-1]["data"]) == r["addr"]:
            segs[-1]["data"] += r["data"]
            segs[-1]["nrec"] += 1
        else:
            segs.append(dict(addr=r["addr"], data=bytearray(r["data"]), nrec=1, off=r["off"] + 16))
    return segs


def final_regions(recs):
    """Apply WRITEs in boot order (later wins); return sorted contiguous regions [(addr, bytearray)].
    Overlays (e.g. 0x850000 loaded twice) collapse to the last write; stale tails of the earlier one remain."""
    mem = {}
    for r in recs:
        for i in range(0, r["size"], 4):
            mem[r["addr"] + i] = r["data"][i:i + 4]
    regs = []
    for a in sorted(mem):
        if regs and regs[-1][0] + len(regs[-1][1]) == a:
            regs[-1][1] += mem[a]
        else:
            regs.append([a, bytearray(mem[a])])
    return regs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("image")
    ap.add_argument("--out")
    a = ap.parse_args()
    b = Path(a.image).read_bytes()
    h, recs, jump, end = parse(b)
    print("BCF header:", {k: hex(v) for k, v in h.items()})
    print("file bytes %d, primary bytes %d, records %d, bad checksums %d, unchecked %d" % (
        len(b), h["size"] * 4, len(recs), sum(r["ck_ok"] is False for r in recs),
        sum(r["ck_ok"] is None for r in recs)))
    segs = merge(recs)
    print("idx  load_addr  end_addr   size     recs  file_off")
    for i, s in enumerate(segs):
        print("%2d   0x%06x   0x%06x   0x%06x %4d  0x%x" % (
            i, s["addr"], s["addr"] + len(s["data"]), len(s["data"]), s["nrec"], s["off"]))
    print("final:", {k: (hex(v) if isinstance(v, int) else v) for k, v in jump.items()})
    print("trailing bytes after primary:", len(b) - h["size"] * 4)
    if a.out:
        o = Path(a.out)
        o.mkdir(parents=True, exist_ok=True)
        with open(o / "segments.tsv", "w") as f:
            f.write("idx\tfile\taddr\tsize\n")
            for i, s in enumerate(segs):
                n = "seg%02d_%06x.bin" % (i, s["addr"])
                (o / n).write_bytes(bytes(s["data"]))
                f.write("%d\t%s\t0x%x\t0x%x\n" % (i, n, s["addr"], len(s["data"])))
        print("wrote", len(segs), "segments to", o)
        regs = final_regions(recs)
        with open(o / "regions.tsv", "w") as f:
            f.write("file\taddr\tsize\n")
            for a_, d_ in regs:
                n = "reg_%06x.bin" % a_
                (o / n).write_bytes(bytes(d_))
                f.write("%s\t0x%x\t0x%x\n" % (n, a_, len(d_)))
        print("final-memory regions:", ", ".join("0x%x+0x%x" % (a_, len(d_)) for a_, d_ in regs))


if __name__ == "__main__":
    main()
