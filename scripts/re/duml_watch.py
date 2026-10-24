#!/usr/bin/env python3
"""Stay connected to a DUML serial port across power-cycles/USB re-enumeration, sending
the Assistant-style heartbeat ping continuously. Built for catching a boot-time "Assistant
window" (docs/fc-usb-duml.md) - a bare run of duml_probe.py's --listen exits the moment the
device drops, which is exactly when a power-cycle happens, so it can never see what comes
right after. This reopens instead of exiting.

Only sends the one heartbeat ping (General 0x00/0x0c) - no Set/Write/Control commands.

  python3 -I scripts/re/duml_watch.py /dev/ttyACM11                # until Ctrl+C
  python3 -I scripts/re/duml_watch.py /dev/ttyACM11 --minutes 10

Log: captures/sessions/<today>/duml_watch.log (tracked, real-hardware data).
"""
import argparse
import importlib.util
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from duml_proto import session_log_dir  # noqa: E402


def _load_probe():
    spec = importlib.util.spec_from_file_location('duml_probe', os.path.join(REPO, 'scripts', 'duml_probe.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


probe = _load_probe()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('port')
    ap.add_argument('--minutes', type=float, default=None, help='stop after this long; default: run until Ctrl+C')
    ap.add_argument('--baud', type=int, default=115200)
    # Device present but silent for this long before we even try to open it again: avoids a
    # hot retry loop spamming device-not-found errors while the OS is still re-enumerating.
    REOPEN_WAIT_S = 0.3
    a = ap.parse_args()

    log_path = os.path.join(session_log_dir(), 'duml_watch.log')
    logf = open(log_path, 'a', buffering=1)

    def tee(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}"
        print(line, flush=True)
        logf.write(line + "\n")

    tee(f"=== watching {a.port} {a.baud} 8N1, heartbeat every 0.5s, Ctrl+C to stop ===")
    end = time.time() + a.minutes * 60 if a.minutes else None
    n = 0
    connects = 0
    try:
        while end is None or time.time() < end:
            if not os.path.exists(a.port):
                time.sleep(REOPEN_WAIT_S)
                continue
            import serial
            ser = serial.Serial()
            ser.port, ser.baudrate, ser.timeout = a.port, a.baud, 0.1
            ser.dtr, ser.rts = False, True
            try:
                ser.open()
            except Exception as e:  # noqa: BLE001 - port exists but busy/racing re-enumeration
                tee(f"open failed: {e}")
                time.sleep(REOPEN_WAIT_S)
                continue
            connects += 1
            tee(f"connected (#{connects})")
            buf = bytearray()
            last_ping = 0.0
            try:
                while end is None or time.time() < end:
                    now = time.time()
                    if now - last_ping >= 0.5:
                        ser.write(probe.build(probe.ttii('1000'), 0x00, 0x2710 + n, 0x00, 0x0c, b'\x00'))
                        n += 1
                        last_ping = now
                    d = ser.read(256)
                    if d:
                        # Plain boot/log lines (e.g. "gps init: nack:0 ack:18") aren't DUML
                        # frames, so they'd never surface via parse_stream below - show each
                        # newly-arrived chunk's printable content as it comes in, separately
                        # from the line-reassembly buffer used for framing.
                        text = d.decode('ascii', 'replace')
                        if sum(1 for c in text if c.isprintable()) >= len(text) * 0.6:
                            tee(f"  raw: {text!r}")
                        buf += d
                        frames, buf = probe.parse_stream(buf)
                        for f, ok in frames:
                            probe.show(f, ok)
                            tee(f"  reply: {f.hex()} crc={'ok' if ok else 'BAD'}")
            except Exception as e:  # noqa: BLE001 - disconnect mid-session; reconnect and keep going
                tee(f"disconnected: {e}")
            finally:
                try:
                    ser.close()
                except Exception:  # noqa: BLE001 - already gone
                    pass
    except KeyboardInterrupt:
        pass
    tee(f"stopped after {connects} connect(s), {n} pings sent")


if __name__ == '__main__':
    sys.exit(main())
