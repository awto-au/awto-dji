#!/usr/bin/env python3.15t
"""Settle awto-dji #101: what constant do the 6 sel<0 B-operand MACs carry?

Runs the pluribus lift's MAC decode on the raw m2001 image (NOT the full gate build) and dumps,
per target MAC tile, the B-operand rows' data_sel + data_inv.
  - Unselected row polarity (pluribus#197, Quartus gxhb_macx_constb_* specimens): inv=0 -> const 1, inv=1 -> const 0.
  - B constant = sum(1<<k for rows with sel<0 and inv==0) -- sparse, NOT all-zero.
  - Earlier "inv=1 -> const 1" polarity was backwards; the all-zero-B conclusion (#89/#101) is superseded.

  python3 -I fpga/m2001/scripts/cycloneiv_clean_mac_settle.py [--image <m2001.bin>]
Read-only w.r.t. the repo; writes only a scratch plane.rbf (removed at exit).
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from _repo import PLURIBUS, DJI  # noqa: E402
sys.path.insert(0, PLURIBUS)
sys.path.insert(0, os.path.join(PLURIBUS, "scripts"))

TARGETS = [(103, 2), (103, 5), (103, 49), (103, 53), (103, 60), (103, 61)]
DEFAULT_IMAGE = os.path.join(DJI, "sources", "dji-fpga-images", "P3X_FW_V01.01.0008", "P3X_FW_V01.01.0008_m2001.bin")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--image", default=DEFAULT_IMAGE)
    a = ap.parse_args()
    from lifters.cycloneiv_clean import emit, mac
    import cycloneiv_decompress as cd
    plane = os.path.join(DJI, "tmp", f"plane_settle.{os.getpid()}.rbf")
    os.makedirs(os.path.dirname(plane), exist_ok=True)
    open(plane, "wb").write(cd.decompress(open(a.image, "rb").read(), {}))
    try:
        cx = emit.Ctx()
        bits = cx.T.plane_bits(plane)
        md = cx.macctl.decode(bits)
        ds, di = md["data_sel"], md["data_inv"]
        print(f"image {os.path.basename(a.image)}: {ds.shape[0]} MAC instances\n")
        for (x, y) in TARGETS:
            i = mac.instance(x, y)
            bsel, binv = ds[i, 18:36], di[i, 18:36]
            ones = [k for k in range(18) if bsel[k] < 0 and binv[k] == 0]
            const = sum(1 << k for k in ones)
            print(f"MAC({x},{y}) i={i}: B sel={bsel.tolist()}")
            print(f"              B inv={binv.tolist()}  const-1 bits={ones}  B const=0x{const:05x}")
        good = [i for i in range(ds.shape[0]) if (ds[i, 18:36] >= 0).any()][:1]
        for i in good:
            cols = mac.columns()
            print(f"\ncontrast GOOD MAC i={i} (x={cols[i // 90]},y={i % 90 + 1}): B sel={ds[i, 18:36].tolist()}")
    finally:
        if os.path.exists(plane):
            os.remove(plane)


if __name__ == "__main__":
    main()
