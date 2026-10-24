#!/usr/bin/env python3
"""Decode DJI USB-serial traffic from a USBPcap capture (.pcapng). Portable replacement for the old
duml_pcap_decode.ps1 / cdc_ctrl_decode.ps1.

  python scripts/pcap_decode.py duml captures/foo.pcapng   # DUML frames, per device and direction
  python scripts/pcap_decode.py cdc  captures/foo.pcapng   # baud / data format / DTR+RTS / break

Needs tshark (Wireshark) on PATH, or at the Windows default location, only to read the capture.
Input must be a USBPcap capture (Windows). Linux usbmon captures use a different pseudo-header and
are not handled yet.

USBPcap pseudo-header (little endian): headerLen u16 @0, irpId u64 @2, status u32 @10, function u16 @14,
info u8 @16 (bit0: 1 = device->host completion), bus u16 @17, device u16 @19, endpoint u8 @21,
transfer u8 @22 (0 iso, 1 interrupt, 2 control, 3 bulk), dataLength u32 @23, control stage u8 @27.
For a control URB the stage-0 packet carries the 8-byte setup at headerLen (plus the data for OUT
requests); the answer to an IN request is in the later device->host packet.

DUML framing is shared with duml_probe.py (CRC8 / CRC16 / stream reassembly).
"""
import argparse
import json
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_probe import parse_stream  # noqa: E402
from _log import log  # noqa: E402


def find_tshark():
    for c in (shutil.which('tshark'), r'C:\Program Files\Wireshark\tshark.exe', '/usr/bin/tshark'):
        if c and os.path.exists(c):
            return c
    sys.exit('tshark not found (install Wireshark)')


def urbs(pcap, display_filter):
    """Yield (time, raw_bytes) for every packet matching the filter."""
    out = subprocess.run([find_tshark(), '-r', pcap, '-Y', display_filter, '-T', 'json', '-x'],
                         capture_output=True, check=True).stdout
    for p in json.loads(out):
        lay = p['_source']['layers']
        yield float(lay['frame']['frame.time_relative']), bytes.fromhex(lay['frame_raw'][0])


def hdr(b):
    hl = struct.unpack_from('<H', b, 0)[0]
    return dict(hl=hl, info=b[16], bus=struct.unpack_from('<H', b, 17)[0], dev=struct.unpack_from('<H', b, 19)[0],
                ep=b[21], xfer=b[22], stage=b[27] if len(b) > 27 else None)


def cmd_duml(pcap):
    bufs = {}
    rows = []
    for t, b in urbs(pcap, 'usb.transfer_type==0x03 && usb.data_len>0'):
        h = hdr(b)
        data = b[h['hl']:]
        if not data:
            continue
        to_host = bool(h['info'] & 1)
        key = (h['bus'], h['dev'], to_host)
        buf = bufs.setdefault(key, bytearray())
        buf += data
        frames, rest = parse_stream(buf)
        bufs[key] = bytearray(rest)
        for f, ok in frames:
            rows.append((t, h['bus'], h['dev'], '<<' if to_host else '>>', f, ok))
    print(f"{'t':>9} dir dev  snd rcv seq  type set id crc payload")
    for t, bus, dev, d, f, ok in rows:
        pl = f[11:-2] if len(f) > 13 else b''
        txt = ''.join(chr(c) if 32 <= c < 127 else '.' for c in pl)
        s = f"{t:9.3f} {d}  {bus}.{dev}  {f[4]:02x}  {f[5]:02x}  {f[7]:02x}{f[6]:02x} {f[8]:02x}   {f[9]:02x}  {f[10]:02x} {'ok ' if ok else 'BAD'} {pl.hex()}"
        if sum(1 for c in pl if 32 <= c < 127) >= 6:
            s += f"  | {txt}"
        print(s)
    log(f"{len(rows)} DUML frames")


NAMES = {0x20: 'SET_LINE_CODING', 0x21: 'GET_LINE_CODING', 0x22: 'SET_CONTROL_LINE_STATE', 0x23: 'SEND_BREAK'}


def line_coding(t, key, kind, d):
    rate, stop, par, bits = struct.unpack('<IBBB', d[:7])
    stops = ['1', '1.5', '2']
    pars = 'NOEMS'
    print(f"{t:9.3f}  {key}    {kind} line coding: {rate} baud, {bits}{pars[par] if par < 5 else '?'}"
          f"{stops[stop] if stop < 3 else '?'}")


def cmd_cdc(pcap):
    last = {}
    for t, b in urbs(pcap, 'usb.transfer_type==0x02'):
        h = hdr(b)
        key = f"{h['bus']}.{h['dev']}"
        hl = h['hl']
        if h['stage'] == 0 and len(b) >= hl + 8:
            rt, rq, wv, wi, wl = struct.unpack_from('<BBHHH', b, hl)
            if (rt & 0x60) != 0x20:          # class requests only
                last.pop(key, None)
                continue
            last[key] = rq
            nm = NAMES.get(rq, f'0x{rq:02x}')
            if rq == 0x22:
                print(f"{t:9.3f}  {key}  {nm}  wValue=0x{wv:04x}  DTR={wv & 1} RTS={(wv >> 1) & 1}")
            elif rq == 0x23:
                print(f"{t:9.3f}  {key}  {nm}  duration={wv} ms")
            else:
                print(f"{t:9.3f}  {key}  {nm}  wLength={wl}")
            if rq == 0x20 and len(b) >= hl + 15:
                line_coding(t, key, 'set', b[hl + 8:hl + 15])
        elif h['stage'] is not None and h['stage'] >= 1 and last.get(key) == 0x21 and len(b) >= hl + 7:
            line_coding(t, key, 'get', b[hl:hl + 7])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('what', choices=['duml', 'cdc'])
    ap.add_argument('pcap')
    a = ap.parse_args()
    log(f"decode {a.what} {a.pcap}")
    {'duml': cmd_duml, 'cdc': cmd_cdc}[a.what](a.pcap)
    log("done")


if __name__ == '__main__':
    main()
