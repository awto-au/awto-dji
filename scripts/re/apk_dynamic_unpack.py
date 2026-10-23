#!/usr/bin/env python3
"""Dynamic unpacking of the DJI GO 4 APK's AppGuard packer, to recover the real dex.

docs/apk-analysis.md established statically that classes.dex is a packer stub (1623
amap/autonavi/AppGuard classes, ~1.8 MB) plus a ~37 MB payload outside the dex tables with
readable dji.* class-name strings but no decompilable bytecode. The payload is decrypted
into process memory at app startup; this script drives that: install -> launch -> dump the
decrypted dex from the live process -> decompile with jadx.

Operator-authorized (unlike the static pass, which deliberately avoided this): "we can
remove appguard - there is no issue". Still in scope per CLAUDE.md: no DJI account login,
no FlySafe/geofence/signature-verify/anti-tamper/crypto-lib ANALYSIS (dumping past them to
reach the dex is fine; reading their logic is not), no credential/key extraction.

This performs live instrumentation of a running process on a real device. The agent/model
that authored this script does not execute its device-mutating steps itself - run it
yourself. Each step is idempotent and safe to re-run; `--step` runs just one.

Fallback chain (first that produces a dex wins):
  1. frida-dexdump   - cleanest; works unless the packer actively detects Frida.
  2. frida script    - manual dalvik.system.DexFile / BaseDexClassLoader walk; survives
                       some anti-Frida checks that only look for the default agent name.
  3. /proc/<pid>/mem scan - no Frida at all; find the dex magic in anonymous RW regions
                       and carve it out. Works even if the packer detects Frida, as long as
                       root (su) access to read another process's memory is available.

CONFIRMED 2026-10-23 against this APK: steps 1 and 2 DO work, but only before the app's
real (post-packer) code executes - attaching frida-dexdump at that point consistently
killed/respawned the target process ("script has been destroyed"), reproducibly, and the
process was stable again as soon as frida-server was killed. This is this packer's
advertised anti-tamper behavior, not a bug here. Step 1 against the cold-start stub (before
the user taps through the consent flow) successfully dumps ~60 dex files, but they are all
stock Android framework classes (android.*, java.*, dalvik.*) loaded by the boot
classloader - the DJI app's own dji.* code is not resident yet at that point. Net result:
for THIS app, step 3 (memscan) is the one that actually recovers DJI code; 1 and 2 are kept
because they may work against the stub, a differently-packed build, or a future unpacking
bypass, but do not assume either will reach the real payload here.

Usage:
    python3 -I scripts/re/apk_dynamic_unpack.py --device <serial> [--step STEP] [--dry-run]

Steps (run in order by default): check, install, frida-server, frida-dexdump,
frida-manual, memscan, decompile, report
Log: tmp/logs/apk_dynamic_unpack.log
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path


def repo_root() -> Path:
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                              capture_output=True, text=True, check=True,
                              cwd=Path(__file__).resolve().parent)
        return Path(out.stdout.strip())
    except Exception:
        return Path(__file__).resolve().parents[2]


ROOT = repo_root()
APK = ROOT / "firmware/apk/dji-go-4_v4.3.64.apk"
OUT = ROOT / "tmp/apk/dynamic"
VENV = ROOT / "tmp/venv-frida"
TOOLS = ROOT / "tmp/tools"
JADX = ROOT / "tmp/tools/jadx/bin/jadx"
LOG = ROOT / "tmp/logs/apk_dynamic_unpack.log"
# Real installed package name (confirmed on-device: `pm list packages`); the APK's own
# directory/activity names (com.dji.go4, dji.pilot.*) suggested otherwise but are wrong.
PKG = "dji.go.v4"
LAUNCHER_ACTIVITY = "dji.pilot.main.activity.DJILauncherActivity"  # confirmed on-device
FRIDA_VERSION = "17.24.3"  # resolved 2026-10-23 via `gh release list -R frida/frida`
DEX_MAGIC = bytes.fromhex("6465780a303335")  # "dex\n035"

FRIDA_SCRIPT = """
Java.perform(function () {
    var seen = {};
    function dump(dexFile, tag) {
        try {
            var cookie = dexFile.mCookie.value;
            var path = dexFile.mFileName ? dexFile.mFileName.value.toString() : tag;
            if (seen[path]) return;
            seen[path] = true;
            send({type: "dex", path: path});
        } catch (e) {}
    }
    var DexFile = Java.use("dalvik.system.DexFile");
    var loaders = Java.enumerateClassLoadersSync();
    loaders.forEach(function (l) {
        try {
            var pathList = Java.cast(l, Java.use("dalvik.system.BaseDexClassLoader"))
                .pathList.value;
            var elements = pathList.dexElements.value;
            for (var i = 0; i < elements.length; i++) {
                var dexFile = elements[i].dexFile.value;
                if (dexFile != null) dump(dexFile, "loader_" + i);
            }
        } catch (e) {}
    });
    send({type: "done"});
});
"""


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def run(cmd, dry_run, check=True, **kw):
    log("$ " + " ".join(str(c) for c in cmd))
    if dry_run:
        log("  (dry-run: not executed)")
        return subprocess.CompletedProcess(cmd, 0, "", "")
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.stdout.strip():
        log(r.stdout.strip()[-2000:])
    if r.stderr.strip():
        log("stderr: " + r.stderr.strip()[-2000:])
    if check and r.returncode != 0:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(str(c) for c in cmd)}")
    return r


def adb(device, *args, dry_run=False, check=True):
    return run(["adb", "-s", device, *args], dry_run, check=check)


def step_check(device, dry_run):
    """Refuse to proceed if DJI GO 4 is already installed (don't touch a real install)."""
    r = adb(device, "shell", "pm", "list", "packages", dry_run=False, check=True)
    if PKG in r.stdout:
        raise SystemExit(f"{PKG} is already installed on {device} - stopping, "
                          "this script does not touch an existing real install")
    r = adb(device, "shell", "su", "-c", "id", dry_run=False, check=False)
    if "uid=0" not in r.stdout:
        raise SystemExit(f"{device} does not have root (su) access - required for "
                          "frida-server and the memory-scan fallback")
    log(f"check: {device} not installed, root ok, abi="
        + adb(device, "shell", "getprop", "ro.product.cpu.abi", dry_run=False).stdout.strip())


def step_install(device, dry_run):
    if not APK.exists():
        raise SystemExit(f"APK not found: {APK}")
    adb(device, "install", str(APK), dry_run=dry_run)


def step_frida_server(device, dry_run):
    """Download the matching frida-server, push it, start it, forward the port."""
    TOOLS.mkdir(parents=True, exist_ok=True)
    abi = adb(device, "shell", "getprop", "ro.product.cpu.abi", dry_run=False).stdout.strip()
    frida_arch = {"arm64-v8a": "android-arm64", "armeabi-v7a": "android-arm"}.get(abi)
    if not frida_arch:
        raise SystemExit(f"unhandled abi {abi!r} - check github.com/frida/frida releases")
    asset = f"frida-server-{FRIDA_VERSION}-{frida_arch}.xz"
    server = TOOLS / asset[:-3]
    if not server.exists():
        run(["gh", "release", "download", FRIDA_VERSION, "-R", "frida/frida",
             "-p", asset, "-D", str(TOOLS)], dry_run)
        run(["xz", "-d", "-f", str(TOOLS / asset)], dry_run)
    run(["chmod", "+x", str(server)], dry_run)
    adb(device, "push", str(server), "/data/local/tmp/frida-server", dry_run=dry_run)
    adb(device, "shell", "su", "-c", "chmod 755 /data/local/tmp/frida-server",
        dry_run=dry_run)
    # backgrounded on-device; nohup survives the adb shell session closing
    adb(device, "shell", "su", "-c",
        "nohup /data/local/tmp/frida-server >/data/local/tmp/frida.log 2>&1 &",
        dry_run=dry_run)
    adb(device, "forward", "tcp:27042", "tcp:27042", dry_run=dry_run)
    if not dry_run:
        time.sleep(2)  # let frida-server bind before the client connects
    log("frida-server pushed and started; local pip install for the client:\n"
        f"  python3 -m venv {VENV}\n"
        f"  {VENV}/bin/pip install frida=={FRIDA_VERSION} frida-tools")


def pip_bin(name):
    return str(VENV / "bin" / name)


def find_standard_cpython():
    """frida ships only a cp37-abi3 (stable-ABI) wheel. That covers any ordinary CPython
    3.7+ but NOT a free-threaded (3.1xt / --disable-gil) build, which breaks the stable
    ABI - pip then falls back to compiling frida from source, which fails without the
    exact build toolchain frida's setup expects. sys.executable is whatever interpreter
    happened to run this script, which may be the free-threaded one, so search explicitly
    for a standard build instead of trusting it."""
    candidates = ["/usr/bin/python3.11", "/usr/bin/python3.12", "/usr/bin/python3.13",
                  "/usr/bin/python3", "python3.11", "python3.12", "python3"]
    for c in candidates:
        exe = c if c.startswith("/") else (
            subprocess.run(["which", c], capture_output=True, text=True).stdout.strip())
        if not exe:
            continue
        r = subprocess.run([exe, "-c", "import sys; print(sys._is_gil_enabled())"],
                            capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip() == "True":
            return exe
        if r.returncode != 0 and "_is_gil_enabled" in r.stderr:
            return exe  # older interpreter with no GIL toggle at all = never free-threaded
    raise SystemExit("no standard (non-free-threaded) CPython 3.7+ found for the frida venv")


def ensure_frida_client(dry_run):
    # frida-tools is a separate package from frida itself and does NOT share its version
    # numbering (frida-tools caps out around 14.x on PyPI while frida core is at 17.x+);
    # only `frida` needs to match the server version, frida-tools just needs frida>=17.10.
    if not (VENV / "bin" / "frida").exists():
        python = find_standard_cpython()
        log(f"using {python} for the frida venv (avoiding any free-threaded build)")
        run([python, "-m", "venv", str(VENV)], dry_run)
        run([pip_bin("pip"), "install", f"frida=={FRIDA_VERSION}", "frida-tools"], dry_run)


def launch_app(device, dry_run):
    adb(device, "shell", "am", "start", "-n", f"{PKG}/{LAUNCHER_ACTIVITY}", dry_run=dry_run)
    if not dry_run:
        time.sleep(4)  # cold-start settle; NOT enough to reach the real (post-packer) dex
    log("NOTE (confirmed 2026-10-23): this app gates its real init behind a first-run "
        "consent flow - Terms of Use -> OS permission request -> DJI 'Information "
        "Authorization' toggles -> Product Improvement Program -> Sign Up/Sign In. The "
        "packer's real payload does not appear to be loaded (no dji.* classes resident) "
        "until past that flow. This script does NOT automate tapping through it (screen "
        "layout/coordinates are not a stable API); drive it manually with "
        "`adb -s <device> exec-out screencap -p > screen.png` + "
        "`adb -s <device> shell input tap X Y`, stop at Sign Up/Sign In (do not log in), "
        "then re-run the dump step. Declining the OS permission request (storage/location) "
        "and 'Product Improvement Program' is fine and does not block reaching that point.")


def step_frida_dexdump(device, dry_run):
    """Fallback 1: frida-dexdump, the clean path."""
    ensure_frida_client(dry_run)
    if not (VENV / "bin" / "frida-dexdump").exists():
        run([pip_bin("pip"), "install", "frida-dexdump"], dry_run)
    launch_app(device, dry_run)
    OUT.mkdir(parents=True, exist_ok=True)
    run([pip_bin("frida-dexdump"), "-U", "-p", PKG], dry_run, check=False, cwd=str(OUT))


def step_frida_manual(device, dry_run):
    """Fallback 2: walk the classloader manually for packers that confuse frida-dexdump."""
    ensure_frida_client(dry_run)
    OUT.mkdir(parents=True, exist_ok=True)
    script_path = OUT / "dump.js"
    if not dry_run:
        script_path.write_text(FRIDA_SCRIPT)
    launch_app(device, dry_run)
    run([pip_bin("frida"), "-U", "-n", "DJI GO 4", "-l", str(script_path),
         "--runtime=v8", "-e", "exit()"], dry_run, check=False)
    log("manual walk only reports dex paths seen by the classloader; cross-reference "
        "against step 'memscan' to actually carve the bytes if this doesn't dump files")


def step_memscan(device, dry_run):
    """Fallback 3: no Frida - scan /proc/<pid>/mem for the dex magic and carve it out."""
    r = adb(device, "shell", "su", "-c", f"pidof {PKG}", dry_run=False, check=False)
    pid = r.stdout.strip().split()[0] if r.stdout.strip() else None
    if not pid:
        launch_app(device, dry_run)
        r = adb(device, "shell", "su", "-c", f"pidof {PKG}", dry_run=False, check=False)
        pid = r.stdout.strip().split()[0] if r.stdout.strip() else None
    if not pid and not dry_run:
        raise SystemExit(f"{PKG} is not running - launch it first")
    log(f"target pid: {pid}")
    maps_path = OUT / "maps.txt"
    OUT.mkdir(parents=True, exist_ok=True)
    r = adb(device, "shell", "su", "-c", f"cat /proc/{pid}/maps", dry_run=False, check=False)
    if not dry_run:
        maps_path.write_text(r.stdout)
    regions = []
    if not dry_run:
        for line in maps_path.read_text().splitlines():
            if "rw-p" not in line:
                continue
            addr_range = line.split()[0]
            start_s, end_s = addr_range.split("-")
            start, end = int(start_s, 16), int(end_s, 16)
            if end - start > 64 * 1024 * 1024:  # skip huge heaps; dex stub is a few MB
                continue
            regions.append((start, end))
    log(f"{len(regions)} candidate rw regions under 64MB to scan")
    hits = []
    for start, end in regions:
        size = end - start
        local = OUT / f"region_{start:x}.bin"
        # dd by byte offset via skip=/count= in 4K blocks, aligned to page boundaries.
        # exec-out (not shell+text capture) is required here: adb shell's stdout capture
        # is not binary-safe (newline/encoding translation corrupts the dump silently).
        cmd = ["adb", "-s", device, "exec-out", "su", "-c",
               f"dd if=/proc/{pid}/mem bs=4096 skip={start // 4096} "
               f"count={size // 4096} 2>/dev/null"]
        log("$ " + " ".join(cmd))
        if dry_run:
            log("  (dry-run: not executed)")
            continue
        r = subprocess.run(cmd, capture_output=True, check=False)  # no text=True: binary
        local.write_bytes(r.stdout)
        data = local.read_bytes()
        off = data.find(DEX_MAGIC)
        if off >= 0:
            hits.append((local, off, start + off))
            log(f"dex magic hit in {local.name} at file offset {off:#x} "
                f"(process addr {start + off:#x})")
        else:
            local.unlink(missing_ok=True)  # keep only the hit(s); regions are large
    if not hits and not dry_run:
        log("no dex magic found in scanned regions - widen the size cutoff above "
            "or check maps.txt by hand for anon regions missed by the rw-p filter")
    for local, off, _ in hits:
        carved = OUT / f"carved_{local.stem}.dex"
        data = local.read_bytes()[off:]
        carved.write_bytes(data)
        log(f"carved {carved} ({len(data)} bytes, file_size field not fixed up - "
            "jadx may still refuse it; truncate to the real size if so)")


def step_decompile(device, dry_run):
    if not JADX.exists():
        raise SystemExit(f"jadx not found at {JADX} - run scripts/re/apk_extract.py first "
                          "(it fetches jadx via gh release download)")
    dex_files = sorted(OUT.glob("*.dex")) + sorted(OUT.glob("**/*.dex"))
    if not dex_files:
        raise SystemExit(f"no .dex files found under {OUT} - run a dump step first")
    for dex in dex_files:
        out_dir = OUT / "decompiled" / dex.stem
        run([str(JADX), "-d", str(out_dir), str(dex)], dry_run, check=False)
    log(f"decompiled output under {OUT / 'decompiled'}")


def step_report(device, dry_run):
    log("Done. Next: grep the decompiled output under "
        f"{OUT / 'decompiled'} for DataConfig CmdSet/CmdId int constants and the AOA "
        "accessory strings (T600/DJI/version), then update docs/apk-analysis.md and "
        "docs/data/apk-duml-commands.tsv by hand (this script does not write those).")


STEPS = [
    ("check", step_check),
    ("install", step_install),
    ("frida-server", step_frida_server),
    ("frida-dexdump", step_frida_dexdump),
    ("frida-manual", step_frida_manual),
    ("memscan", step_memscan),
    ("decompile", step_decompile),
    ("report", step_report),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True, help="adb device serial")
    ap.add_argument("--step", choices=[s for s, _ in STEPS],
                     help="run only this step (default: run all in order)")
    ap.add_argument("--dry-run", action="store_true",
                     help="print every command without touching the device or network")
    args = ap.parse_args()

    names = [args.step] if args.step else [s for s, _ in STEPS]
    for name in names:
        fn = dict(STEPS)[name]
        log(f"=== step: {name} ===")
        fn(args.device, args.dry_run)


if __name__ == "__main__":
    main()
