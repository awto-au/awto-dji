#!/usr/bin/env python3
"""Play the DJI RC ('T600', the AOA accessory HOST) toward the phone app, no real RC.

Modes:
  handshake            AOA switch, then verify on the phone via adb (AdbObserver)
  listen --seconds N   read bulk from the phone, print channel + CRC-valid DUML frames
  replay FILE          send recorded RC->phone envelopes (raw bytes or hex text lines)

SAFETY (enforced in replay_filter, tested): only frames whose DUML receiver is 0x02
(the app) are ever sent. Everything else is refused. A frame whose sender is the app
(0x02) is never sent or originated. This tool cannot issue flight-control commands:
it builds no frames, it only forwards recorded ones that pass the filter.

Backends: PyUsbBackend (PC is host, phone on a PC USB port), CynthionBackend (stub).
Generic AOA handshake lives in cynthion-workspace scripts/tools/aoa_probe.py; the
DJI-specific identity lives here / aoa_identity.dart.
Log: tmp/logs/t600_rc_emulator.log
"""
import argparse
import logging
import os
import re
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aoa_mux import AoaMux, COMMAND  # noqa: E402
from duml_proto import crc8, crc16, repo_root  # noqa: E402

log = logging.getLogger("t600")

APP = 0x02
IDENTITY_DART = "app/awto_dji_app/lib/transport/aoa_identity.dart"
# V: docs/aoa-live-test-2026-10-23.md - current_accessory as read off the phone.
DESCRIPTION, VERSION, URI, SERIAL = "DJI", "v1.2.3.4", "www.dji.com", "12345678"
AOA_VID, AOA_PIDS = 0x18D1, (0x2D00, 0x2D01)
# Re-enumeration into accessory mode ~1.5 s (aoa_probe/live tests); limit 5 s (~3x);
# poll 100 ms. On expiry: raise with elapsed time.
REENUM_LIMIT_S, REENUM_POLL_S = 5.0, 0.1
# Bulk read: one 512 B packet at USB HS is <1 ms; RC link idles are bounded by the
# listen loop. 200 ms keeps the loop responsive; expiry just means "no data yet".
READ_TIMEOUT_MS = 200
WRITE_TIMEOUT_MS = 200  # a 512 B bulk OUT is <1 ms; 200 ms = clear stall
ADB_TIMEOUT_S = 10  # dumpsys/logcat return in <1 s; 10 s = stall


def parse_identity(path=None):
    """manufacturer/model parsed from aoa_identity.dart; raises if the file changed shape."""
    path = path or os.path.join(repo_root(), IDENTITY_DART)
    text = open(path, encoding="utf-8").read()
    out = {}
    for key in ("manufacturer", "model"):
        m = re.search(rf"static const String {key} = '([^']+)';", text)
        if not m:
            raise ValueError(f"{path}: no `static const String {key} = '...';`")
        out[key] = m.group(1)
    return out


def aoa_strings(identity=None):
    i = identity or parse_identity()
    return [i["manufacturer"], i["model"], DESCRIPTION, VERSION, URI, SERIAL]


class Backend:
    def open(self): raise NotImplementedError
    def switch_to_accessory(self, strings): raise NotImplementedError
    def read_bulk(self, size, timeout_ms): raise NotImplementedError
    def write_bulk(self, data, timeout_ms): raise NotImplementedError
    def close(self): raise NotImplementedError


