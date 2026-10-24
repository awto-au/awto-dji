#!/usr/bin/env python3
"""Short gimbal-move CLI: one line instead of hand-building a REGISTRY send each time.

Sends gimbal.requestCtrPermission first (AngleControl is ignored without it - see
docs/apk-vs-dissector-gap-report-2026-10-23.md), then gimbal.angle. Via the AOA proxy
(aoa_relay_server.py must already be running and the app already connected).

Usage: python3 -I scripts/re/gimbal.py <pitch> <roll> <yaw> [--duration ms] [--overtime n]
  python3 -I scripts/re/gimbal.py 12 0 -10
  python3 -I scripts/re/gimbal.py 0 0 0          # recenter
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_commands import REGISTRY  # noqa: E402
from duml_proto import build_frame, send_via_proxy  # noqa: E402


def send(name, seq, **field_overrides):
    cset, cid, sender, receiver, struct_cls, scale, defaults = REGISTRY[name]
    inst = struct_cls()
    for fname, _ctype in struct_cls._fields_:
        if fname in field_overrides:
            setattr(inst, fname, round(field_overrides[fname] * scale.get(fname, 1)))
        elif fname in defaults:
            setattr(inst, fname, defaults[fname])
    frame = build_frame(sender=sender, receiver=receiver, seq=seq, ack_type=2,
                         cmd_set=cset, cmd_id=cid, payload=bytes(inst))
    send_via_proxy(frame)
    return frame


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pitch", type=float)
    ap.add_argument("roll", type=float)
    ap.add_argument("yaw", type=float)
    ap.add_argument("--duration", type=int, default=300, help="ms, APK default 300")
    ap.add_argument("--overtime", type=int, default=0)
    ap.add_argument("--seq", type=lambda s: int(s, 0), default=0x6900)
    args = ap.parse_args()

    seq = args.seq
    send("gimbal.requestCtrPermission", seq)
    seq += 1
    frame = send("gimbal.angle", seq, pitch=args.pitch, roll=args.roll, yaw=args.yaw,
                 duration=args.duration, overtime=args.overtime)
    print(f"pitch={args.pitch} roll={args.roll} yaw={args.yaw} -> {frame.hex()}")
    print("sent (see captures/sessions/<today>/aoa_relay_frames.log for any reply)")


if __name__ == "__main__":
    main()
