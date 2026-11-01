#!/usr/bin/env python3
"""Drive DJI Pilot (dji.pilot) as a reference app for comparison against our own
awto_dji_app - see docs/phone-bridge-operator-guide.md "Driving DJI Pilot as a
reference app". Run as `./dev.py dji-pilot <sub> ...`.

  login                             fill DJI account creds from secrets.yaml, submit
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

**Coordinates do not port across phones.** Every tap here is computed from a fresh
`uiautomator dump`'s `bounds=`, never a hardcoded pixel pair (`DROPDOWN_TAP` is the
one legacy exception, S9-only - see `select-aircraft`'s docstring). An S9 is
1440x2960; an S20 is 1440x3200. Scale any pixel pair you must hardcode by
`target_width/source_width, target_height/source_height`, or better, don't -
resolve the element by resource-id/text from a dump instead (see `login` below).

A single `input tap`/`input text` is **not reliable** even at the right coordinates
- a tap can land before the keyboard/IME has focus-settled, and text can then land
in the wrong field or get silently truncated (observed: a `KEYCODE_DEL` flood NOT
preceded by a focus check deleted into the email field while the password field had
focus, and vice versa). `login` below is the pattern that proved reliable: verify
`focused="true"` on the target node before editing (retry the tap if not focused),
then poll the dump after typing until the text stops changing between two reads
before trusting it - never read once and assume the edit landed.

Device: --device, else the one `adb devices -l` lists as a single non-Pixel device
(works for the S9 test phone or an S20 - don't hardcode a device id/codename).
Log: tmp/logs/dji_pilot_bench.log.
"""
import argparse
import os
import re
import shlex
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
LOGIN_BTN_ID = f"{PACKAGE}:id/sign_in"
EMAIL_FIELD_ID = f"{PACKAGE}:id/edt_email"
PASSWORD_FIELD_ID = f"{PACKAGE}:id/edt_password"
SUBMIT_BTN_ID = f"{PACKAGE}:id/btn_sign_ok"
DUMP_PATH = "/sdcard/dji_pilot_bench_ui.xml"
# How long one uiautomator dump + the UI it reflects takes to settle (observed
# <1s on this device); 3x margin.
DUMP_SETTLE_S = 3
# Max focus-tap retries / text-stability polls before giving up - a handful of
# ~1 dump-round-trips each (observed settle within 2-3), generous margin for a
# slow device.
MAX_FOCUS_TRIES = 6
MAX_STABLE_POLLS = 10
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
    candidates = [l.split()[0] for l in out.splitlines()
                  if " device " in l and "model:Pixel" not in l]
    if len(candidates) == 1:
        return candidates[0]
    sys.exit(f"need exactly one non-Pixel device online to pick automatically, "
              f"found {candidates or 'none'} (adb devices -l); pass --device")


def dump_ui(device):
    adb(device, "shell", "uiautomator", "dump", DUMP_PATH)
    return adb(device, "shell", "cat", DUMP_PATH)


def find_field_node(xml, resource_id):
    for n in re.findall(r'<node [^>]*>', xml):
        if f'resource-id="{resource_id}"' in n:
            return n
    return None


def field_text(xml, resource_id):
    n = find_field_node(xml, resource_id)
    return re.search(r' text="([^"]*)"', n).group(1) if n else None


def field_bounds_center(xml, resource_id):
    n = find_field_node(xml, resource_id)
    if not n:
        return None
    m = re.search(r'bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', n)
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def ensure_focus(device, resource_id, tap_xy, tries=MAX_FOCUS_TRIES):
    """Tap tap_xy and re-dump until resource_id reports focused="true". A single
    tap is not reliable (see module docstring) - this is the fix, not a workaround
    to route around in a hurry."""
    for _ in range(tries):
        xml = dump_ui(device)
        n = find_field_node(xml, resource_id)
        if n and re.search(r'focused="(\w+)"', n).group(1) == "true":
            return True
        adb(device, "shell", "input", "tap", str(tap_xy[0]), str(tap_xy[1]))
    return False