class PyUsbBackend(Backend):
    """PC as USB host. Phone found by --vid/--pid (default: any non-AOA device is not
    guessed; pass them) and re-found as 18d1:2d00/2d01 after the switch."""

    def __init__(self, vid, pid):
        self.vid, self.pid, self.dev, self.ep_in, self.ep_out = vid, pid, None, None, None

    def open(self):
        import usb.core
        self.dev = usb.core.find(idVendor=self.vid, idProduct=self.pid)
        if self.dev is None:
            raise RuntimeError(f"no USB device {self.vid:04x}:{self.pid:04x}")

    def switch_to_accessory(self, strings):
        import usb.core
        import usb.util
        ver = self.dev.ctrl_transfer(0xC0, 51, 0, 0, 2)
        proto = ver[0] | (ver[1] << 8)
        log.info("AOA protocol %d", proto)
        if proto < 1:
            raise RuntimeError("device does not speak AOA")
        for idx, s in enumerate(strings):
            self.dev.ctrl_transfer(0x40, 52, 0, idx, s.encode() + b"\0")
        self.dev.ctrl_transfer(0x40, 53, 0, 0, None)
        usb.util.dispose_resources(self.dev)
        t0 = time.monotonic()
        self.dev = None
        while time.monotonic() - t0 < REENUM_LIMIT_S:
            for pid in AOA_PIDS:
                self.dev = usb.core.find(idVendor=AOA_VID, idProduct=pid)
                if self.dev:
                    break
            if self.dev:
                break
            time.sleep(REENUM_POLL_S)
        if self.dev is None:
            raise TimeoutError(
                f"phone did not re-enumerate as 18d1:2d00/2d01 in {REENUM_LIMIT_S}s "
                f"(elapsed {time.monotonic() - t0:.1f}s)")
        self.dev.set_configuration()
        intf = self.dev.get_active_configuration()[(0, 0)]
        self.ep_out = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_OUT)
        self.ep_in = usb.util.find_descriptor(
            intf, custom_match=lambda e: usb.util.endpoint_direction(e.bEndpointAddress)
            == usb.util.ENDPOINT_IN)

    def read_bulk(self, size, timeout_ms):
        import usb.core
        try:
            return bytes(self.ep_in.read(size, timeout_ms))
        except usb.core.USBTimeoutError:
            return b""

    def write_bulk(self, data, timeout_ms):
        self.ep_out.write(data, timeout_ms)

    def close(self):
        import usb.util
        if self.dev is not None:
            usb.util.dispose_resources(self.dev)


class CynthionBackend(Backend):
    """Stub. Will drive the Cynthion RV shell console verbs:
      usb <port> aoa      - run the AOA switch with the strings from aoa_strings()
      usb <port> tx <hex> - bulk OUT
      usb <port> rx       - bulk IN (hex)
    Not implemented until the shell gains those verbs.
    """

    def __init__(self, *a, **k):
        raise NotImplementedError("CynthionBackend: needs `usb <port> aoa|tx|rx` shell verbs")

    open = switch_to_accessory = read_bulk = write_bulk = close = lambda *a, **k: None


class AdbObserver:
    """Reads the phone side. Parse only; the adb serial is always an argument."""

    def __init__(self, serial, run=None):
        self.serial = serial
        self._run = run or self._adb

    def _adb(self, *args):
        return subprocess.run(["adb", "-s", self.serial, *args], capture_output=True,
                              text=True, timeout=ADB_TIMEOUT_S, check=True).stdout

    @staticmethod
    def parse_usb(text):
        fn = re.search(r"current_functions=(\S+)", text)
        acc = re.search(r"current_accessory=(\{[^}]*\}|null)", text)
        return {"current_functions": fn.group(1) if fn else None,
                "current_accessory": acc.group(1) if acc else None}

    @staticmethod
    def parse_logcat(text):
        return [ln for ln in text.splitlines()
                if "[transport:android-accessory]" in ln or "[link]" in ln]

    def usb_state(self):
        return self.parse_usb(self._run("shell", "dumpsys", "usb"))

    def app_log(self):
        return self.parse_logcat(self._run("logcat", "-d", "-s", "flutter"))


def verify_accessory(state, identity):
    acc = state.get("current_accessory") or ""
    return ("ACCESSORY" in (state.get("current_functions") or "")
            and f"manufacturer={identity['manufacturer']}" in acc
            and f"model={identity['model']}" in acc)


def handshake(backend, observer=None, identity=None):
    identity = identity or parse_identity()
    backend.open()
    backend.switch_to_accessory(aoa_strings(identity))
    if observer is None:
        return True
    state = observer.usb_state()
    log.info("phone usb state: %s", state)
    return verify_accessory(state, identity)


def duml_ok(frame):
    if len(frame) < 13 or frame[0] != 0x55:
        return False
    length = (frame[1] | (frame[2] << 8)) & 0x3FF
    return (length == len(frame) and crc8(0x77, frame[:3]) == frame[3]
            and crc16(0x3692, frame[:-2]) == frame[-2] | (frame[-1] << 8))


