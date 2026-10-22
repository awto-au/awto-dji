#!/usr/bin/env python3
"""Drive Renode to capture m0900's AD9363 SPI config, then print the decoded sequence.

Boots the real m0900 firmware in the Renode harness (renode/), then triggers the
DUML-cmdset-0x09 radio bring-up that cold boot never reaches on its own
(awto-au/awto-dji#2; gate proven by scripts/re/m0900_trace.py), and saves the AD9363
register sequence the firmware computes.

Renode resolves relative *write* paths against its own binary dir, so this runner passes
absolute output paths into the .resc via `-e` and runs Renode with cwd = repo root (so the
`@renode/...` read paths resolve).

Usage:  python3 scripts/re/m0900_capture.py
Env:    RENODE_BIN   path to the built `renode` launcher (default: the git_mirror build)
Log:    tmp/logs/m0900_capture.log      Outputs: tmp/spi{1,2}-{capture,raw}.txt
"""
import os
import subprocess
import sys

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
RESC = "renode/scripts/m0900_trigger_capture.resc"


def main():
    tmp = os.path.join(ROOT, "tmp")
    logs = os.path.join(tmp, "logs")
    os.makedirs(logs, exist_ok=True)
    outs = {k: os.path.join(tmp, v) for k, v in {
        "cap1": "spi1-capture.txt", "raw1": "spi1-raw.txt",
        "cap2": "spi2-capture.txt", "raw2": "spi2-raw.txt"}.items()}
    for p in outs.values():
        if os.path.exists(p):
            os.remove(p)

    cmd = [RENODE, "--console", "--disable-xwt"]
    for var, path in outs.items():
        cmd += ["-e", f"${var}=@{path}"]
    cmd += ["-e", f"include @{RESC}"]

    logpath = os.path.join(logs, "m0900_capture.log")
    print(f"# running Renode: {RENODE}\n# cwd={ROOT}\n# log={logpath}")
    with open(logpath, "w") as log:
        proc = subprocess.run(cmd, cwd=ROOT, stdout=log,
                              stderr=subprocess.STDOUT, text=True)
    print(f"# renode exit={proc.returncode}")

    # Report the counts the monitor echoed, and the decoded captures.
    with open(logpath, errors="replace") as f:
        loglines = f.readlines()
    for i, line in enumerate(loglines):
        if "transaction count" in line.lower():
            # the count prints on the following non-empty monitor line
            for j in range(i + 1, min(i + 4, len(loglines))):
                if loglines[j].strip():
                    print("  " + line.strip() + " -> " + loglines[j].strip())
                    break

    for name in ("cap1", "cap2"):
        path = outs[name]
        bus = "SPI1" if name == "cap1" else "SPI2"
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path) as f:
                body = f.read()
            n = sum(1 for ln in body.splitlines() if ln and not ln.startswith("#"))
            print(f"\n===== {bus} capture ({n} transactions): {path} =====")
            print(body if n <= 400 else "\n".join(body.splitlines()[:400]) + "\n...")
        else:
            print(f"\n===== {bus}: no capture written =====")


if __name__ == "__main__":
    main()
