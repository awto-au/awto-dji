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
import time

from duml_catalog import CATALOG
from duml_generated import common_version, gimbal_push_params, osd_general, rc_signal_quality, restart_device
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


# DataGimbalControl.MODE - byte6>>6 of GetPushParams, also GimbalControl's mode_byte>>6.
# Not schema-encoded (see docs/schema/duml/commands.yaml 0x04/0x05's `status` field doc):
# one two-bit value used in exactly this one place isn't worth a dedicated field kind.
GIMBAL_MODE_NAMES = {0: "YawNoFollow", 1: "FPV", 2: "YawFollow"}


def _gimbal_push(b):
    d = gimbal_push_params.decode(b)
    if d is None:
        return None
    status = d.pop("status")
    d["err"] = status & 1
    d["mode"] = GIMBAL_MODE_NAMES.get(status >> 6, status >> 6)
    return d


# All pushes below are now schema-generated - see docs/schema/duml/commands.yaml +
# docs/schema/duml/README.md (awto-dji#33). Regenerate with
# `python3 -I scripts/re/gen_duml_schema.py` after editing the schema, never this file.

# name -> (tuple of (cmdset, cmdid) pairs the decoder matches, decode_fn). A tuple of
# pairs (not just one) because some real classes are registered under more than one
# cmdset/cmdid in the vendor app (see docs/schema/duml/osd_general.yaml's `ids`) -
# matching only the first one found silently looked like "this telemetry never
# arrives" for 2026-10-24's whole session until the second id was found.
PUSH_DECODERS = {
    "gimbal": (gimbal_push_params.IDS, _gimbal_push),  # GIMBAL/0x05 GetPushParams
    "osd": (osd_general.IDS, osd_general.decode),  # DataOsdGetPushCommon, both ids - schema-generated
    "rc_signal": (rc_signal_quality.IDS, rc_signal_quality.decode),  # hdLink/0x08 GetPushSignalQuality
    "restart_device": (restart_device.IDS, restart_device.decode),  # COMMON/RestartDevice, schema-generated
    "version": (common_version.IDS, common_version.decode),  # COMMON/GetVersion reply
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
    decoder = next((d for d in PUSH_DECODERS.values() if (cset, cid) in d[0]), None)
    if decoder:
        decoded = decoder[1](payload)
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
    # Pre-existing bug fixed here (not this task's subject, found while wiring in the
    # schema-generated osd decoder): PUSH_DECODERS values are (ids_tuple, decode_fn),
    # not (cset, cid, decode) - this used to raise ValueError on every call. ids_tuple
    # may hold more than one (cset, cid) pair (see PUSH_DECODERS' own comment).
    ids, decode = PUSH_DECODERS[decoder_name]
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
        if (c, i) in ids:
            d = decode(payload)
            if d:
                yield d
    f.close()