def replay_filter(frame):
    """(allowed, reason). Only CRC-valid frames with receiver 0x02 and sender != 0x02."""
    if not duml_ok(frame):
        return False, "not a CRC-valid DUML frame"
    sender, receiver = frame[4] & 0x1F, frame[5] & 0x1F
    if sender == APP:
        return False, "sender is the app"
    if receiver != APP:
        return False, f"receiver 0x{receiver:02x} is not the app"
    return True, ""


def envelope(payload, channel=COMMAND):
    return b"\x55\xcc" + struct.pack("<HI", channel, len(payload)) + payload


def load_capture(path):
    raw = open(path, "rb").read()
    try:
        txt = raw.decode("ascii").split()
        if txt and all(re.fullmatch(r"(?:[0-9a-fA-F]{2})+", t) for t in txt):
            return bytes.fromhex("".join(txt))
    except UnicodeDecodeError:
        pass
    return raw


def replay(backend, data):
    sent = refused = 0
    for pkt in AoaMux().feed(data):
        if pkt.channel != COMMAND:
            continue
        ok, why = replay_filter(pkt.payload)
        if not ok:
            refused += 1
            log.warning("REFUSED: %s: %s", why, pkt.payload.hex())
            continue
        backend.write_bulk(envelope(pkt.payload), WRITE_TIMEOUT_MS)
        sent += 1
        log.info("sent %s", pkt.payload.hex())
    log.info("replay done: sent=%d refused=%d", sent, refused)
    return sent, refused


def listen(backend, seconds, out=print):
    mux, t0, n = AoaMux(), time.monotonic(), 0
    while time.monotonic() - t0 < seconds:
        data = backend.read_bulk(16384, READ_TIMEOUT_MS)
        if not data:
            continue
        for pkt in mux.feed(data):
            valid = duml_ok(pkt.payload)
            n += 1
            out(f"ch=0x{pkt.channel:04x} len={len(pkt.payload)} duml_crc_ok={valid}"
                + (f" sender=0x{pkt.payload[4] & 0x1f:02x} receiver=0x{pkt.payload[5] & 0x1f:02x}"
                   f" set=0x{pkt.payload[9]:02x} id=0x{pkt.payload[10]:02x}" if valid else ""))
    return n


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["handshake", "listen", "replay"])
    ap.add_argument("file", nargs="?", help="capture for replay")
    ap.add_argument("--vid", type=lambda s: int(s, 16), help="phone USB VID (hex)")
    ap.add_argument("--pid", type=lambda s: int(s, 16), help="phone USB PID (hex)")
    ap.add_argument("--adb-serial", help="phone adb serial (verify / dialog accept)")
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--accept-dialog", action="store_true",
                    help="after START, answer the permission dialog via phone_usb_dialog")
    a = ap.parse_args(argv)
    logdir = os.path.join(repo_root(), "tmp", "logs")
    os.makedirs(logdir, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", handlers=[
        logging.FileHandler(os.path.join(logdir, "t600_rc_emulator.log")),
        logging.StreamHandler()])
    if a.vid is None or a.pid is None:
        ap.error("--vid and --pid are required")
    be = PyUsbBackend(a.vid, a.pid)
    obs = AdbObserver(a.adb_serial) if a.adb_serial else None
    try:
        if a.mode == "handshake":
            if a.accept_dialog and a.adb_serial:
                import threading
                import phone_usb_dialog
                threading.Timer(1.0, phone_usb_dialog.accept, [a.adb_serial]).start()
            ok = handshake(be, obs)
            log.info("handshake %s", "verified" if ok else "NOT verified")
            return 0 if ok else 1
        if a.mode == "replay":
            if not a.file:
                ap.error("replay needs FILE")
            be.open()
            be.switch_to_accessory(aoa_strings())
            replay(be, load_capture(a.file))
            return 0
        be.open()
        be.switch_to_accessory(aoa_strings())
        listen(be, a.seconds)
        return 0
    finally:
        be.close()


if __name__ == "__main__":
    sys.exit(main())
