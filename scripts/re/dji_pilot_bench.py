#!/usr/bin/env python3
"""Drive DJI Pilot (dji.pilot) as a reference app for comparison against our own
awto_dji_app - see docs/phone-bridge-operator-guide.md "Driving DJI Pilot as a
reference app". Run as `./dev.py dji-pilot <sub> ...`.

  select-aircraft [--series PHANTOM] [--version 3] [--subversion PROFESSIONAL]
                                    force-stop, launch, pick the aircraft model
  connect                          tap the "Camera" button (the real connect trigger)
  screenshot [--out PATH]          save a PNG of the current screen

No model-selection intent exists (internal app state, no exported extras) - this
drives the UI via uiautomator dumps, verifying each step actually changed the
screen rather than trusting one gesture blindly (an `adb shell input swipe` on the
aircraft dropdown was unreliable by eye - worked once when the operator did it
on-device, repeatedly failed when scripted at the same coordinates; this tries
several swipe variants and re-checks after each one instead of assuming success).

Device: --device, else the one `adb devices -l` lists as device:starlte (the test S9).
Log: tmp/logs/dji_pilot_bench.log.
"""
import argparse
import os
import subprocess
import sys
import time

HERE = __import__("pathlib").Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
from _log import log  # noqa: E402

PACKAGE = "dji.pilot"
LAUNCHER = f"{PACKAGE}/.main.activity.DJILauncherActivity"
DROPDOWN_TAP = (719, 382)
CONNECT_BTN_ID = f"{PACKAGE}:id/v2_phantom_start_connect_btn"
DUMP_PATH = "/sdcard/dji_pilot_bench_ui.xml"
# How long one uiautomator dump + the UI it reflects takes to settle (observed
# <1s on this device); 3x margin.
DUMP_SETTLE_S = 3
SWIPE_VARIANTS = [
    (720, 500, 720, 200, 300),
    (720, 600, 720, 100, 600),
    (720, 820, 720, 470, 800),
    (720, 850, 720, 460, 1200),
]


def adb(device, *args, check=False):
    r = subprocess.run(["adb", "-s", device] + list(args), capture_output=True, text=True, check=check)
    return r.stdout


def find_device(explicit):
    if explicit:
        return explicit
    out = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "device:starlte" in line and " device " in line:
            return line.split()[0]
    sys.exit("no starlte device online (adb devices -l); pass --device")


def dump_ui(device):
    adb(device, "shell", "uiautomator", "dump", DUMP_PATH)
    return adb(device, "shell", "cat", DUMP_PATH)


def find_row_bounds(xml, series, version, subversion):
    """Returns (x, y) center of the row's item_content_ly if all three labels are
    present as sibling text nodes close together, else None."""
    import re
    blocks = xml.split('item_content_ly"')
    for block in blocks[1:]:
        end = block.find('</node></node>')
        chunk = block[:end] if end > 0 else block[:2000]
        texts = re.findall(r'text="([^"]*)"', chunk)
        if series in texts and version in texts and (not subversion or subversion in texts):
            bounds_m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', block)
            if bounds_m:
                x1, y1, x2, y2 = map(int, bounds_m.groups())
                return (x1 + x2) // 2, (y1 + y2) // 2
    return None


def cmd_select_aircraft(args):
    device = args.device
    adb(device, "shell", "am", "force-stop", PACKAGE)
    adb(device, "shell", "am", "start", "-n", LAUNCHER)
    time.sleep(DUMP_SETTLE_S)
    adb(device, "shell", "input", "tap", *map(str, DROPDOWN_TAP))
    time.sleep(1)

    xml = dump_ui(device)
    target = find_row_bounds(xml, args.series, args.version, args.subversion)
    if target is None:
        log(f"target not visible yet, trying swipe variants to scroll the dropdown")
        for variant in SWIPE_VARIANTS:
            adb(device, "shell", "input", "touchscreen", "swipe", *map(str, variant))
            time.sleep(1)
            xml = dump_ui(device)
            target = find_row_bounds(xml, args.series, args.version, args.subversion)
            if target is not None:
                log(f"swipe variant {variant} worked")
                break
            log(f"swipe variant {variant} did not change visible rows")
    if target is None:
        log(f"could not find {args.series} {args.version} {args.subversion} after "
            f"{len(SWIPE_VARIANTS)} swipe attempts - dropdown may need a manual swipe "
            f"on-device, see docs/phone-bridge-operator-guide.md", "ERROR")
        return 1

    adb(device, "shell", "input", "tap", str(target[0]), str(target[1]))
    time.sleep(1)
    log(f"selected {args.series} {args.version} {args.subversion}")
    return 0


def cmd_connect(args):
    device = args.device
    xml = dump_ui(device)
    import re
    m = re.search(rf'resource-id="{re.escape(CONNECT_BTN_ID)}"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        log(f"connect button ({CONNECT_BTN_ID}) not found on screen - "
            f"run select-aircraft first", "ERROR")
        return 1
    x1, y1, x2, y2 = map(int, m.groups())
    adb(device, "shell", "input", "tap", str((x1 + x2) // 2), str((y1 + y2) // 2))
    log("tapped connect button")
    return 0


def cmd_screenshot(args):
    device = args.device
    out = args.out or f"/tmp/dji_pilot_{int(time.time())}.png"
    r = subprocess.run(["adb", "-s", device, "exec-out", "screencap", "-p"],
                       capture_output=True)
    with open(out, "wb") as f:
        f.write(r.stdout)
    log(f"saved {out} ({len(r.stdout)} bytes)")
    print(out)
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device")
    sub = ap.add_subparsers(dest="sub", required=True)

    p = sub.add_parser("select-aircraft")
    p.add_argument("--series", default="PHANTOM")
    p.add_argument("--version", default="3")
    p.add_argument("--subversion", default="PROFESSIONAL")
    p.set_defaults(fn=cmd_select_aircraft)

    sub.add_parser("connect").set_defaults(fn=cmd_connect)

    p = sub.add_parser("screenshot")
    p.add_argument("--out")
    p.set_defaults(fn=cmd_screenshot)

    args = ap.parse_args()
    args.device = find_device(args.device)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
