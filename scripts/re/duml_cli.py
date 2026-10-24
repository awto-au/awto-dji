#!/usr/bin/env python3
"""Generic DUML command CLI over the AOA proxy - send by name, no raw bytes needed.

Two sources, merged:
  - duml_commands.py REGISTRY: commands with a reverse-engineered real payload struct
    (field names, e.g. `gimbal.angle --pitch 12 --yaw -10`).
  - duml_catalog.py CATALOG (generated from the APK, 723 names): everything else, by
    cmdset/cmdid only - payload unknown, so only usable empty or with explicit --payload
    (this covers every Get* query, which is empty-payload and safe by convention, see
    docs/apk-vs-dissector-gap-report-2026-10-23.md).

aoa_relay_server.py must already be running and the app already connected as accessory.

Usage:
  python3 -I scripts/re/duml_cli.py list [pattern]
  python3 -I scripts/re/duml_cli.py send GetVersion
  python3 -I scripts/re/duml_cli.py send gimbal.angle --pitch 12 --yaw -10
  python3 -I scripts/re/duml_cli.py send SomeSetCommand --payload 0102 --receiver 0x03
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_catalog import CATALOG  # noqa: E402
from duml_commands import REGISTRY  # noqa: E402
from duml_proto import DeviceType, build_frame, send_via_proxy  # noqa: E402

# cmdset -> best-guess default receiver, for CATALOG-only (unstructured) commands.
# Always overridable with --receiver; these are a convenience, not verified per-command.
CMDSET_DEFAULT_RECEIVER = {
    0x00: DeviceType.flight_controller,  # GENERAL/COMMON
    0x01: DeviceType.flight_controller,  # SPECIAL
    0x02: DeviceType.camera,
    0x03: DeviceType.flight_controller,  # FLYC
    0x04: DeviceType.gimbal,
    0x06: DeviceType.remote_controller,
    0x09: DeviceType.remote_controller,  # HDLINK/OSD - matches earlier verified sends
}


def cmd_list(args):
    pat = (args.pattern or "").lower()
    print("-- structured (duml_commands.py REGISTRY) --")
    for name, (cset, cid, _s, _r, struct, _scale, _defaults) in sorted(REGISTRY.items()):
        if pat in name.lower():
            fields = ", ".join(f[0] for f in struct._fields_)
            print(f"  {name:30s} set={cset:#04x} id={cid:#04x}  fields: {fields}")
    print("-- catalog only (payload unknown, --payload required unless empty) --")
    for name, (cset, cid, cset_name) in sorted(CATALOG.items()):
        if pat in name.lower():
            print(f"  {name:40s} set={cset:#04x} id={cid:#04x}  ({cset_name})")


def cmd_send(args):
    name = args.name
    if name in REGISTRY:
        cset, cid, sender, receiver, struct_cls, scale, defaults = REGISTRY[name]
        inst = struct_cls()
        for fname, _ctype in struct_cls._fields_:
            raw = getattr(args, fname, None)
            if raw is not None:
                setattr(inst, fname, round(raw * scale.get(fname, 1)))
            elif fname in defaults:
                setattr(inst, fname, defaults[fname])
        payload = bytes(inst)
        if args.sender is not None:
            sender = int(args.sender, 0)
        if args.receiver is not None:
            receiver = int(args.receiver, 0)
    elif name in CATALOG:
        cset, cid, cset_name = CATALOG[name]
        payload = bytes.fromhex(args.payload) if args.payload else b""
        sender = int(args.sender, 0) if args.sender is not None else DeviceType.pc
        receiver = (int(args.receiver, 0) if args.receiver is not None
                    else CMDSET_DEFAULT_RECEIVER.get(cset, DeviceType.flight_controller))
    else:
        raise SystemExit(f"unknown command {name!r} - try `duml_cli.py list {name}`")

    frame = build_frame(sender=sender, receiver=receiver, seq=args.seq, ack_type=args.ack,
                         cmd_set=cset, cmd_id=cid, payload=payload)
    print(f"{name}: set={cset:#04x} id={cid:#04x} sender={sender:#04x} "
          f"receiver={receiver:#04x} payload={payload.hex()} -> {frame.hex()}")
    send_via_proxy(frame)
    print("sent (see tmp/logs/aoa_relay_server.log for the TX line and any reply)")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    lst = sub.add_parser("list", help="search known command names")
    lst.add_argument("pattern", nargs="?", default="")
    lst.set_defaults(func=cmd_list)

    snd = sub.add_parser("send", help="send a command by name")
    snd.add_argument("name")
    snd.add_argument("--payload", default=None, help="hex payload (CATALOG-only commands)")
    snd.add_argument("--sender", default=None, help="override sender device type")
    snd.add_argument("--receiver", default=None, help="override receiver device type")
    snd.add_argument("--seq", type=lambda s: int(s, 0), default=0x7400)
    snd.add_argument("--ack", type=int, default=2, choices=[0, 1, 2])
    snd.set_defaults(func=cmd_send)
    # Structured-command fields are unknown ahead of time; accept any --field via a
    # permissive parse pass rather than hardcoding gimbal/camera-specific args here.
    args, extra = ap.parse_known_args()
    i = 0
    while i < len(extra):
        if extra[i].startswith("--"):
            fname = extra[i][2:].replace("-", "_")
            val = float(extra[i + 1])
            setattr(args, fname, val)
            i += 2
        else:
            i += 1

    args.func(args)


if __name__ == "__main__":
    main()
