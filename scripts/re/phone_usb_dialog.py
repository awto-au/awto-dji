#!/usr/bin/env python3
"""Answer Android's "Allow <app> to access <accessory>?" USB dialog over adb, no touch.

Ticks "Use by default for this USB accessory" (so Android remembers the grant and
launches the app on USB_ACCESSORY_ATTACHED), then taps OK. Control positions come from
the `uiautomator dump` bounds=, never hardcoded pixels.

Exit: 0 granted, 1 dialog not present, 2 controls not found / state not reached.
Usage: python3 -I scripts/re/phone_usb_dialog.py --adb-serial <serial>
Library: accept(serial) -> exit code (used by t600_rc_emulator.py after START).
"""
import argparse
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

TRIES = 3  # dialog may still be animating in; each try re-dumps first, 3 covers ~1 s of settle
ADB_TIMEOUT_S = 15  # uiautomator dump takes ~1-2 s on a phone; 15 s is the stall bound
REMOTE = "/sdcard/awto_usb_dialog.xml"
CHECK_ID = "android:id/alwaysUse"
CHECK_TEXT = "Use by default for this USB accessory"
OK_IDS = ("android:id/button1",)
OK_TEXTS = ("OK", "Allow", "ALLOW")
DIALOG_RE = re.compile(r"(Allow|Open) .* (to access|when)", re.I)

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _centre(bounds):
    m = _BOUNDS.fullmatch(bounds)
    if not m:
        return None
    x1, y1, x2, y2 = map(int, m.groups())
    return (x1 + x2) // 2, (y1 + y2) // 2


def parse_dialog(xml_text):
    """-> None if no dialog, else dict(checkbox=(x,y)|None, checked=bool|None, ok=(x,y)|None)."""
    root = ET.fromstring(xml_text)
    nodes = list(root.iter("node"))
    if not any(DIALOG_RE.search(n.get("text", "")) or n.get("text") == CHECK_TEXT
               for n in nodes):
        return None
    res = dict(checkbox=None, checked=None, ok=None)
    for n in nodes:
        rid, text, cls = n.get("resource-id", ""), n.get("text", ""), n.get("class", "")
        if res["checkbox"] is None and (rid == CHECK_ID or text == CHECK_TEXT) \
                and "CheckBox" in cls:
            res["checkbox"] = _centre(n.get("bounds", ""))
            res["checked"] = n.get("checked") == "true"
        elif res["ok"] is None and "Button" in cls and \
                (rid in OK_IDS or text in OK_TEXTS):
            res["ok"] = _centre(n.get("bounds", ""))
    return res


def _adb(serial, *args):
    return subprocess.run(["adb", "-s", serial, *args], capture_output=True, text=True,
                          timeout=ADB_TIMEOUT_S, check=True).stdout


class NeverIdle(Exception):
    """A constantly-redrawing foreground app (the bench) cannot be dumped; the dialog is not on top."""


def dump(serial):
    local = os.path.join("tmp", f"usb_dialog_{serial}.xml")
    os.makedirs(os.path.dirname(local), exist_ok=True)
    r = subprocess.run(["adb", "-s", serial, "shell", "uiautomator", "dump", REMOTE],
                       capture_output=True, text=True, timeout=ADB_TIMEOUT_S)
    if "could not get idle state" in r.stdout + r.stderr:
        raise NeverIdle((r.stdout + r.stderr).strip())
    _adb(serial, "pull", REMOTE, local)
    with open(local, encoding="utf-8") as f:
        return f.read()


def tap(serial, xy):
    _adb(serial, "shell", "input", "tap", str(xy[0]), str(xy[1]))


def accept(serial, dump_fn=None, tap_fn=None, log=print):
    dump_fn = dump_fn or (lambda: dump(serial))
    tap_fn = tap_fn or (lambda xy: tap(serial, xy))
    for attempt in range(1, TRIES + 1):
        try:
            d = parse_dialog(dump_fn())
        except NeverIdle:
            log("usb-dialog: not present (foreground app never idles, so no dialog is on top)")
            return 1
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ET.ParseError) as e:
            log(f"usb-dialog: cannot read the screen on try {attempt} ({type(e).__name__}); "
                "is it on and unlocked?")
            return 3
        if d is None:
            if attempt == 1:
                log("usb-dialog: not present")
                return 1
            log(f"usb-dialog: gone after try {attempt - 1} -> granted")
            return 0
        if d["checkbox"] is None or d["ok"] is None:
            log(f"usb-dialog: controls missing on try {attempt}: {d}")
            continue
        if d["checked"] is False:
            tap_fn(d["checkbox"])
            d2 = parse_dialog(dump_fn())  # verify checked state before OK
            if d2 is None or not d2["checked"]:
                log(f"usb-dialog: checkbox not ticked on try {attempt}")
                continue
            d = d2
        tap_fn(d["ok"])
        log(f"usb-dialog: tapped OK on try {attempt}")
        if parse_dialog(dump_fn()) is None:
            return 0
    return 2


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--adb-serial", required=True)
    sys.exit(accept(ap.parse_args().adb_serial))


if __name__ == "__main__":
    main()
