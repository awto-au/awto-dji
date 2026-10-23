#!/usr/bin/env python3
"""Reproducible extraction of the DJI GO 4 APK pieces used by docs/apk-analysis.md.

Run from repo root:  python3 -I scripts/re/apk_extract.py [step ...]
Steps: unzip, manifest, jadx, strings, dexstrings, all (default).
- Finding: classes.dex is a packer stub (1623 amap/autonavi/AppGuard classes, 1.8 MB) + ~37 MB payload;
  DJI code is NOT decompilable (unpacking = anti-tamper analysis, out of scope). `dexstrings` only
  scans printable strings of the file (class names, resource names, constants) - no unpacking.
- APK and outputs are untrusted data: nothing is executed; outputs go to tmp/apk/ (git-ignored).
- Scope: no FlySafe/geofence, signature-verify, anti-tamper or crypto-lib analysis.
- jadx: tmp/tools/jadx (github.com/skylot/jadx v1.5.6, `gh release download`).
Log: tmp/logs/apk_extract.log
"""
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                           text=True, check=True).stdout.strip())
APK = ROOT / "firmware/apk/dji-go-4_v4.3.64.apk"
OUT = ROOT / "tmp/apk"
RAW, MANI, SRC, STR = OUT / "raw", OUT / "manifest", OUT / "jadx", OUT / "strings"
JADX = ROOT / "tmp/tools/jadx/bin/jadx"
LOG = ROOT / "tmp/logs/apk_extract.log"
# libs we only read strings from (video/transport); out-of-scope libs are never touched
LIBS = ["libdjivideo.so", "libvideoLib.so", "libGroudStation.so", "libudtjni.so"]
SKIP = re.compile(r"flysafe|flyforbid|appguard|upgradeverify|waes|sqlcipher|stringfog", re.I)


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run(cmd):
    log("run: " + " ".join(map(str, cmd)))
    r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, errors="replace")
    log(f"rc={r.returncode} tail={(r.stdout + r.stderr)[-400:]!r}")
    return r.returncode


def unzip():
    RAW.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(APK) as z:
        for n in z.namelist():
            base = n.rsplit("/", 1)[-1]
            keep = (n == "classes.dex" or n.startswith("res/xml/")
                    or (n.startswith("lib/arm64-v8a/") and base in LIBS))
            if keep and not SKIP.search(n):
                z.extract(n, RAW)
                log(f"extracted {n}")


def manifest():
    # apktool decodes binary manifest + res/xml (accessory filter); no sources, no assets
    run([str(Path.home() / ".local/bin/apktool"), "d", "-s", "--no-assets", "-f",
         "-o", str(MANI), str(APK)])


def jadx():
    run([str(JADX), "-d", str(SRC), "--no-res", "--threads-count", "8",
         "--log-level", "ERROR", str(RAW / "classes.dex")])


def strings():
    STR.mkdir(parents=True, exist_ok=True)
    for lib in LIBS:
        p = RAW / "lib/arm64-v8a" / lib
        if not p.exists():
            continue
        data = p.read_bytes()
        out = [m.group().decode() for m in re.finditer(rb"[\x20-\x7e]{6,}", data)]
        (STR / f"{lib}.txt").write_text("\n".join(out))
        log(f"strings {lib}: {len(out)}")


def dexstrings():
    STR.mkdir(parents=True, exist_ok=True)
    d = (RAW / "classes.dex").read_bytes()
    names = sorted({m.group()[1:-1].decode() for m in re.finditer(rb"Ldji/[\w/$]+;", d)})
    names = [n for n in names if not SKIP.search(n) and not re.search(r"forbid|unlimit|nfz|unlock", n, re.I)]
    (STR / "dji_classnames.txt").write_text("\n".join(names))
    strs = sorted({m.group().decode() for m in re.finditer(rb"[\x20-\x7e]{4,200}", d)})
    (STR / "dex_strings.txt").write_text("\n".join(strs))
    log(f"dexstrings: {len(names)} dji class names, {len(strs)} strings")


if __name__ == "__main__":
    steps = sys.argv[1:] or ["all"]
    fn = {"unzip": unzip, "manifest": manifest, "jadx": jadx, "strings": strings, "dexstrings": dexstrings}
    for s in (fn if "all" in steps else steps):
        fn[s]()
