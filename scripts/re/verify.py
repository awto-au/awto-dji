#!/usr/bin/env python3
"""Generic closed-loop command verification: send a command, confirm the effect from
the device's own telemetry push - not from an ack, not from a human watching.
Supersedes gimbal_verify.py (now deleted): same logic, parameterized by command/push
name instead of hardcoded to the gimbal, built on the shared, tested parser in
duml_telemetry.py instead of a hand-rolled regex.

Sends via duml_cli.py's REGISTRY/CATALOG (same command names as `duml_cli.py list`).
Watches via duml_telemetry.PUSH_DECODERS (currently: "gimbal" -> pitch/roll/yaw).

Usage:
  python3 -I scripts/re/verify.py gimbal.angle --watch gimbal --field pitch --target -10 \\
      --pitch -10 --roll 0 --yaw 0
  python3 -I scripts/re/verify.py gimbal.angle --watch gimbal --field pitch --target 0 \\
      --loop 3 --pitch 0 --roll 0 --yaw 0

Needs: aoa_relay_server.py running, phone connected as AOA accessory to the RC
(docs/phone-bridge-operator-guide.md).
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_catalog import CATALOG  # noqa: E402
from duml_cli import CMDSET_DEFAULT_RECEIVER  # noqa: E402
from duml_commands import REGISTRY  # noqa: E402
from duml_proto import DeviceType, build_frame, send_via_proxy, session_log_dir  # noqa: E402
from duml_telemetry import PUSH_DECODERS, tail_frames, tail_pushes  # noqa: E402

# DataRcRequestGimbalCtrPermission.java's RcGimbalError enum - the real app's own
# decode of this reply, which this tool never checked before (found 2026-10-24: zero
# reply frames for RC/0x22 in the whole session's capture - permission may simply
# never have been granted, silently, the entire time).
GIMBAL_PERMISSION_REPLY = {0: "GRANTED", 1: "Refused", 2: "TimeOut", 3: "Getted(held by other)"}


def wait_for_permission_reply(log_path, offset, seconds):
    """-> (status_int_or_None, label). None = no reply frame arrived at all."""
    for sender, receiver, cset, cid, payload in tail_frames(log_path, seconds,
                                                              start_offset=offset):
        if cset == 0x06 and cid == 0x22 and payload:
            status = payload[0]
            return status, GIMBAL_PERMISSION_REPLY.get(status, f"unknown({status})")
    return None, "NO REPLY"


def send(name, seq, sender_override=None, receiver_override=None, payload_hex=None,
         **field_overrides):
    if name in REGISTRY:
        cset, cid, sender, receiver, struct_cls, scale, defaults = REGISTRY[name]
        inst = struct_cls()
        for fname, _ctype in struct_cls._fields_:
            if fname in field_overrides:
                setattr(inst, fname, round(field_overrides[fname] * scale.get(fname, 1)))
            elif fname in defaults:
                setattr(inst, fname, defaults[fname])
        payload = bytes(inst)
    elif name in CATALOG:
        cset, cid, _cset_name = CATALOG[name]
        sender, payload = DeviceType.pc, (bytes.fromhex(payload_hex) if payload_hex else b"")
        receiver = CMDSET_DEFAULT_RECEIVER.get(cset, DeviceType.flight_controller)
    else:
        raise SystemExit(f"unknown command {name!r} - try `duml_cli.py list {name}`")
    if sender_override is not None:
        sender = sender_override
    if receiver_override is not None:
        receiver = receiver_override
    frame = build_frame(sender=sender, receiver=receiver, seq=seq, ack_type=2,
                         cmd_set=cset, cmd_id=cid, payload=payload)
    send_via_proxy(frame)
    return frame


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", help="name from `duml_cli.py list`, e.g. gimbal.angle")
    ap.add_argument("--watch", required=True, choices=sorted(PUSH_DECODERS),
                     help="which push decoder confirms the effect")
    ap.add_argument("--field", required=True, help="field name within the decoded push dict")
    ap.add_argument("--target", type=float, required=True)
    ap.add_argument("--tol", type=float, default=2.0)
    ap.add_argument("--settle", type=float, default=2.0)
    ap.add_argument("--baseline", type=float, default=1.0)
    ap.add_argument("--loop", type=int, default=1)
    ap.add_argument("--seq", type=lambda s: int(s, 0), default=0x6c00)
    # Any extra --field value becomes a REGISTRY struct field override (e.g. --pitch -10),
    # same permissive pass duml_cli.py uses - structured commands' fields aren't known ahead.
    args, extra = ap.parse_known_args()
    overrides = {}
    i = 0
    while i < len(extra):
        if extra[i].startswith("--"):
            overrides[extra[i][2:].replace("-", "_")] = float(extra[i + 1])
            i += 2
        else:
            i += 1

    log_path = os.path.join(session_log_dir(), "aoa_relay_frames.log")
    if not os.path.exists(log_path):
        raise SystemExit(f"{log_path} doesn't exist yet - is the relay running and the "
                          "phone connected? (docs/phone-bridge-operator-guide.md)")
    verify_log = os.path.join(session_log_dir(), "verify.log")
    vf = open(verify_log, "a", buffering=1)

    def tee(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        vf.write(line + "\n")

    tee(f"=== verify {args.command} watch={args.watch}.{args.field}->{args.target} "
        f"x{args.loop} overrides={overrides} ===")
    offset = os.path.getsize(log_path)
    confirmed = 0
    for i in range(args.loop):
        baseline = list(tail_pushes(log_path, args.watch, args.baseline, start_offset=offset))
        offset = os.path.getsize(log_path)
        if not baseline:
            tee(f"[{i}] no {args.watch!r} pushes in {args.baseline}s baseline - "
                "link not live? stopping.")
            break
        before = baseline[-1][args.field]
        tee(f"[{i}] baseline {args.field}={before} ({len(baseline)} pushes)")

        if "gimbal" in args.command:  # gimbal ignores angle commands without this first
            send("gimbal.requestCtrPermission", args.seq + i * 2)
            perm_offset = os.path.getsize(log_path)
            # DataRcRequestGimbalCtrPermission.java waits up to 10s; 2s here because on
            # this link any reply at all arrives near-instantly - raise if real replies
            # turn out to need longer and get missed.
            status, label = wait_for_permission_reply(log_path, perm_offset, 2.0)
            offset = os.path.getsize(log_path)
            tee(f"[{i}] gimbal.requestCtrPermission reply: {label} "
                f"(status={status}) - {'proceeding' if status == 0 else 'PROCEEDING ANYWAY, not granted'}")
        frame = send(args.command, args.seq + i * 2 + 1, **overrides)
        tee(f"[{i}] sent {args.command} {overrides} -> {frame.hex()}")

        samples = list(tail_pushes(log_path, args.watch, args.settle, start_offset=offset))
        offset = os.path.getsize(log_path)
        if not samples:
            tee(f"[{i}] no pushes in {args.settle}s after send - link may have dropped")
            continue
        after = samples[-1][args.field]
        err = abs(after - args.target)
        reached = err <= args.tol
        tee(f"[{i}] after {args.field}={after} (was {before}) err={err:.2f} "
            f"{'REACHED' if reached else 'NOT REACHED'} ({len(samples)} pushes)")
        if reached:
            confirmed += 1

    tee(f"=== {confirmed}/{args.loop} confirmed by telemetry (not just sent) ===")
    print(f"log: {verify_log}")


if __name__ == "__main__":
    main()
