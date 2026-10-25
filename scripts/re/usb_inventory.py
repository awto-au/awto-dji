#!/usr/bin/env python3
"""Snapshot DJI USB devices and USB UART adapters from Linux sysfs.

Reads cached attributes only: no device opens, port claims or USB requests.
Optional watching records enumeration changes for cable/power tests.
"""
import argparse
import datetime
import json
import time
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import log  # noqa: E402

RELEVANT_VENDORS = {'2ca3', 'fff0', '0547', '070a', '04b4', '0403', '067b', '10c4', '1a86'}


def read(path):
    try:
        return path.read_text().strip()
    except OSError:
        return None


def snapshot(include_all=False):
    root = Path('/sys/bus/usb/devices')
    if not root.is_dir():
        raise RuntimeError('USB sysfs is unavailable; enumeration cannot be determined')
    devices = []
    candidates = list(root.iterdir())
    for path in sorted(candidates):
        if ':' in path.name:
            continue
        vendor = read(path / 'idVendor')
        product = read(path / 'product') or ''
        manufacturer = read(path / 'manufacturer') or ''
        if not vendor:
            continue
        if not include_all and vendor not in RELEVANT_VENDORS and 'dji' not in (product + manufacturer).lower():
            continue
        interfaces = []
        for interface in sorted(root.glob(path.name + ':*')):
            driver = interface / 'driver'
            interfaces.append({
                'path': interface.name,
                'class': read(interface / 'bInterfaceClass'),
                'subclass': read(interface / 'bInterfaceSubClass'),
                'protocol': read(interface / 'bInterfaceProtocol'),
                'driver': driver.resolve().name if driver.exists() else None,
                'endpoints': [{
                    'address': read(ep / 'bEndpointAddress'),
                    'attributes': read(ep / 'bmAttributes'),
                    'max_packet': read(ep / 'wMaxPacketSize'),
                } for ep in sorted(interface.glob('ep_*'))],
            })
        actual_path = path.resolve()
        serial_ports = []
        for tty in Path('/sys/class/tty').glob('tty*'):
            if tty.name.startswith(('ttyACM', 'ttyUSB')) and actual_path in tty.resolve().parents:
                serial_ports.append('/dev/' + tty.name)
        devices.append({
            'topology': path.name, 'bus': read(path / 'busnum'), 'address': read(path / 'devnum'),
            'vid': vendor, 'pid': read(path / 'idProduct'), 'manufacturer': manufacturer,
            'product': product, 'serial': read(path / 'serial'), 'speed_mbps': read(path / 'speed'),
            'serial_ports': sorted(serial_ports), 'interfaces': interfaces,
        })
    return {'timestamp': datetime.datetime.now(ZoneInfo('Australia/Melbourne')).isoformat(timespec='seconds'),
            'method': 'cached Linux sysfs; no device opens or application traffic',
            'usb_device_count': sum((p / 'idVendor').exists() for p in candidates),
            'devices': devices}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--watch-seconds', type=float, default=0)
    parser.add_argument('--interval', type=float, default=1)
    parser.add_argument('--all', action='store_true', help='include every USB vendor to detect unrecognized subsystems')
    parser.add_argument('--output', type=Path, help='append JSONL snapshots, initially and on changes')
    args = parser.parse_args()
    if args.watch_seconds < 0 or args.interval <= 0:
        parser.error('watch-seconds must be nonnegative and interval must be positive')
    deadline = time.monotonic() + args.watch_seconds
    previous = None
    while True:
        current = snapshot(args.all)
        signature = (current['usb_device_count'], current['devices'])
        if signature != previous:
            line = json.dumps(current, sort_keys=True)
            print(line, flush=True)
            log(f"snapshot: {current['usb_device_count']} USB devices")
            if args.output:
                with args.output.open('a') as stream:
                    stream.write(line + '\n')
            previous = signature
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))


if __name__ == '__main__':
    main()