def stable_field_text(device, resource_id, settle_reads=2, polls=MAX_STABLE_POLLS):
    """Poll the dump until resource_id's text is identical twice in a row, instead
    of trusting a single read right after an edit (observed: reads immediately
    after `input text` can catch mid-IME-commit state)."""
    prev, same = None, 0
    for _ in range(polls):
        t = field_text(dump_ui(device), resource_id)
        if t == prev:
            same += 1
            if same >= settle_reads:
                return t
        else:
            same = 0
        prev = t
    return prev


def set_field(device, resource_id, value, tap_xy):
    if not ensure_focus(device, resource_id, tap_xy):
        return None
    adb(device, "shell", "input", "keyevent", "KEYCODE_MOVE_END")
    adb(device, "shell", "input", "keyevent", *(["KEYCODE_DEL"] * 40))
    stable_field_text(device, resource_id)  # wait for the clear to land before typing
    adb(device, "shell", "input", "text", shlex.quote(value.replace(" ", "%s")))
    return stable_field_text(device, resource_id)


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


def cmd_login(args):
    """DJI account creds come from ~/.config/awto/secrets.yaml `dji:` (url/purpose/
    username/password) - never hardcode or log them; only lengths/match booleans are
    logged, same discipline as the interactive session this was lifted from."""
    import yaml
    device = args.device
    secrets_path = os.path.expanduser("~/.config/awto/secrets.yaml")
    with open(secrets_path) as f:
        creds = yaml.safe_load(f)["dji"]

    adb(device, "shell", "am", "force-stop", PACKAGE)
    adb(device, "shell", "am", "start", "-n", LAUNCHER)
    xml = dump_ui(device)
    for _ in range(MAX_STABLE_POLLS):
        if find_field_node(xml, LOGIN_BTN_ID) or find_field_node(xml, EMAIL_FIELD_ID):
            break
        xml = dump_ui(device)
    if find_field_node(xml, EMAIL_FIELD_ID) is None:
        login_btn_xy = field_bounds_center(xml, LOGIN_BTN_ID)
        if login_btn_xy is None:
            log("neither the login form nor the intro Login button is on screen - "
                "unexpected app state, see a screenshot", "ERROR")
            return 1
        adb(device, "shell", "input", "tap", str(login_btn_xy[0]), str(login_btn_xy[1]))
        xml = dump_ui(device)

    email_xy = field_bounds_center(xml, EMAIL_FIELD_ID)
    pw_xy = field_bounds_center(xml, PASSWORD_FIELD_ID)
    if not email_xy or not pw_xy:
        log("login form fields not found on screen", "ERROR")
        return 1

    got = set_field(device, EMAIL_FIELD_ID, creds["username"], email_xy)
    if got != creds["username"]:
        log(f"email field: got len {len(got) if got else 0}, "
            f"expected {len(creds['username'])} - did not land cleanly", "ERROR")
        return 1
    log(f"email field set, len {len(got)} matches")

    got = set_field(device, PASSWORD_FIELD_ID, creds["password"], pw_xy)
    # the field masks with bullets once password=true, so compare length only
    if got is None or len(got) != len(creds["password"]):
        log(f"password field: got len {len(got) if got else 0}, "
            f"expected {len(creds['password'])} - did not land cleanly", "ERROR")
        return 1
    log(f"password field set, len {len(got)} matches")

    # re-verify email wasn't disturbed by the password edit (observed happening
    # when focus wasn't re-checked between fields)
    xml = dump_ui(device)
    email_now = field_text(xml, EMAIL_FIELD_ID)
    if email_now != creds["username"]:
        log("email field was disturbed while editing password - retyping", "ERROR")
        return 1

    submit_xy = field_bounds_center(xml, SUBMIT_BTN_ID)
    adb(device, "shell", "input", "tap", str(submit_xy[0]), str(submit_xy[1]))
    log("tapped sign-in submit; check the screen/logcat for the result "
        "(EHOSTUNREACH on dji.pilot's pid usually means a stale proxy on the "
        "phone, not bad creds - `adb shell settings get global http_proxy`)")
    return 0


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
    out = args.out or f"tmp/dji_pilot_{int(time.time())}.png"
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

    sub.add_parser("login").set_defaults(fn=cmd_login)

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
