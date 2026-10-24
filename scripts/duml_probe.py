#!/usr/bin/env python3
"""Read-only DUML probe for a DJI Phantom 3 controller / aircraft USB-serial port.

Sends only harmless queries (GENERAL set 0x00: ping 0x0c, version 0x01, build string 0xff) and prints
the replies; `--listen` just prints whatever the port volunteers (the aircraft FFF0 port emits ASCII
debug lines). Nothing here writes, flashes, calibrates or changes state.

Line setup copies what DJI Assistant 2 does (captures/2026-10-23_assistant2-both-connected.cdc-ctrl.txt):
115200 8N1, RTS asserted, DTR NOT asserted.

Framing (verified against captures/*.pcapng, see --selftest):
  55 | len | ver<<2|len_hi | crc8(first 3 bytes) | sender | receiver | seq(LE16) | type | set | id | payload | crc16(all prior, LE)

Needs pyserial. Close DJI Assistant first (its DJIService holds the port open).

  python scripts/duml_probe.py --selftest
  python scripts/duml_probe.py COM3                  # controller (2CA3:0008)
  python scripts/duml_probe.py COM4 --listen 10      # aircraft side (FFF0:0008): listen 10 s
  python scripts/duml_probe.py COM3 --receiver 1400 --sender 1000 --cmd 0:1

Log: captures/sessions/<today>/duml_probe.log (tracked, real-hardware data; --selftest doesn't log).
"""
import argparse
import datetime
import os
import subprocess
import sys
import time

_logf = None  # set in main(); session_log_dir() lives here too since this script has no
              # sibling helper module to import from (it's used standalone, outside scripts/re/)


def repo_root():
    return os.environ.get("AWTO_DJI_REPO") or subprocess.check_output(
        ["git", "rev-parse", "--show-toplevel"], text=True,
        cwd=os.path.dirname(os.path.abspath(__file__))).strip()


def session_log_dir():
    d = os.path.join(repo_root(), "captures", "sessions", datetime.date.today().isoformat())
    os.makedirs(d, exist_ok=True)
    return d


def tee(msg):
    print(msg)
    if _logf:
        _logf.write(msg + "\n")

# DUML CRCs (reflected): CRC8 poly 0x31 init 0x77; CRC16 poly 0x1021 init 0x3692.
def crc8(data, init=0x77):
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8C if crc & 1 else crc >> 1
    return crc


def crc16(data, init=0x3692):
    crc = init
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0x8408 if crc & 1 else crc >> 1
    return crc


def ttii(s):
    """'1400' -> wire byte: decimal type 14, index 0 -> (index<<5)|type (matches dji-firmware-tools)."""
    s = s.lstrip('m')
    return (int(s[-2:]) << 5) | int(s[:-2])


def build(sender, receiver, seq, cmd_set, cmd_id, payload=b'', ack=2, pack_type=0):
    n = 13 + len(payload)
    hdr = bytes([0x55, n & 0xFF, (n >> 8) & 0x03 | 0x04])
    body = hdr + bytes([crc8(hdr), sender, receiver, seq & 0xFF, seq >> 8,
                        (pack_type << 7) | (ack << 5), cmd_set, cmd_id]) + payload
    c = crc16(body)
    return body + bytes([c & 0xFF, c >> 8])


def parse_stream(buf):
    """Yield (frame_bytes) for each complete 0x55 frame in buf; return (frames, rest)."""
    frames = []
    i = 0
    while i < len(buf):
        if buf[i] != 0x55:
            i += 1
            continue
        if len(buf) - i < 4:
            break
        n = buf[i + 1] | ((buf[i + 2] & 0x03) << 8)
        if n < 13:
            i += 1
            continue
        if len(buf) - i < n:
            break
        f = bytes(buf[i:i + n])
        ok = crc8(f[:3]) == f[3] and crc16(f[:-2]) == f[-2] | f[-1] << 8
        frames.append((f, ok))
        i += n
    return frames, buf[i:]


