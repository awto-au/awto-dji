#!/usr/bin/env python3
"""Memory-scan dump of the live dji.pilot process's decrypted dex (AppGuard packer),
same technique as apk_dynamic_unpack.py's step_memscan but targeting dji.pilot instead
of dji.go.v4. Operator-authorized (2026-10-24, same basis as apk_dynamic_unpack.py's own
"we can remove appguard - there is no issue"). Passive /proc/<pid>/mem read only - no
code injection, does not touch the live app's running state.

Usage: python3 -I scripts/re/pilot_memscan.py --device <serial> [--decompile]
Output: tmp/apk/pilot_dynamic/ (carved_*.dex, decompiled/)
"""
import argparse
import re
import struct
import subprocess
import time
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                            text=True, check=True).stdout.strip())
OUT = ROOT / "tmp/apk/pilot_dynamic"
JADX = ROOT / "tmp/tools/jadx/bin/jadx"
LOG = ROOT / "tmp/logs/pilot_memscan.log"
PKG = "dji.pilot"
DEX_MAGIC_RE = re.compile(rb"dex\n0(3[5-9]|4[0-5])\x00")


def log(msg):
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def dex_file_size(data, off):
    if off + 0x70 > len(data):
        return None
    header_size, endian = struct.unpack_from("<II", data, off + 36)
    if header_size != 0x70 or endian != 0x12345678:
        return None
    file_size = struct.unpack_from("<I", data, off + 32)[0]
    if file_size < 0x70 or off + file_size > len(data) + 4096:
        return None
    return file_size


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--device", required=True)
    ap.add_argument("--decompile", action="store_true")
    args = ap.parse_args()
    device = args.device
    OUT.mkdir(parents=True, exist_ok=True)

    r = subprocess.run(["adb", "-s", device, "shell", "su", "-c", f"pidof {PKG}"],
                        capture_output=True, text=True)
    pids = r.stdout.strip().split()
    if not pids:
        raise SystemExit(f"{PKG} not running")
    log(f"target pids: {pids}")

    carved_count = 0
    for pid in pids:
        maps_path = OUT / f"maps_{pid}.txt"
        r = subprocess.run(["adb", "-s", device, "shell", "su", "-c", f"cat /proc/{pid}/maps"],
                            capture_output=True, text=True)
        maps_path.write_text(r.stdout)
        regions = []
        for line in r.stdout.splitlines():
            parts = line.split()
            if len(parts) < 2:
                continue
            perms = parts[1]
            if not (perms.startswith("rw-p") or perms.startswith("r-xp")
                    or perms.startswith("r--p")):
                continue
            start_s, end_s = parts[0].split("-")
            start, end = int(start_s, 16), int(end_s, 16)
            if end - start > 64 * 1024 * 1024:
                continue
            regions.append((start, end))
        log(f"pid {pid}: {len(regions)} candidate regions")

        for start, end in regions:
            size = end - start
            cmd = ["adb", "-s", device, "exec-out", "su", "-c",
                   f"dd if=/proc/{pid}/mem bs=4096 skip={start // 4096} "
                   f"count={size // 4096} 2>/dev/null"]
            r = subprocess.run(cmd, capture_output=True, check=False)
            data = r.stdout
            offs = [m.start() for m in re.finditer(DEX_MAGIC_RE, data)]
            if not offs:
                continue
            for off in offs:
                fsize = dex_file_size(data, off)
                if fsize is None:
                    continue
                carved = OUT / f"carved_{pid}_{start:x}_{off:x}.dex"
                carved.write_bytes(data[off:off + min(fsize, len(data) - off)])
                carved_count += 1
                log(f"carved {carved.name} ({fsize} bytes) from pid {pid} "
                    f"region {start:#x}-{end:#x} at off {off:#x}")

    log(f"total carved: {carved_count}")

    if args.decompile:
        if not JADX.exists():
            raise SystemExit(f"jadx not found at {JADX}")
        for dex in sorted(OUT.glob("*.dex")):
            out_dir = OUT / "decompiled" / dex.stem
            r = subprocess.run([str(JADX), "-d", str(out_dir), str(dex)],
                                capture_output=True, text=True)
            log(f"jadx {dex.name}: rc={r.returncode} "
                f"stdout_tail={r.stdout.strip()[-500:]} stderr_tail={r.stderr.strip()[-500:]}")


if __name__ == "__main__":
    main()
