#!/usr/bin/env python3
"""Gimbal left/right sweep test: yaw +N, 1s pause, yaw -N, repeated - for visually
confirming movement in real time. The 1s pause is an explicit, user-requested real-time
viewing cadence (not a blind wait), via Python's own time.sleep, not a shell sleep.

Sends gimbal.requestCtrPermission once first (see docs/apk-vs-dissector-gap-report -
AngleControl needs this before the gimbal honors it), then the sweep, via the AOA proxy
(aoa_relay_server.py) - no app UI involved.

Usage: python3 -I scripts/re/gimbal_sweep.py [--degrees 15] [--cycles 2] [--pause 1.0]
"""
import argparse
import ctypes as C
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_commands import REGISTRY  # noqa: E402
from duml_proto import build_frame, send_via_proxy, session_log_dir  # noqa: E402


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
    ap.add_argument("--degrees", type=float, default=15.0)
    ap.add_argument("--cycles", type=int, default=2)
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between moves")
    args = ap.parse_args()

    log_path = os.path.join(session_log_dir(), "gimbal_sweep.log")
    logf = open(log_path, "a", buffering=1)

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        logf.write(line + "\n")

    seq = 0x7500
    log("requesting gimbal control permission")
    send("gimbal.requestCtrPermission", seq)
    seq += 1
    time.sleep(args.pause)

    for i in range(args.cycles):
        log(f"cycle {i + 1}/{args.cycles}: yaw +{args.degrees}")
        send("gimbal.angle", seq, pitch=0, roll=0, yaw=args.degrees, overtime=10)
        seq += 1
        time.sleep(args.pause)

        log(f"cycle {i + 1}/{args.cycles}: yaw -{args.degrees}")
        send("gimbal.angle", seq, pitch=0, roll=0, yaw=-args.degrees, overtime=10)
        seq += 1
        time.sleep(args.pause)

    log("recentering: yaw 0")
    send("gimbal.angle", seq, pitch=0, roll=0, yaw=0, overtime=10)
    log("done")


if __name__ == "__main__":
    main()