def show(f, ok):
    sender, receiver = f[4], f[5]
    seq = f[6] | f[7] << 8
    cs, cid = f[9], f[10]
    pl = f[11:-2]
    txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in pl)
    kind = 'ACK/reply' if f[8] & 0x80 else 'request'
    s = f"  {kind} snd={sender:02x} rcv={receiver:02x} seq={seq:04x} set={cs:02x} id={cid:02x} crc={'ok' if ok else 'BAD'} payload={pl.hex()}"
    if sum(1 for c in pl if 32 <= c < 127) >= 6:
        s += f"  ascii={txt!r}"
    tee(s)


def selftest():
    # Request/reply bytes taken from captures/2026-10-23_assistant2-phantom_p3-controller.pcapng
    req = bytes.fromhex('550d04330a0e00004000' '01' 'e803')
    mine = build(ttii('1000'), ttii('1400'), 0, 0x00, 0x01)
    assert mine == req, (mine.hex(), req.hex())
    rep = bytes.fromhex('552c04360e0a000080000100' '10474c333030430000000000000000000007010103001c18054302000000' '89d4')
    frames, rest = parse_stream(rep)
    assert frames and frames[0][1] and not rest, 'reply CRC check failed'
    print('selftest ok: request bytes and reply CRCs match the capture')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('port', nargs='?')
    ap.add_argument('--sender', default='1000', help='TTII, default 1000 (PC)')
    ap.add_argument('--receiver', default='1400', help='TTII, default 1400 (what the controller answered)')
    ap.add_argument('--cmd', action='append', help='SET:ID (decimal or 0x..); default ping/version/build. Only use read-only ones')
    ap.add_argument('--payload', default='', help='hex payload sent with every --cmd, e.g. 01030a0c0d0f')
    ap.add_argument('--listen', type=float, default=0, help='seconds to listen without sending')
    ap.add_argument('--heartbeat', action='store_true', help='with --listen: send the Assistant-style ping every 0.5 s')
    ap.add_argument('--wait', type=float, default=1.5, help='seconds to wait for each reply')
    ap.add_argument('--baud', type=int, default=115200)
    ap.add_argument('--selftest', action='store_true')
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if not a.port:
        ap.error('port required (or --selftest)')

    global _logf
    log_path = os.path.join(session_log_dir(), 'duml_probe.log')
    _logf = open(log_path, 'a', buffering=1)
    tee(f"\n=== {datetime.datetime.now().isoformat(timespec='seconds')} {' '.join(sys.argv[1:])} ===")

    import serial
    ser = serial.Serial()
    ser.port, ser.baudrate, ser.timeout = a.port, a.baud, 0.1
    ser.dtr, ser.rts = False, True      # same as DJI Assistant 2; set before open() so there is no later toggle
    ser.open()
    tee(f"opened {a.port} {a.baud} 8N1 RTS=1 DTR=0")
    buf = bytearray()
    raw = [0]

    def pump(seconds):
        nonlocal buf
        end = time.time() + seconds
        got = 0
        while time.time() < end:
            d = ser.read(256)
            if d:
                raw[0] += len(d)
                buf += d
                frames, buf = parse_stream(buf)
                for f, ok in frames:
                    show(f, ok)
                    got += 1
        return got

    if a.listen:
        tee(f"listening {a.listen}s{' with 0.5 s heartbeat' if a.heartbeat else ''} ...")
        end, n = time.time() + a.listen, 0
        while time.time() < end:
            if a.heartbeat:   # what the Assistant sends the FFF0 port: PC -> receiver 00, set 00 id 0c, payload 00
                ser.write(build(ttii('1000'), 0x00, 0x2710 + n, 0x00, 0x0c, b'\x00'))
                n += 1
            pump(0.5 if a.heartbeat else end - time.time())
    else:
        cmds = [tuple(int(x, 0) for x in c.split(':')) for c in a.cmd] if a.cmd else [(0, 0x0c), (0, 0x01), (0, 0xff)]
        for n, (cs, cid) in enumerate(cmds):
            pkt = build(ttii(a.sender), ttii(a.receiver), 0x2700 + n, cs, cid, bytes.fromhex(a.payload))
            tee(f"> set={cs:02x} id={cid:02x}  {pkt.hex()}")
            ser.write(pkt)
            if not pump(a.wait):
                tee("  (no reply)")
    tee(f"{raw[0]} raw bytes received")
    ser.close()


if __name__ == '__main__':
    sys.exit(main())
