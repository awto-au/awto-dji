#!/usr/bin/env python3
"""Phone/RC bench operations, reusable instead of ad-hoc adb one-liners
(docs/phone-bridge-operator-guide.md). Run as `./dev.py phone <sub> ...`.

  connect [--relay HOST:PORT] [--reads N]   force-stop, CONNECT intent, wait for the relay
                                            connection (and N raw UDP reads if given)
  stop                                      force-stop the app
  reboot                                    adb reboot, then wait for the device to come back
  usb-state [--watch S]                     gadget state, last USB events, foreground window;
                                            --watch prints transitions for S seconds
  send NAME [duml_cli args...]              connect, then duml_cli.py send NAME ...
  trace [phone_usb_trace args...]           kernel-level OUT/IN length trace (phone_usb_trace.py)

Device: --device, else the one `adb devices -l` lists as device:starlte (the test S9).
aoa_relay_server.py must already be running for connect/send/trace. If Android shows the
USB accessory permission prompt, this reports it and waits for it to be accepted on the
phone; it never drives the screen. Log: tmp/logs/phone_bench.log.
"""
import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))
sys.path.insert(0, str(HERE.parent))
from _log import log  # noqa: E402
from duml_proto import session_log_dir  # noqa: E402

ROOT = HERE.parents[2]
APP = "au.awto.dji.awto_dji_app"
DEFAULT_RELAY = "192.168.25.114:9900"
# Connect: relay TCP up within ~3 s of the intent (observed); 15 s = not coming.
CONNECT_S = 15
# Reads: ~10/s while the RC streams (this session); 20 s silent = link not delivering.
STALL_S = 20
# Boot: observed 37-42s on this device (two reboots this session); 90s is a ~2.2x margin.
REBOOT_S = 90


def adb(device, *args, check=False):
    r = subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True, check=check)
    return r.stdout.strip()


def find_device(explicit):
    if explicit:
        return explicit
    out = subprocess.run(["adb", "devices", "-l"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if "device:starlte" in line and " device " in line:
            return line.split()[0]
    sys.exit("no starlte device online (adb devices -l); pass --device")


def relay_log():
    return Path(session_log_dir()) / "aoa_relay_server.log"


def count(path, needle):
    try:
        with open(path) as f:
            return sum(1 for line in f if needle in line)
    except FileNotFoundError:
        return 0


def permission_prompt(device):
    return "UsbPermissionActivity" in adb(device, "shell", "dumpsys", "window") .split("mCurrentFocus")[-1][:200]


def cmd_stop(args):
    adb(args.device, "shell", "am", "force-stop", APP)
    log("app force-stopped")
    return 0


def cmd_reboot(args):
    subprocess.run(["adb", "-s", args.device, "reboot"], capture_output=True, text=True)
    log("reboot issued, waiting for device")
    t0 = time.time()
    while subprocess.run(["adb", "-s", args.device, "shell", "true"],
                          capture_output=True).returncode != 0:
        if time.time() - t0 > REBOOT_S:
            log(f"device not back within {REBOOT_S}s", "ERROR")
            return 1
        time.sleep(1)
    booted = adb(args.device, "shell", "getprop", "sys.boot_completed")
    log(f"device responded after {time.time() - t0:.0f}s, sys.boot_completed={booted!r}")
    if booted != "1":
        log(f"adb responded but boot not yet complete (sys.boot_completed={booted!r}) - "
            f"debugfs/tracefs mounts will need remounting if you were tracing", "WARN")
    return 0


def cmd_connect(args):
    path = relay_log()
    if not path.exists():
        log(f"{path} missing: is aoa_relay_server.py running?", "ERROR")
        return 1
    adb(args.device, "shell", "am", "force-stop", APP)
    c0 = count(path, "=== connection from")
    r0 = count(path, "RAWUDP seq=")
    adb(args.device, "shell", "am", "start", "-n", f"{APP}/.MainActivity",
        "-a", "au.awto.dji.action.CONNECT", "--es", "relay", args.relay)
    log(f"CONNECT sent (relay {args.relay})")
    t0 = time.time()
    warned = False
    while count(path, "=== connection from") == c0:
        if time.time() - t0 > CONNECT_S:
            log(f"no relay connection within {CONNECT_S}s", "ERROR")
            return 1
        time.sleep(0.5)
    log(f"relay connected after {time.time() - t0:.1f}s")
    if not args.reads:
        return 0
    last, last_change = 0, time.time()
    while True:
        n = count(path, "RAWUDP seq=") - r0
        if n != last:
            last, last_change = n, time.time()
        if n >= args.reads:
            log(f"{n} raw reads in {time.time() - t0:.1f}s")
            return 0
        if not warned and permission_prompt(args.device):
            log("USB accessory permission prompt is showing: accept it on the phone", "WARN")
            warned = True
        if time.time() - last_change > STALL_S:
            log(f"stalled: {n} reads, none for {STALL_S}s", "ERROR")
            return 1
        time.sleep(0.5)


def cmd_usb_state(args):
    def snapshot():
        state = adb(args.device, "shell", "cat", "/sys/class/android_usb/android0/state")
        funcs = adb(args.device, "shell", "getprop", "sys.usb.state")
        focus = adb(args.device, "shell", "dumpsys", "window").split("mCurrentFocus=")[-1].split("\n")[0]
        return state, funcs, focus

    state, funcs, focus = snapshot()
    print(f"gadget={state} functions={funcs} focus={focus}")
    events = adb(args.device, "shell", "dumpsys", "usb")
    for line in events.splitlines():
        if re.search(r"UEVENT|USB intent|accessoryAttached", line):
            print(line.strip())
    if args.watch:
        prev = state
        t0 = time.time()
        while time.time() - t0 < args.watch:
            state = snapshot()[0]
            if state != prev:
                log(f"gadget {prev} -> {state}")
                prev = state
            time.sleep(1)
    return 0


def cmd_send(args):
    rc = cmd_connect(args)
    if rc:
        return rc
    time.sleep(1)  # relay socket settles before the first FIFO write (observed ~0.2 s)
    cmd = [sys.executable, "-I", str(HERE.parent / "duml_cli.py"), "send", args.name, *args.rest]
    log("run: " + " ".join(cmd[2:]))
    return subprocess.call(cmd, cwd=ROOT)


def cmd_trace(args):
    cmd = [sys.executable, "-I", str(HERE.parent / "phone_usb_trace.py"),
           "--device", args.device, *args.rest]
    return subprocess.call(cmd, cwd=ROOT)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device")
    sub = ap.add_subparsers(dest="sub", required=True)
    p = sub.add_parser("connect")
    p.add_argument("--relay", default=DEFAULT_RELAY)
    p.add_argument("--reads", type=int, default=0)
    p.set_defaults(fn=cmd_connect)
    sub.add_parser("stop").set_defaults(fn=cmd_stop)
    sub.add_parser("reboot").set_defaults(fn=cmd_reboot)
    p = sub.add_parser("usb-state")
    p.add_argument("--watch", type=int, default=0)
    p.set_defaults(fn=cmd_usb_state)
    p = sub.add_parser("send")
    p.add_argument("name")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.add_argument("--relay", default=DEFAULT_RELAY)
    p.set_defaults(fn=cmd_send, reads=0)
    p = sub.add_parser("trace")
    p.add_argument("rest", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_trace)
    args = ap.parse_args()
    args.device = find_device(args.device)
    os.chdir(ROOT)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
