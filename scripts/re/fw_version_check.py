#!/usr/bin/env python3
"""Query `GetVersion` (General/0x00/id=0x01) from every board we have a live command
path to, decode the reply, and flag it against a reference "latest known-good" table.
awto-dji#32.

Devices: flight_controller, gimbal, camera, remote_controller, ofdm_radio (the air
radio MCU - DeviceType.ofdm added this session, see duml_proto.py). Each gets its own
GetVersion request; a per-device timeout then decides match/mismatch/unknown/no-reply.

Needs aoa_relay_server.py already running and the phone connected as AOA accessory
(docs/phone-bridge-operator-guide.md). Without that, every device correctly reports
"not connected" rather than crashing - this is a read-only diagnostic, safe to run
with no aircraft/RC present.

Usage: python3 -I scripts/re/fw_version_check.py [--wait SECONDS]
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from _log import log  # noqa: E402
from duml_proto import DeviceType, build_frame, send_via_proxy, session_log_dir  # noqa: E402
from duml_telemetry import tail_frames  # noqa: E402

GETVERSION_CSET, GETVERSION_CID = 0x00, 0x01

# Devices this repo has a live GetVersion receiver type for (issue #32 scope).
# ofdm_radio = DeviceType.ofdm (added to duml_proto.py this session - was missing,
# gap already documented at docs/app-upgrade-sequence.md:332).
#
# remote_controller uses DeviceType.osd (0x0e), NOT DeviceType.remote_controller (0x06):
# docs/identity-queries.md:7,18,22 - on real RC USB-serial hardware, 0x0e answered
# GetVersion/GetDeviceInfo/GetDeviceState with real data (hw="GL300C"), while 0x06 got
# no reply to any of 10 queries including GetVersion. DJI's own naming calls 0x0e "OSD"
# even though it is physically the RC handset's main MCU for this purpose.
DEVICES = {
    "flight_controller": DeviceType.flight_controller,
    "gimbal": DeviceType.gimbal,
    "camera": DeviceType.camera,
    "remote_controller": DeviceType.osd,
    "ofdm_radio": DeviceType.ofdm,
}

# "Latest known-good" per module, wire format (4-field dotted, same as CommonVersion
# below). Provenance + translation rule + confidence (V/I) per module:
# docs/firmware-reference-versions.md. Only gimbal's translation is independently
# cross-confirmed (V); the rest follow the same documented ini->wire rule but have no
# cross-check yet (I) - reported alongside the result, never silently upgraded to V.
REFERENCE_VERSIONS = {
    "flight_controller": ("2.4.51.70", "I"),
    "gimbal": ("1.48.0.0", "V"),
    "camera": ("1.32.54.32", "I"),
    "remote_controller": ("4.10.0.6", "I"),
    "ofdm_radio": ("4.1.0.0", "I"),
}

# Any DUML reply on this link arrives near-instantly once sent (observed basis:
# verify.py's gimbal-permission-reply wait, this repo, 2026-10-24) - no measured RTT
# for GetVersion specifically exists yet. 2s default: same margin verify.py uses for
# an equivalent single-reply wait. On expiry: reported as "no reply", not a crash.
DEFAULT_WAIT_S = 2.0


def decode_common_version(payload):
    """GetVersion response layout - offsets fixed this session (awto-dji#32), one byte
    later than app/packages/duml/lib/src/version.dart CommonVersion.fromPayload's
    offsets: that Dart decoder has an off-by-one (missing a second leading "unknown"
    byte), confirmed against two independent sources:
    1. o-gs/dji-firmware-tools' general_version_inquiry_dissector (externally RE'd,
       unrelated to this repo's possibly-wrong-app APK decompile - see awto-dji#30),
       /mnt/2tb/git/dji-firmware-tools/comm_dissector/wireshark/dji-dumlv1-general.lua
       lines 120-160: response = unknown0(1B) + unknown1(1B) + hw(16B) + ldr(4B) +
       app(4B) + flags(4B) [+ 1B or 4B trailer], hw starting at offset 2, not 1.
    2. Two real captured GetVersion replies, captures/sessions/2026-10-24/duml_probe.log
       (docs/identity-queries.md:18 for the first): with THESE (fixed) offsets, the
       RC/GL300C reply's hw field decodes to a clean "GL300C" (the old offset produces
       a garbled "\\x10GL300C"); an unprogrammed device's reply (same log, receiver
       0x14) decodes loaderVersion AND firmwareVersion to "255.255.255.254" -
       byte-for-byte the same placeholder pattern independently observed in the SD-card
       upgrade log's own "[19 00]" lines (docs/firmware-upgrade-log-review.md:62-64).
    Layout: hardwareVersion = ASCII @ payload[2:18] (NUL-terminated), firmwareVersion =
    bytes[25,24,23,22] dotted, loaderVersion = bytes[21,20,19,18] dotted, info =
    LE uint32 @26 (bit31=isProduction, bit30=isSupportSafeUpgrade). Needs 30 bytes
    minimum (31/34-byte variants add a trailer the app firmware string doesn't need)."""
    if len(payload) < 30:
        return None
    hw_bytes = payload[2:18]
    nul = hw_bytes.find(0)
    hw = hw_bytes[:nul if nul >= 0 else None].decode("ascii", "replace")

    def dotted(hi, lo):
        return ".".join(f"{payload[i]:02d}" for i in range(hi, lo - 1, -1))

    info = int.from_bytes(payload[26:30], "little")
    return {
        "hardwareVersion": hw,
        "firmwareVersion": dotted(25, 22),
        "loaderVersion": dotted(21, 18),
        "isProduction": bool((info >> 31) & 1),
        "isSupportSafeUpgrade": bool((info >> 30) & 1),
    }


def query_device(log_path, offset, device_type, seq, wait_s):
    """Send GetVersion to device_type, wait up to wait_s for its reply. ->
    decoded dict or None (no reply)."""
    frame = build_frame(sender=DeviceType.app, receiver=device_type, seq=seq,
                         ack_type=2, cmd_set=GETVERSION_CSET, cmd_id=GETVERSION_CID,
                         payload=b"")
    send_via_proxy(frame)
    for sender, _receiver, cset, cid, payload in tail_frames(log_path, wait_s,
                                                                start_offset=offset):
        if cset == GETVERSION_CSET and cid == GETVERSION_CID and sender == device_type:
            return decode_common_version(payload)
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--wait", type=float, default=DEFAULT_WAIT_S,
                     help=f"seconds to wait for each device's reply (default {DEFAULT_WAIT_S})")
    # 0x7a00 matches DiagnosticsCommands' own default sequence base
    # (app/awto_dji_app/lib/link/diagnostics_commands.dart) - not load-bearing, just
    # keeps this tool's sequence numbers in the same range as the app's own.
    ap.add_argument("--seq", type=lambda s: int(s, 0), default=0x7a00)
    args = ap.parse_args()

    log_path = os.path.join(session_log_dir(), "aoa_relay_frames.log")
    relay_up = os.path.exists(log_path)
    if not relay_up:
        log("no aoa_relay_frames.log yet - relay not running / phone not connected; "
            "every device will report 'not connected'", "WARN")

    results = []
    for name, device_type in DEVICES.items():
        ref_version, ref_conf = REFERENCE_VERSIONS.get(name, (None, None))
        if not relay_up:
            results.append((name, None, ref_version, ref_conf, "not connected"))
            continue
        offset = os.path.getsize(log_path)
        try:
            decoded = query_device(log_path, offset, device_type, args.seq, args.wait)
        except SystemExit as e:
            log(f"{name}: {e}", "WARN")
            results.append((name, None, ref_version, ref_conf, "not connected"))
            continue
        args.seq += 1
        if decoded is None:
            results.append((name, None, ref_version, ref_conf, "no reply"))
            continue
        current = decoded["firmwareVersion"]
        if ref_version is None:
            status = "unknown (no reference version)"
        elif current == ref_version:
            status = "match" if ref_conf == "V" else f"match ({ref_conf}, translation unconfirmed)"
        else:
            status = "mismatch" if ref_conf == "V" else f"mismatch ({ref_conf}, translation unconfirmed)"
        results.append((name, decoded, ref_version, ref_conf, status))

    print(f"{'device':<20} {'current fw':<14} {'latest-known':<14} {'conf':<5} status")
    for name, decoded, ref_version, ref_conf, status in results:
        current = decoded["firmwareVersion"] if decoded else "-"
        log(f"{name}: current={current} reference={ref_version or 'none'} "
            f"({ref_conf or '-'}) status={status}")
        print(f"{name:<20} {current:<14} {ref_version or '-':<14} {ref_conf or '-':<5} {status}")

    unknowns = sum(1 for *_x, s in results if s.startswith("unknown"))
    no_replies = sum(1 for *_x, s in results if s in ("no reply", "not connected"))
    mismatches = sum(1 for *_x, s in results if s.startswith("mismatch"))
    log(f"done: {len(results)} devices, {mismatches} mismatch, {unknowns} unknown, "
        f"{no_replies} no-reply/not-connected")


if __name__ == "__main__":
    main()
