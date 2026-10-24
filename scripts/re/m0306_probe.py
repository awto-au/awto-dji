#!/usr/bin/env python3
"""Drive Renode to boot the real m0306 (flight controller) firmware and probe the USB-CDC
gate found by static trace: all 5 USB OTG NVIC vectors point to the Default_Handler
infinite self-loop at 0x080219a0, not any CDC-receive code (docs/fc-usb-duml.md).

Boots m0306, checks whether the firmware itself ever unmasks USB OTG at the NVIC, then
forces the OTG_HS interrupt enabled+pending (Renode has no STM32 OTG peripheral model, so
this is forced register state standing in for a real USB transaction, same method used for
m0900's AD9363 SPI writers) and shows where the CPU ends up.

Usage:  python3 scripts/re/m0306_probe.py
Env:    RENODE_BIN   path to the built `renode` launcher (default: the git_mirror build)
Log:    tmp/logs/m0306_probe.log
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=HERE,
            stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(HERE, "..", ".."))


ROOT = repo_root()
RENODE = os.environ.get("RENODE_BIN", "/mnt/2tb/git_mirror/renode/renode")
RESC = "renode/scripts/m0306_probe.resc"


def main():
    logs = os.path.join(ROOT, "tmp", "logs")
    os.makedirs(logs, exist_ok=True)
    logpath = os.path.join(logs, "m0306_probe.log")

    cmd = [RENODE, "--console", "--disable-xwt", "-e", f"include @{RESC}"]
    print(f"# running Renode: {RENODE}\n# cwd={ROOT}\n# log={logpath}")
    with open(logpath, "w") as log:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log,
                               stderr=subprocess.STDOUT, text=True)
    print(f"# renode exit={proc.returncode}")

    with open(logpath, errors="replace") as f:
        print(f.read())


if __name__ == "__main__":
    main()
