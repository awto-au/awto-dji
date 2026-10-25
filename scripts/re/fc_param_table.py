#!/usr/bin/env python3
"""Extract the DJI FC (m0306) parameter table with min/max/default.

Entry = FlycExportParam2015 (60B): nameptr, valptr, valsize, type_id, limits(36B),
attribute, callback (layout from o-gs/dji-firmware-tools dji_flyc_param_ed.py). The 36-byte
limit block is THREE parallel {min,max,default} views of the same logical limit, so the code
can read whichever matches the field's storage type:
    +0x10  float32  min,max,default
    +0x1c  int32    min,max,default
    +0x28  uint32   min,max,default
We pick the view by type (fractional/float -> float view; negative -> signed int; else uint).

Run on the DECRYPTED m0306 (scripts/re/xv4_decrypt.py).
Usage: python3 scripts/re/fc_param_table.py m0306_dec.bin [--defaults]
  (no flag) -> addr/name/type/size (original columns)
  --defaults -> addr/name/type/size/min/max/default
"""
import sys, struct

d = open(sys.argv[1], "rb").read()
WANT_DEF = "--defaults" in sys.argv[2:]
B = 0x08020000; E = B + len(d); sz = 60


def cstr(va):
    o = va - B
    if not (0 <= o < len(d)):
        return None
    e = d.find(b"\0", o); s = d[o:e]
    return s.decode() if 2 < len(s) < 80 and all(32 <= c < 127 for c in s) else None


def ident(nm):
    # real param names are identifiers (allow . [ ] space inside brackets); reject format strings
    if "%" in nm or nm[0] in "[(" or "  " in nm:
        return False
    return all(c.isalnum() or c in "_.[] " for c in nm)


inram = lambda v: 0x20000000 <= v < 0x20030000 or 0x10000000 <= v < 0x10010000
GOODSZ = {1, 2, 4, 8, 12, 16, 24, 32, 48, 64}


def pick(lim, tid):
    f = struct.unpack_from("<fff", lim, 0x00)
    iv = struct.unpack_from("<iii", lim, 0x0c)
    uv = struct.unpack_from("<III", lim, 0x18)
    def frac(x):
        return x == x and abs(x) < 1e15 and x != int(x)
    # float types, or any view with a fractional component -> float view
    if tid in (6, 7) or frac(f[0]) or frac(f[1]) or frac(f[2]):
        return ("f",) + f
    # integer: signedness from type_id (0,1,2=unsigned; 3,4,5=signed); validate min<=def<=max,
    # fall back to the other signedness, then float, so a mislabeled view can't drop a real param.
    order = [("u", uv), ("i", iv)] if tid in (0, 1, 2) else \
            [("i", iv), ("u", uv)] if tid in (3, 4, 5) else [("u", uv), ("i", iv)]
    for k, (mn, mx, df) in order:
        if mn <= df <= mx:
            return k, mn, mx, df
    return ("f",) + f


def fmt(kind, x):
    if kind == "f":
        return ("%.6g" % x)
    return str(int(x))


rows = []
i = 0
while i < len(d) - sz:
    npv, vpv, vsize, tid = struct.unpack_from("<IIII", d, i)
    nm = cstr(npv) if B <= npv < E else None
    if nm and ident(nm) and inram(vpv) and tid < 16 and vsize in GOODSZ:
        lim = d[i + 0x10:i + 0x34]
        kind, mn, mx, df = pick(lim, tid)
        # sanity: min <= default <= max in the chosen view -> rejects format-string junk
        ok = (mn <= df <= mx) if kind != "u" else (mn <= df <= mx)
        if ok:
            rows.append((vpv, nm, tid, vsize, kind, mn, mx, df))
            i += sz; continue
    i += 4

if WANT_DEF:
    print("addr\tname\ttype_id\tsize\tmin\tmax\tdefault")
    for a, nm, tid, s, k, mn, mx, df in rows:
        print("%#010x\t%s\t%d\t%d\t%s\t%s\t%s" % (a, nm, tid, s, fmt(k, mn), fmt(k, mx), fmt(k, df)))
else:
    print("addr\tname\ttype_id\tsize")
    for a, nm, tid, s, k, mn, mx, df in rows:
        print("%#010x\t%s\t%d\t%d" % (a, nm, tid, s))
