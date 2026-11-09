#!/usr/bin/env python3.15t
"""Settle awto-dji #101: are the 6 all-zero-B MACs design-zero or a data_inv lift miss?

Runs the pluribus lift's MAC decode on the raw m2001 image (NOT the full gate build) and dumps,
for each target MAC tile, the B-operand rows' data_sel + data_inv. The lift's emit._mac pin()
returns GND for an unselected row (sel<0) and DISCARDS data_inv there — so a const-1 encoded as
"invert an unselected (GND) row" would be silently lost. Verdict:
  - any B row with sel<0 AND inv==1  -> LIFT MISS (fix emit.pin() to return 1'b1 when inv)
  - all unselected B rows have inv==0 -> faithful lift; the 0 is genuine (design/dead logic)

  python3.15t fpga/m2001/scripts/cycloneiv_clean_mac_settle.py [--image <m2001.bin>]
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
        miss = False
        for (x, y) in TARGETS:
            i = mac.instance(x, y)
            bsel, binv = ds[i, 18:36], di[i, 18:36]
            unsel_inv = [(18 + k, int(binv[k])) for k in range(18) if bsel[k] < 0 and binv[k] == 1]
            verdict = "LIFT MISS (unselected B row(s) inverted = const-1 dropped)" if unsel_inv else "faithful (all unselected B rows inv=0 -> genuine 0)"
            miss = miss or bool(unsel_inv)
            print(f"MAC({x},{y}) i={i}: B sel={bsel.tolist()}")
            print(f"              B inv={binv.tolist()}  unselected+inverted rows={unsel_inv}  -> {verdict}")
        # contrast: a MAC whose B operand has real routed inputs (sel>=0)
        good = [i for i in range(ds.shape[0]) if (ds[i, 18:36] >= 0).any()][:1]
        for i in good:
            cols = mac.columns()
            print(f"\ncontrast GOOD MAC i={i} (x={cols[i // 90]},y={i % 90 + 1}): B sel={ds[i, 18:36].tolist()}  (decode resolves real B inputs)")
        print("\nVERDICT:", "LIFT MISS on >=1 target -> fix emit.pin()" if miss else "no lift miss -> the all-zero B ports are genuine design-0")
    finally:
        if os.path.exists(plane):
            os.remove(plane)


if __name__ == "__main__":
    main()
