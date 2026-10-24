"""DUML v1 frame encode + the command-proxy FIFO send, shared by aoa_send.py and the
per-subsystem CLIs (gimbal.py, ...). Not a standalone script - import only.
"""
import datetime
import os
import subprocess


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def session_log_dir():
    """captures/sessions/<today>/ - tracked, for logs from scripts that talk to real
    hardware (not regenerable from firmware/code). Static-analysis scripts keep using
    tmp/logs/ instead (see root CLAUDE.md: derived/regenerable artifacts stay untracked)."""
    d = os.path.join(repo_root(), "captures", "sessions", datetime.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    return d


def crc8(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8C if seed & 1 else seed >> 1
    return seed & 0xFF


def crc16(seed, data):
    for b in data:
        seed ^= b
        for _ in range(8):
            seed = (seed >> 1) ^ 0x8408 if seed & 1 else seed >> 1
    return seed & 0xFFFF


# Device type ids (COMM_DEV_TYPE), matches app/packages/duml/lib/src/packet.dart.
class DeviceType:
    camera = 1
    app = 2
    flight_controller = 3
    gimbal = 4
    center_board = 5
    remote_controller = 6
    pc = 10
    osd = 14  # DJI's own "OSD" naming for this id; RequestGimbalCtrPermission targets it
    ofdm = 9  # air radio MCU (m0900, STM32F103) - gap noted at
    # docs/app-upgrade-sequence.md:332, value per M/data/config/P3/DeviceType.java


def build_frame(sender, receiver, seq, ack_type, cmd_set, cmd_id, payload):
    length = 11 + len(payload) + 2
    out = bytearray(length)
    out[0] = 0x55
    tag = (length & 0x3FF) | (1 << 10)  # version=1
    out[1] = tag & 0xFF
    out[2] = (tag >> 8) & 0xFF
    out[3] = crc8(0x77, out[:3])
    out[4] = sender & 0x1F
    out[5] = receiver & 0x1F
    out[6] = seq & 0xFF
    out[7] = (seq >> 8) & 0xFF
    out[8] = (ack_type & 0x3) << 5  # request, no encryption
    out[9] = cmd_set & 0xFF
    out[10] = cmd_id & 0xFF
    out[11:11 + len(payload)] = payload
    crc = crc16(0x3692, bytes(out[:-2]))
    out[-2] = crc & 0xFF
    out[-1] = (crc >> 8) & 0xFF
    return bytes(out)


def send_via_proxy(frame, fifo_path=None):
    """Write a frame to aoa_relay_server.py's command FIFO. Raises if the FIFO (and so
    presumably the relay server) doesn't exist yet."""
    fifo_path = fifo_path or os.path.join(repo_root(), "tmp", "aoa_send.fifo")
    if not os.path.exists(fifo_path):
        raise SystemExit(f"no command FIFO at {fifo_path} - is aoa_relay_server.py running?")
    with open(fifo_path, "w") as f:
        f.write(frame.hex() + "\n")
