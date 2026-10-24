"""Shared relay-frames-log parsing + named-field push decoders. One parser, reused by
every "send a command, confirm it from telemetry" script - the bug this replaces
(gimbal_verify.py's hand-rolled regex silently breaking when the log format gained a
`protection=` field) is exactly the kind of duplication this exists to stop.

Log line shape (aoa_relay_server.py's logframe, e.g. captures/sessions/<date>/
aoa_relay_frames.log): "<ts> sender=0x.. receiver=0x.. seq=N type=0x.. set=0x.. id=0x..
[protection=N] payload=<hex>" - the protection field is optional, added after this
parser was first written; matched as optional here so a future added field doesn't
silently break it again (add a test to test_duml_telemetry.py for any new field).
"""
import os
import re
import struct
import time

LINE_RE = re.compile(
    r"sender=(0x[0-9a-f]+) receiver=(0x[0-9a-f]+) seq=\d+ type=0x[0-9a-f]+ "
    r"set=(0x[0-9a-f]+) id=(0x[0-9a-f]+)(?:\s+\w+=\S+)*\s+payload=([0-9a-f]*)"
)


def parse_line(line):
    """-> (sender, receiver, cmdset, cmdid, payload_bytes) ints/bytes, or None."""
    m = LINE_RE.search(line)
    if not m:
        return None
    sender, receiver, cset, cid, payload = m.groups()
    return int(sender, 16), int(receiver, 16), int(cset, 16), int(cid, 16), bytes.fromhex(payload)


# name -> (cmdset, cmdid, decode(payload_bytes) -> dict)
def _gimbal_push(b):
    if len(b) < 6:
        return None
    pitch, roll, yaw = struct.unpack_from("<hhh", b, 0)
    return {"pitch": pitch / 10, "roll": roll / 10, "yaw": yaw / 10}


PUSH_DECODERS = {
    "gimbal": (0x04, 0x05, _gimbal_push),  # GIMBAL/0x05 GetPushParams, DataGimbalGetPushParams.java
}


def tail_pushes(log_path, decoder_name, seconds, start_offset=None):
    """Yield decoded dicts from new matching push lines for `seconds`. 0.1s poll: these
    pushes arrive every tens of ms (observed live), so this keeps up without
    busy-spinning; it's a log-file tail, not a hardware-facing timeout."""
    cset, cid, decode = PUSH_DECODERS[decoder_name]
    f = open(log_path)
    f.seek(0, os.SEEK_END) if start_offset is None else f.seek(start_offset)
    end = time.time() + seconds
    while time.time() < end:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        parsed = parse_line(line)
        if parsed is None:
            continue
        _sender, _receiver, c, i, payload = parsed
        if c == cset and i == cid:
            d = decode(payload)
            if d:
                yield d
    f.close()
