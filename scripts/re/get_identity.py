#!/usr/bin/env python3
"""READ-ONLY identity/serial/version query of the Phantom 3 RC over its USB-serial DUML port.

Sends ONLY the whitelisted pure-read queries in QUERIES (no --cmd, no free-form payload) to a short
explicit receiver list. No Set/Write/Control/Loader/Update/Reboot/Reset/Calibrate/Activate/file/key
commands exist in this script. See docs/identity-queries.md for how each was verified.

  python3 -I scripts/re/get_identity.py --dry-run                  # print frames, open nothing
  python3 -I scripts/re/get_identity.py --port /dev/ttyACM4        # RC, receiver 0x0e
  python3 -I scripts/re/get_identity.py --port /dev/ttyACM4 --receivers 0e,08,0d,06

Line setup as duml_probe.py: 115200 8N1, RTS=1, DTR=0 set before open.
Log: captures/sessions/<today>/get_identity.log (tracked, real-hardware data).
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

LOG = os.path.join(session_log_dir(), 'get_identity.log')


def _load_probe():
    spec = importlib.util.spec_from_file_location('duml_probe', os.path.join(REPO, 'scripts', 'duml_probe.py'))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


probe = _load_probe()

SENDER = 0x0a  # PC, type 10 idx 0
# Receiver wire bytes (type | idx<<5). 0e = OSD/'1400' (what the RC answers); 08 = DM368 (app uses it for 0x51);
# 0d = DM368_G; 06 = RC type. All local-to-RC modules; none is a flight-side target.
ALLOWED_RECEIVERS = {0x0e, 0x08, 0x0d, 0x06}
# Hard deny: cmdsets/ids this tool must never carry (belt and braces; QUERIES is already a whitelist).
# name, set, id, payload, source note. Every entry is a Get/Query/Version/Serial in dissector AND catalog.
QUERIES = [
    ('GetDeviceState', 0x00, 0x0c, b'', 'dissector General 0x0c Get Device State; catalog GetDeviceStatus'),
    ('GetVersion', 0x00, 0x01, b'', 'dissector General 0x01 version inquiry; APK DataCommonGetVersion (empty payload)'),
    ('GetDeviceInfo', 0x00, 0xff, b'', 'dissector General 0xff Query Device Info; APK DataCommonGetDeviceInfo (empty)'),
    ('GetSerialNum(BoardNum)', 0x00, 0x51, b'\x01', 'dissector General 0x51 Get Serial Number; APK DataCommonGetDeviceSerialNumber idx 1'),
    ('GetSerialNum(ChipId)', 0x00, 0x51, b'\x02', 'same, idx 2'),
    ('GetSerialNum(ModuleNum)', 0x00, 0x51, b'\x03', 'same, idx 3'),
    ('GetSerialNum(FlycNum)', 0x00, 0x51, b'\x04', 'same, idx 4 (FC serial; expected only from a flight controller)'),
    ('RcGetName', 0x06, 0x09, b'', 'dissector RC 0x09 RC Name Get; APK DataRcGetName (empty, receiver OSD)'),
    ('RcGetMaster', 0x06, 0x07, b'', 'dissector RC 0x07 Master/Slave Mode Get; APK DataRcGetMaster (empty)'),
    ('RcGetConnectMaster', 0x06, 0x0d, b'', 'dissector RC 0x0d Connected Master Id Get; APK DataRcGetConnectMaster (empty)'),
]
# Names that must never appear in a query name; asserted at import.
FORBIDDEN = ('Set', 'Write', 'Control', 'Loader', 'Update', 'Upgrade', 'Reboot', 'Restart', 'Reset', 'Calibrat',
             'Unlock', 'Activ', 'Transfer', 'File', 'Delete', 'Format', 'Encrypt', 'Key', 'Password')
for _n, _s, _i, _p, _src in QUERIES:
    assert not any(f in _n for f in FORBIDDEN), _n
    assert (_s, _i) in {(0, 0x0c), (0, 0x01), (0, 0xff), (0, 0x51), (6, 0x09), (6, 0x07), (6, 0x0d)}, _n

_logf = None


def out(msg=''):
    print(msg)
    if _logf:
        _logf.write(msg + '\n')
        _logf.flush()


def ascii_runs(b, minlen=4):
    runs, cur = [], ''
    for c in b:
        if 32 <= c < 127:
            cur += chr(c)
        else:
            if len(cur) >= minlen:
                runs.append(cur)
            cur = ''
    if len(cur) >= minlen:
        runs.append(cur)
    return runs


def decode(name, pl):
    """Return a human decode string for a reply payload (pl = bytes after set/id)."""
    s = f"len={len(pl)} hex={pl.hex()}"
    if name == 'RcGetConnectMaster' and len(pl) >= 12:
        s = f"len={len(pl)} id=0x{int.from_bytes(pl[0:4], 'little'):08x} name={pl[4:10]!r} pairing-password=<elided> raw[0:10]={pl[:10].hex()}"
    elif name.startswith('GetSerialNum') and len(pl) >= 2:
        n = int.from_bytes(pl[0:2], 'little')
        s += f" | declared_len={n}"
    runs = ascii_runs(pl)
    if runs:
        s += f" | ascii={runs}"
    return s


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--port', help='RC serial port, e.g. /dev/ttyACM4')
    ap.add_argument('--receivers', default='0e', help='comma list of receiver wire bytes (hex); allowed: '
                    + ','.join(f'{r:02x}' for r in sorted(ALLOWED_RECEIVERS)))
    ap.add_argument('--dry-run', action='store_true', help='print frames only, open no port')
    ap.add_argument('--wait', type=float, default=0.5,
                    help='per-query reply wait s; RC answered ping/version within one 115200 frame time (~3 ms) + USB; 0.5 s = >100x')
    a = ap.parse_args()

    recvs = [int(x, 16) for x in a.receivers.split(',')]
    bad = [r for r in recvs if r not in ALLOWED_RECEIVERS]
    if bad:
        ap.error(f'receiver(s) {[hex(b) for b in bad]} not in allowed list')
    if not a.dry_run and not a.port:
        ap.error('--port required unless --dry-run')

    global _logf
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    _logf = open(LOG, 'a')
    out(f"# get_identity {time.strftime('%Y-%m-%dT%H:%M:%S%z')} port={a.port} dry_run={a.dry_run} receivers={a.receivers}")

    plan = []
    seq = 0x2800
    for r in recvs:
        for name, cs, ci, pl, src in QUERIES:
            plan.append((r, name, cs, ci, pl, src, seq, probe.build(SENDER, r, seq, cs, ci, pl)))
            seq += 1
    out('Frames to send (all verified pure reads):')
    for r, name, cs, ci, pl, src, sq, fr in plan:
        out(f"  rcv={r:02x} {name:<24} set={cs:02x} id={ci:02x} payload={pl.hex() or '-'} frame={fr.hex()}  [{src}]")
    if a.dry_run:
        out('dry-run: nothing sent')
        return 0

    import serial
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = a.port, 115200, 0.05
    ser.dtr, ser.rts = False, True
    ser.open()
    out(f"opened {a.port} 115200 8N1 RTS=1 DTR=0")
    buf = bytearray()
    try:
        for r, name, cs, ci, pl, src, sq, fr in plan:
            out(f"> rcv={r:02x} {name} {fr.hex()}")
            ser.write(fr)
            end = time.time() + a.wait
            got = False
            while time.time() < end and not got:
                d = ser.read(256)
                if not d:
                    continue
                buf += d
                frames, buf = probe.parse_stream(buf)
                for f, ok in frames:
                    rseq = f[6] | f[7] << 8
                    is_reply = bool(f[8] & 0x80)
                    rpl = f[11:-2]
                    out(f"  < snd={f[4]:02x} rcv={f[5]:02x} seq={rseq:04x} type={f[8]:02x} set={f[9]:02x} id={f[10]:02x} crc={'ok' if ok else 'BAD'}")
                    if not ok:
                        out('ANOMALY: bad CRC in reply - stopping'); return 2
                    if rseq == sq and is_reply:
                        if (f[9], f[10]) != (cs, ci):
                            out('ANOMALY: reply set/id differ from request - stopping'); return 2
                        out(f"    {name}: {decode(name, rpl)}")
                        got = True
                    else:
                        out(f"    (unsolicited/other) payload={rpl.hex()}")
            if not got:
                out('  (no reply)')
    finally:
        ser.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
