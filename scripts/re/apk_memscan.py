#!/usr/bin/env python3
"""Memory-scan dump of a live Android app's decrypted dex (AppGuard-style packers),
generalized from scripts/re/pilot_memscan.py (dji.pilot-specific) to any package name.
Passive /proc/<pid>/mem read only - no code injection, does not touch the live app's
running state.

Confirmed technique (2026-10-24, dji.pilot): a torn/live read of a packer's decrypted
dex region fails the dex checksum but still has a structurally valid header and parses
fine once jadx's checksum check is skipped. The first dji.pilot attempt scanned the
process too early (payload not yet resident) and found nothing; a second attempt with
a fresh memory snapshot (same process, just re-run) recovered thousands of real
classes. If a scan comes back with only packer/framework classes (no real app code),
re-run it rather than concluding the technique doesn't work for that app - see
docs/dji-app-protocol-pipeline.md.

Operator-authorized bypass of app packing/obfuscation (2026-10-24, extending the same
basis recorded in apk_dynamic_unpack.py for dji.go.v4 to any DJI app this is run
against). Requires root (su) on the target device.

Usage:
    python3 -I scripts/re/apk_memscan.py --device <serial> --package <pkg> \
        [--out tmp/apk/<name>_dynamic] [--decompile]

Output (default --out): carved_<pid>_<addr>_<off>.dex, maps_<pid>.txt, and if
--decompile, decompiled/carved_.../ (jadx output, -Pdex-input.verify-checksum=no).
"""
import argparse
import re
import struct
import subprocess
import time
from pathlib import Path


def repo_root() -> Path:
    return Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                                text=True, check=True).stdout.strip())


ROOT = repo_root()
JADX = ROOT / "tmp/tools/jadx/bin/jadx"
DEX_MAGIC_RE = re.compile(rb"dex\n0(3[5-9]|4[0-5])\x00")


def default_out(package: str) -> Path:
    safe = package.replace(".", "_")
    return ROOT / "tmp" / "apk" / f"{safe}_dynamic"


def log(log_path: Path, msg: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    print(line, flush=True)
    with log_path.open("a") as f:
        f.write(line + "\n")


def dex_file_size(data: bytes, off: int):
    """Pure offset arithmetic (dex header field read) - no checksum/signature work,
    which is exactly why this still works on a torn/live-process read that fails the
    real checksum. jadx is run separately with -Pdex-input.verify-checksum=no."""
    if off + 0x70 > len(data):
        return None
    header_size, endian = struct.unpack_from("<II", data, off + 36)
    if header_size != 0x70 or endian != 0x12345678:
        return None
    file_size = struct.unpack_from("<I", data, off + 32)[0]
    if file_size < 0x70 or off + file_size > len(data) + 4096:
        return None
    return file_size


def memscan(device: str, package: str, out: Path, log_path: Path) -> int:
    r = subprocess.run(["adb", "-s", device, "shell", "su", "-c", f"pidof {package}"],
                        capture_output=True, text=True)
    pids = r.stdout.strip().split()
    if not pids:
        raise SystemExit(f"{package} not running on {device} - launch it first "
                          "(and get it past any consent/sign-in flow - see "
                          "docs/dji-app-protocol-pipeline.md)")
    log(log_path, f"target pids: {pids}")
    out.mkdir(parents=True, exist_ok=True)

    carved_count = 0
    for pid in pids:
        maps_path = out / f"maps_{pid}.txt"
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
            if end - start > 64 * 1024 * 1024:  # skip huge heaps; dex stub is a few MB
                continue
            regions.append((start, end))
        log(log_path, f"pid {pid}: {len(regions)} candidate regions")

        for start, end in regions:
            size = end - start
            cmd = ["adb", "-s", device, "exec-out", "su", "-c",
                   f"dd if=/proc/{pid}/mem bs=4096 skip={start // 4096} "
                   f"count={size // 4096} 2>/dev/null"]
            r = subprocess.run(cmd, capture_output=True, check=False)  # binary, no text=True
            data = r.stdout
            offs = [m.start() for m in re.finditer(DEX_MAGIC_RE, data)]
            if not offs:
                continue
            local = out / f"region_{pid}_{start:x}.bin"
            local.write_bytes(data)
            for off in offs:
                fsize = dex_file_size(data, off)
                if fsize is None:
                    continue
                carved = out / f"carved_{pid}_{start:x}_{off:x}.dex"
                carved.write_bytes(data[off:off + min(fsize, len(data) - off)])
                carved_count += 1
                log(log_path, f"carved {carved.name} ({fsize} bytes) from pid {pid} "
                    f"region {start:#x}-{end:#x} at off {off:#x}")

    log(log_path, f"total carved: {carved_count}")
    return carved_count


def decompile(out: Path, log_path: Path) -> None:
    if not JADX.exists():
        raise SystemExit(f"jadx not found at {JADX} - run scripts/re/apk_extract.py first")
    for dex in sorted(out.glob("*.dex")):
        out_dir = out / "decompiled" / dex.stem
        r = subprocess.run(
            [str(JADX), "-Pdex-input.verify-checksum=no", "-d", str(out_dir), str(dex)],
            capture_output=True, text=True,
        )
        log(log_path, f"jadx {dex.name}: rc={r.returncode} "
            f"stdout_tail={r.stdout.strip()[-500:]} stderr_tail={r.stderr.strip()[-500:]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True, help="adb device serial")
    ap.add_argument("--package", required=True, help="Android package name, e.g. dji.go.v4")
    ap.add_argument("--out", type=Path, default=None,
                     help="output dir (default tmp/apk/<package_with_underscores>_dynamic)")
    ap.add_argument("--decompile", action="store_true",
                     help="also run jadx (-Pdex-input.verify-checksum=no) on carved dex files")
    args = ap.parse_args()

    out = args.out or default_out(args.package)
    log_path = ROOT / "tmp" / "logs" / f"apk_memscan_{args.package.replace('.', '_')}.log"
    carved = memscan(args.device, args.package, out, log_path)
    if args.decompile:
        if carved == 0:
            log(log_path, "0 dex carved - skipping decompile, nothing to decompile")
        else:
            decompile(out, log_path)
    print(f"done - see {log_path}")


if __name__ == "__main__":
    main()
