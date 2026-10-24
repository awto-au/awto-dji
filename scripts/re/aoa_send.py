#!/usr/bin/env python3
"""Send a raw DUML command through the AOA proxy, from the PC, no app UI involved.

The app (app/awto_dji_app) just pumps bytes between the RC's USB accessory port and a
TCP socket on this machine (aoa_relay_server.py). This script builds one DUML frame and
writes it to that server's command FIFO (tmp/aoa_send.fifo), which forwards it straight
to the phone's accessory `write()` - from there to the RC exactly like any other DUML
frame. aoa_relay_server.py must already be running and the app already connected.

For a specific subsystem, prefer its own CLI (e.g. gimbal.py) over hand-building a frame
here - this is the low-level fallback when no such CLI exists yet.

Usage:
  python3 -I scripts/re/aoa_send.py --set 0x04 --id 0x0a --receiver 0x04 \\
      --payload 5000000000000005
  python3 -I scripts/re/aoa_send.py --set 0x02 --id 0xb3 --receiver 0x01   # RequestIFrame

Device type ids (sender/receiver): pc=10 app=2 camera=1 flightController=3 gimbal=4
centerBoard=5 remoteController=6.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_proto import build_frame, send_via_proxy  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", required=True, help="cmd set, e.g. 0x04")
    ap.add_argument("--id", required=True, help="cmd id, e.g. 0x0a")
    ap.add_argument("--receiver", default="0x03", help="receiver device type (default 0x03 FC)")
    ap.add_argument("--sender", default="0x0a", help="sender device type (default 0x0a PC)")
    ap.add_argument("--seq", type=lambda s: int(s, 0), default=0x7200)
    ap.add_argument("--ack", type=int, default=2, choices=[0, 1, 2],
                     help="0=none 1=beforeExec 2=afterExec (default 2)")
    ap.add_argument("--payload", default="", help="hex payload bytes, e.g. 5000000000000005")
    args = ap.parse_args()

    frame = build_frame(
        sender=int(args.sender, 0),
        receiver=int(args.receiver, 0),
        seq=args.seq,
        ack_type=args.ack,
        cmd_set=int(args.set, 0),
        cmd_id=int(args.id, 0),
        payload=bytes.fromhex(args.payload),
    )

    print(f"sending: {frame.hex()}")
    send_via_proxy(frame)
    print("sent (see tmp/logs/aoa_relay_server.log for the TX line and any reply)")


if __name__ == "__main__":
    main()
