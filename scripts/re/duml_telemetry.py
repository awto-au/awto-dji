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

from duml_catalog import CATALOG
from duml_proto import DeviceType

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
    if len(b) < 7:
        return None
    pitch, roll, yaw = struct.unpack_from("<hhh", b, 0)
    status = b[6]
    return {
        "pitch": pitch / 10, "roll": roll / 10, "yaw": yaw / 10,
        "err": status & 1,
        "mode": GIMBAL_MODE_NAMES.get(status >> 6, status >> 6),
    }


# DataGimbalControl.MODE - byte6>>6 of GetPushParams, also GimbalControl's mode_byte>>6.
GIMBAL_MODE_NAMES = {0: "YawNoFollow", 1: "FPV", 2: "YawFollow"}

PUSH_DECODERS = {
    "gimbal": (0x04, 0x05, _gimbal_push),  # GIMBAL/0x05 GetPushParams, DataGimbalGetPushParams.java
}

# (cmdset, cmdid) -> name, first CATALOG entry wins on duplicates (e.g. AngleControl/SetAngle).
NAME_BY_ID = {}
for _name, (_cset, _cid, _csetname) in CATALOG.items():
    NAME_BY_ID.setdefault((_cset, _cid), f"{_csetname}/{_name}")

DEVICE_NAMES = {v: k for k, v in vars(DeviceType).items() if not k.startswith("_")}


def format_frame(sender, receiver, cset, cid, payload):
    """One human-readable line for a parsed frame - names instead of raw hex where known."""
    src = DEVICE_NAMES.get(sender, hex(sender))
    dst = DEVICE_NAMES.get(receiver, hex(receiver))
    name = NAME_BY_ID.get((cset, cid), f"0x{cset:02x}/0x{cid:02x}")
    decoder = PUSH_DECODERS.get("gimbal") if (cset, cid) == (0x04, 0x05) else None
    if decoder:
        decoded = decoder[2](payload)
        if decoded:
            fields = " ".join(f"{k}={v}" for k, v in decoded.items())
            return f"{src}->{dst} {name} {fields}"
    return f"{src}->{dst} {name} payload={payload.hex()}"


def tail_frames(log_path, seconds, start_offset=None):
    """Yield (sender, receiver, cset, cid, payload) tuples for new lines, for `seconds`.
    Generic version of tail_pushes - every frame, not filtered to one decoder."""
    f = open(log_path)
    f.seek(0, os.SEEK_END) if start_offset is None else f.seek(start_offset)
    end = time.time() + seconds
    while time.time() < end:
        line = f.readline()
        if not line:
            time.sleep(0.1)
            continue
        parsed = parse_line(line)
        if parsed:
            yield parsed
    f.close()


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
