#!/usr/bin/env python3
"""dev.py — canonical entry point for <PROJECT> (awto dev.py convention).

AI agents: run `./dev.py describe` for machine-readable JSON help.
Humans: run `./dev.py --help`.

All output is timestamped in LOCAL time and mirrored to ./tmp/logs/dev.log.

Scaffold usage:
    cp awto-dan/dev.py-template/dev.py  <repo>/dev.py
    cp awto-dan/dev.py-template/test_dev.py <repo>/tests/
    - set PROJECT below
    - edit the STEPS table; that is the ONLY place build/test commands live

Everything else (help, describe, gate, ci, logging, exit codes) is generic
and should not need editing.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

PROJECT = "awto-dji"


def _repo_root() -> Path:
    """Three-tier resolution (awto-dan#35): env override, git toplevel,
    file-relative. Works at <repo>/dev.py AND <repo>/scripts/dev.py.
    Never VSCODE_CWD — that is the launch directory, not the workspace."""
    env = os.environ.get(f"{PROJECT.upper().replace('-', '_')}_REPO")
    if env:
        p = Path(env).expanduser().resolve()
        if p.is_dir():
            return p
    here = Path(__file__).resolve().parent
    try:
        # local .git read, ~1 ms warm; 0.25 s covers a cold first exec.
        # On expiry/absence: file-relative fallback below.
        out = subprocess.run(["git", "-C", str(here), "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, timeout=0.25)
        if out.returncode == 0 and out.stdout.strip():
            return Path(out.stdout.strip()).resolve()
    except (OSError, subprocess.SubprocessError):
        pass
    return here.parent if here.name == "scripts" else here


REPO = _repo_root()
TMP = REPO / "tmp"           # scratch, pidfiles
LOGS = TMP / "logs"          # logs, per the ./tmp/logs/ rule
LOG = LOGS / "dev.log"

# --------------------------------------------------------------------------
# STEPS — the only project-specific part.
#
# Each entry: command name -> (summary, argv, accepts_extra_args)
# argv of [] means "not configured for this project"; such a step SKIPS
# rather than fails, so a fresh scaffold runs green before you fill it in.
# Swap for your build system: cargo / pytest / west / npm / make ...
# --------------------------------------------------------------------------
# Ships UNCONFIGURED ([]) so a fresh copy runs green immediately: every step
# SKIPs, `ci` reports GO with skips listed, and you fill them in one at a time
# and watch each go from SKIP to ok. Replace [] with the real argv.
#
#   Rust    build ["cargo","build"]   test ["cargo","test","--workspace"]
#           lint  ["cargo","clippy","--all-targets"]   fmt ["cargo","fmt"]
#   Python  test  [sys.executable,"-m","pytest","-q"]  lint ["ruff","check","."]
#   Zephyr  build ["west","build"]     test ["west","build","-t","run_tests"]
# dart analyze/format take paths; dart test must run inside each package (no
# pubspec at repo root), hence _DART_TEST_EACH. geofence has no test/ dir yet.
DART_PKGS = ["app/packages/duml", "app/packages/geofence"]
DART_TEST_PKGS = ["app/packages/duml"]

# Runs `dart test <args>` in each package, returns first nonzero rc.
# Exits 125 (SKIPPED) when dart is absent, matching the template's skip contract.
_DART_TEST_EACH = (
    "import shutil, subprocess, sys\n"
    "if not shutil.which('dart'):\n"
    "    sys.exit(125)\n"
    f"pkgs = {DART_TEST_PKGS!r}\n"
    "rcs = [subprocess.call(['dart', 'test', *sys.argv[1:]], cwd=p) for p in pkgs]\n"
    "sys.exit(next((rc for rc in rcs if rc), 0))\n"
)

STEPS: dict[str, tuple[str, list[str], bool]] = {
    "build":     ("compile the project",          [], True),
    "test":      ("run the test suite",           [sys.executable, "-c", _DART_TEST_EACH], True),
    "lint":      ("static analysis",              ["dart", "analyze", *DART_PKGS], True),
    "fmt-check": ("formatting check (no writes)", ["dart", "format", "--output=none",
                                                   "--set-exit-if-changed", *DART_PKGS], False),
    "fmt":       ("reformat in place",            ["dart", "format", *DART_PKGS], False),
    "run":       ("build + execute",              [], True),
}

# gate = fail-fast, blocks a commit. First failure wins; fix that.
GATE = ["fmt-check", "lint", "test", "build"]
# ci = run-all-collect-all. Every leg runs even after a failure, then ONE
# GO/NO-GO. On hardware a re-run costs minutes and may not reproduce.
CI = ["fmt-check", "lint", "test", "build"]

# --------------------------------------------------------------------------
# Logging — Tier A (dev tooling): local time, stderr + ./tmp/logs/dev.log,
# colour on TTY only, file copy always plain.
# --------------------------------------------------------------------------
_COLOR = {
    "FATAL": "\033[1;91m", "ERROR": "\033[31m", "WARN": "\033[33m",
    "INFO": "\033[97m", "DEBUG": "\033[94m", "ALERT": "\033[92m",
}
_RESET = "\033[0m"
_USE_COLOR = (
    sys.stderr.isatty()
    and not os.environ.get("NO_COLOR")
    and os.environ.get("CLICOLOR") != "0"
)


def _stamp() -> str:
    # Local zone incl. DST (AEST +1000 / AEDT +1100). Never hardcode the
    # offset and never use UTC here: a human reads these live.
    return datetime.now().astimezone().strftime("%H:%M:%S.%f%z")


def log(msg: str, level: str = "INFO") -> None:
    line = f"{_stamp()}  {level:<5} [dev.py] {msg}"
    if _USE_COLOR:
        sys.stderr.write(f"{_COLOR.get(level, '')}{line}{_RESET}\n")
    else:
        sys.stderr.write(line + "\n")
    sys.stderr.flush()
    try:
        LOGS.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")          # file copy is ALWAYS plain
    except OSError:
        pass                                # never let logging kill the run


SKIPPED = 125   # distinct from any real tool's exit code


def run_step(name: str, extra: list[str] | None = None) -> int:
    """Run one STEPS entry. Returns its exit code, or SKIPPED."""
    summary, argv, takes_extra = STEPS[name]
    if not argv:
        log(f"{name}: not configured for this project - skipped", "WARN")
        return SKIPPED
    if not shutil.which(argv[0]) and argv[0] != sys.executable:
        log(f"{name}: {argv[0]} not on PATH - skipped", "WARN")
        return SKIPPED
    cmd = argv + (list(extra) if (extra and takes_extra) else [])
    log("run: " + " ".join(cmd))
    rc = subprocess.call(cmd, cwd=REPO)
    log(f"rc={rc}: " + " ".join(cmd), "INFO" if rc == 0 else "ERROR")
    return rc


# --------------------------------------------------------------------------
# Command registry — ONE source of truth. The decorator populates the table
# that drives dispatch, --help AND describe, so they cannot drift apart.
# --------------------------------------------------------------------------
COMMANDS: dict[str, dict] = {}


def command(summary: str, *, args: str = "", kind: str = "action"):
    def deco(fn):
        COMMANDS[fn.__name__.replace("cmd_", "").replace("_", "-")] = {
            "summary": summary, "args": args, "kind": kind, "fn": fn,
        }
        return fn
    return deco


@command("machine-readable command list (JSON, for AI agents)", kind="meta")
def cmd_describe(_extra: list[str]) -> int:
    print(json.dumps({
        "project": PROJECT,
        "schema": 1,
        "entrypoint": "./dev.py",
        "log": str(LOG.relative_to(REPO)),
        "exit_codes": {"0": "success", "2": "usage error",
                       "125": "step skipped (tool absent)", "other": "failure"},
        "commands": {
            name: {k: v for k, v in meta.items() if k != "fn"}
            for name, meta in COMMANDS.items()
        },
    }, indent=2))
    return 0


@command("check the toolchain is present; run this first when stuck", kind="meta")
def cmd_doctor(_extra: list[str]) -> int:
    log(f"project    : {PROJECT}")
    log(f"python     : {sys.version.split()[0]} ({sys.executable})")
    log(f"gil        : {'disabled (free-threaded)' if not sys._is_gil_enabled() else 'enabled'}"
        if hasattr(sys, "_is_gil_enabled") else "gil        : n/a (<3.13)")
    missing = []
    for name, (_s, argv, _e) in STEPS.items():
        if not argv:
            log(f"{name:10s} : not configured", "WARN")
        elif argv[0] == sys.executable or shutil.which(argv[0]):
            log(f"{name:10s} : {argv[0]} ok")
        else:
            log(f"{name:10s} : {argv[0]} MISSING", "ERROR")
            missing.append(argv[0])
    if missing:
        log(f"missing tools: {', '.join(sorted(set(missing)))}", "ERROR")
        return 1
    log("doctor ok", "ALERT")
    return 0


@command("remove build output and logs", kind="action")
def cmd_clean(_extra: list[str]) -> int:
    for path in (TMP,):
        if path.exists():
            shutil.rmtree(path)
            log(f"removed {path.relative_to(REPO)}")
    return 0


@command("fail-fast pre-commit gate: " + " + ".join(GATE), kind="aggregate")
def cmd_gate(_extra: list[str]) -> int:
    for name in GATE:
        rc = run_step(name)
        if rc not in (0, SKIPPED):
            log(f"GATE FAILED at {name} (rc={rc})", "FATAL")
            return rc
    log("GATE PASSED", "ALERT")
    return 0


@command("run every leg, collect all results, one GO/NO-GO", kind="aggregate")
def cmd_ci(_extra: list[str]) -> int:
    results: dict[str, int] = {}
    for name in CI:
        results[name] = run_step(name)          # no early exit - that is the point
    failed = {k: v for k, v in results.items() if v not in (0, SKIPPED)}
    skipped = [k for k, v in results.items() if v == SKIPPED]
    log("-" * 52)
    for name, rc in results.items():
        state = "SKIP" if rc == SKIPPED else ("ok" if rc == 0 else f"FAIL rc={rc}")
        log(f"  {name:12s} {state}", "INFO" if rc in (0, SKIPPED) else "ERROR")
    if skipped:
        log(f"{len(skipped)} step(s) skipped: {', '.join(skipped)}", "WARN")
    if failed:
        log(f"NO-GO - {len(failed)} of {len(results)} failed: {', '.join(failed)}", "FATAL")
        return 1
    log("GO", "ALERT")
    return 0


@command("verify dev.py's own contract (help/describe/exit codes)", kind="meta")
def cmd_selftest(_extra: list[str]) -> int:
    failures = []

    def check(label: str, cond: bool) -> None:
        log(f"  {label}: {'ok' if cond else 'FAIL'}", "INFO" if cond else "ERROR")
        if not cond:
            failures.append(label)

    out = subprocess.run([sys.executable, __file__, "describe"],
                         capture_output=True, text=True, cwd=REPO)
    check("describe exits 0", out.returncode == 0)
    try:
        doc = json.loads(out.stdout)
        check("describe emits valid JSON", True)
        check("describe has project+commands", {"project", "commands"} <= doc.keys())
        check("every command documented", all(
            m.get("summary") for m in doc.get("commands", {}).values()))
    except json.JSONDecodeError:
        check("describe emits valid JSON", False)

    h = subprocess.run([sys.executable, __file__, "--help"],
                       capture_output=True, text=True, cwd=REPO)
    check("--help exits 2 (usage)", h.returncode == 2)
    check("--help lists commands", all(c in h.stdout for c in COMMANDS))

    u = subprocess.run([sys.executable, __file__, "no-such-command"],
                       capture_output=True, text=True, cwd=REPO)
    check("unknown command exits 2", u.returncode == 2)

    check("registry has no duplicate handlers",
          len({m["fn"] for m in COMMANDS.values()}) == len(COMMANDS))

    if failures:
        log(f"selftest FAILED: {', '.join(failures)}", "FATAL")
        return 1
    log("selftest ok", "ALERT")
    return 0


def _register_steps() -> None:
    """Expose each STEPS entry as a first-class command."""
    for name, (summary, _argv, takes_extra) in STEPS.items():
        if name in COMMANDS:
            continue
        COMMANDS[name] = {
            "summary": summary,
            "args": "[extra args passed through]" if takes_extra else "",
            "kind": "step",
            "fn": (lambda n: lambda extra: run_step(n, extra))(name),
        }


_register_steps()


def _tool(script: str, summary: str) -> dict:
    """Command that runs one repo script with the user's extra args."""
    def fn(extra: list[str]) -> int:
        cmd = [sys.executable, str(REPO / script), *extra]
        log(f"tool: {script} {' '.join(extra)}".rstrip())
        rc = subprocess.call(cmd, cwd=REPO)
        log(f"rc={rc}: {script}", "INFO" if rc == 0 else "ERROR")
        return rc
    return {"summary": summary, "args": "[args passed to the script]",
            "kind": "action", "fn": fn}


# Diagnostics and bench tools a human reaches for (see docs/known-telemetry-and-commands.md).
# Each runs the script as-is; `./dev.py <cmd> --help` shows its own options.
COMMANDS.update({
    "duml-probe":     _tool("scripts/duml_probe.py", "probe the aircraft over DUML (identity/version)"),
    "probe-fc-usb":   _tool("scripts/probe_fc_usb.py", "probe the flight controller USB port"),
    "pcap-decode":    _tool("scripts/pcap_decode.py", "decode a USB pcap capture"),
    "fetch-firmware": _tool("scripts/fetch_firmware.py", "fetch DJI firmware images from a tools CSV"),
    "duml-pretty":    _tool("scripts/re/duml_pretty.py", "pretty-print live DUML frames"),
    "duml-watch":     _tool("scripts/re/duml_watch.py", "watch and log live DUML traffic"),
    "duml-cli":       _tool("scripts/re/duml_cli.py", "send a named DUML command from the catalog"),
    "verify":         _tool("scripts/re/verify.py", "closed-loop command verify via telemetry push"),
    "fw-check":       _tool("scripts/re/fw_version_check.py", "GetVersion every board, flag vs latest known"),
    "gimbal":         _tool("scripts/re/gimbal.py", "one-shot gimbal angle move via AOA proxy"),
    "gimbal-sweep":   _tool("scripts/re/gimbal_sweep.py", "gimbal left/right sweep via AOA proxy"),
    "aoa-relay":      _tool("scripts/re/aoa_relay_server.py", "run the phone AOA relay server"),
    "aoa-send":       _tool("scripts/re/aoa_send.py", "send one raw DUML frame via the AOA relay"),
    "get-identity":   _tool("scripts/re/get_identity.py", "query aircraft identity fields"),
    "usb-inventory":  _tool("scripts/re/usb_inventory.py", "snapshot DJI and USB-UART devices from sysfs"),
    "phone":          _tool("scripts/re/phone_bench.py", "phone/RC bench ops: connect/stop/usb-state/send/trace"),
    "keepalive":      _tool("scripts/re/keepalive.py", "PC-side periodic Get* sends to stop the RC idle-timing-out"),
    "dji-pilot":      _tool("scripts/re/dji_pilot_bench.py", "drive DJI Pilot (reference app): select-aircraft/connect/screenshot"),
})


# --------------------------------------------------------------------------
# Phone / bench-app commands (docs/phone-bridge-operator-guide.md).
# All APK and phone work goes through these; every external argv is logged.
# Tests replace _exec / _spawn with a fake that records argv.
# --------------------------------------------------------------------------
PKG_DJI = "au.awto.dji.awto_dji_app"
PKG_BENCH = "au.awto.aoabench"
PKG_OLD_BENCH = "au.awto.dji.awto_dji_app.aoabench"   # superseded id, removed by `unload --old-bench`
ACTIVITY = "au.awto.dji.awto_dji_app.MainActivity"    # namespace/classes are shared by all three ids
BENCH_ACTION = "au.awto.dji.action.BENCH"
PACKAGES = {"dji": PKG_DJI, "bench": PKG_BENCH, "old-bench": PKG_OLD_BENCH}
APP_DIR = REPO / "app" / "awto_dji_app"
APK_OUT = APP_DIR / "build" / "app" / "outputs" / "flutter-apk" / "app-debug.apk"
APK_DIR = TMP / "apk"
BENCH_HOST_PY = "scripts/re/bench_host.py"
BENCH_HOST_LOG = LOGS / "bench_host.log"   # written by bench_host.py; `connect` watches it
DEFAULT_PORT = 9910

# Bounds. LAN adb calls answer in <1 s; 15 s = stall (matches phone_usb_dialog.ADB_TIMEOUT_S).
ADB_STALL_S = 15
# Build: no output for 120 s = gradle hung (owner rule). Overall is a backstop only: no cold
# build has been timed on this box, so 1800 s is a guess, not 3x a measurement.
BUILD_STALL_S, BUILD_OVERALL_S = 120, 1800
# Install: streamed push of a ~100 MB debug APK over wifi adb prints nothing meanwhile.
INSTALL_STALL_S, INSTALL_OVERALL_S = 90, 300
# connect -> first STATE line: cold Flutter start ~5 s + one 1 s reconnect backoff + 2 s
# margin = 8 s expected worst, x1.25 = 10 s. Expiry prints the logcat tail.
CONNECT_WAIT_S = 10


class ExecResult:
    def __init__(self, rc: int, out: str = "", reason: str = ""):
        self.rc, self.out, self.reason = rc, out, reason


def _exec(argv: list[str], *, why: str, stall_s: float | None = None,
          overall_s: float | None = None, env: dict | None = None, cwd=None,
          tee: Path | None = None, echo: bool = False) -> ExecResult:
    """Run argv, log it, kill on stall (no output for stall_s) or overall expiry.
    stall_s/overall_s None = unbounded, only for foreground tools that run until ^C."""
    log(f"exec: {' '.join(argv)}  [{why}; stall={stall_s}s overall={overall_s}s]")
    full_env = None
    if env is not None:
        full_env = dict(os.environ)
        for k, v in env.items():
            if v is None:
                full_env.pop(k, None)
            else:
                full_env[k] = v
    try:
        p = subprocess.Popen(argv, cwd=cwd or REPO, env=full_env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, bufsize=0)
    except OSError as e:
        log(f"exec failed to start: {e}", "ERROR")
        return ExecResult(127, "", f"cannot start: {e}")
    chunks: list[bytes] = []
    state = {"last": time.monotonic()}
    fh = None
    if tee is not None:
        tee.parent.mkdir(parents=True, exist_ok=True)
        fh = tee.open("ab")

    def pump():
        assert p.stdout is not None
        while True:
            b = os.read(p.stdout.fileno(), 65536)
            if not b:
                return
            state["last"] = time.monotonic()
            chunks.append(b)
            if fh:
                fh.write(b)
                fh.flush()
            if echo:
                sys.stdout.write(b.decode("utf-8", "replace"))
                sys.stdout.flush()

    t = threading.Thread(target=pump, daemon=True)
    t.start()
    t0 = time.monotonic()
    reason = ""
    try:
        while True:
            try:
                p.wait(0.5)
                break
            except subprocess.TimeoutExpired:
                now = time.monotonic()
                if stall_s is not None and now - state["last"] > stall_s:
                    reason = f"stall: no output for {stall_s}s ({why})"
                elif overall_s is not None and now - t0 > overall_s:
                    reason = f"overall limit {overall_s}s exceeded ({why})"
                if reason:
                    p.kill()
                    p.wait()
                    break
    except KeyboardInterrupt:
        p.terminate()
        p.wait()
        reason = "interrupted"
    t.join(2)
    if fh:
        fh.close()
    out = b"".join(chunks).decode("utf-8", "replace")
    rc = p.returncode if not reason or reason == "interrupted" else -9
    if reason:
        tail = out.strip().splitlines()[-1:] or ["<no output>"]
        la = os.getloadavg()[0] if hasattr(os, "getloadavg") else -1
        log(f"{reason}; elapsed {time.monotonic() - t0:.1f}s; last line: {tail[0]!r}; "
            f"loadavg {la:.2f}", "ERROR")
    else:
        log(f"rc={rc}: {argv[0]}", "INFO" if rc == 0 else "ERROR")
    return ExecResult(rc, out, reason)


def _spawn(argv: list[str], *, why: str):
    """Start a long-lived child (the background listener); caller owns its lifetime."""
    log(f"spawn: {' '.join(argv)}  [{why}]")
    return subprocess.Popen(argv, cwd=REPO)


def _parser(prog: str, summary: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog=f"./dev.py {prog}", description=summary)
    return ap


def _parse(ap: argparse.ArgumentParser, extra: list[str], known_only=False):
    try:
        if known_only:
            return ap.parse_known_args(extra)
        return ap.parse_args(extra), []
    except SystemExit as e:
        raise _Usage(int(e.code or 0)) from None


class _Usage(Exception):
    def __init__(self, rc: int):
        self.rc = rc


def _guarded(fn):
    def inner(extra: list[str]) -> int:
        try:
            return fn(extra)
        except _Usage as u:
            return u.rc
    inner.__name__ = fn.__name__
    inner.__doc__ = fn.__doc__
    return inner


# ---- adb / phone resolution ------------------------------------------------
_WIRELESS = re.compile(r"^(\d{1,3}(\.\d{1,3}){3}:\d+|adb-.*_adb-tls-connect\._tcp.*)$")


def parse_devices(text: str) -> list[dict]:
    """`adb devices -l` -> [{serial,state,model,wireless}]; header/daemon noise skipped."""
    devs = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2 or line.startswith(("List of", "*")):
            continue
        model = next((p.split(":", 1)[1] for p in parts[2:] if p.startswith("model:")), "")
        devs.append({"serial": parts[0], "state": parts[1], "model": model,
                     "wireless": bool(_WIRELESS.match(parts[0]))})
    return devs


class PhoneError(Exception):
    pass


def pick_serial(serial: str | None, env_serial: str | None, devices: list[dict]) -> str:
    """--serial, else $AWTO_PHONE, else the single usable device. Several (or none) raises.
    A phone listed twice (USB + wireless, same model) resolves to the wireless entry."""
    if serial:
        return serial
    if env_serial:
        return env_serial
    ok = [d for d in devices if d["state"] == "device"]
    if len(ok) == 1:
        return ok[0]["serial"]
    if len(ok) > 1 and len({d["model"] for d in ok}) == 1:
        wl = [d for d in ok if d["wireless"]]
        if len(wl) == 1:
            return wl[0]["serial"]
    listing = "\n".join(f"  {d['serial']}  {d['state']}  {d['model']}"
                        f"{'  (wireless)' if d['wireless'] else ''}" for d in devices) or "  (none)"
    raise PhoneError(
        ("no usable adb device" if not ok else f"{len(ok)} adb devices, cannot choose") +
        f":\n{listing}\nPass --serial S or set AWTO_PHONE, or --connect IP:PORT "
        "(Settings -> Developer options -> Wireless debugging shows the current IP:port; "
        "it changes on every reboot).")


def _adb(serial: str | None, *args: str, why: str, stall_s=ADB_STALL_S,
         overall_s=None, **kw) -> ExecResult:
    argv = ["adb"] + (["-s", serial] if serial else []) + list(args)
    return _exec(argv, why=why, stall_s=stall_s, overall_s=overall_s or stall_s * 2, **kw)


def adb_devices() -> list[dict]:
    return parse_devices(_adb(None, "devices", "-l", why="list adb devices").out)


def resolve_serial(serial: str | None = None, connect: str | None = None) -> str:
    if connect:
        r = _adb(None, "connect", connect, why="adb connect (wireless port changes per reboot)")
        log(f"adb connect: {r.out.strip()}")
        if r.rc != 0 or "connected" not in r.out or "cannot" in r.out or "failed" in r.out:
            raise PhoneError(f"adb connect {connect} failed: {r.out.strip() or r.reason}")
        serial = serial or connect
    s = pick_serial(serial, os.environ.get("AWTO_PHONE"), [] if serial or
                    os.environ.get("AWTO_PHONE") else adb_devices())
    return s


def installed_packages(serial: str) -> dict[str, bool]:
    out = _adb(serial, "shell", "pm", "list", "packages", why="installed packages").out
    have = {ln.strip().removeprefix("package:") for ln in out.splitlines()}
    return {name: pkg in have for name, pkg in PACKAGES.items()}


def _getprop(serial: str, prop: str) -> str:
    return _adb(serial, "shell", "getprop", prop, why=f"getprop {prop}").out.strip()


def _need_tool(*names: str) -> None:
    missing = [n for n in names if not shutil.which(n)]
    if missing:
        raise PhoneError(f"{', '.join(missing)} not on PATH - install it or fix PATH, then retry")


@command("find the test phone: --serial / $AWTO_PHONE / the one adb device; shows model, "
         "Android, which of dji|bench|old-bench are installed",
         args="[--serial S] [--connect IP:PORT]")
@_guarded
def cmd_phone_connect(extra: list[str]) -> int:
    ap = _parser("phone-connect", "resolve the test phone")
    ap.add_argument("--serial")
    ap.add_argument("--connect", metavar="IP:PORT")
    a, _ = _parse(ap, extra)
    try:
        _need_tool("adb")
        serial = resolve_serial(a.serial, a.connect)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    log(f"serial  : {serial}")
    log(f"model   : {_getprop(serial, 'ro.product.model')}")
    log(f"android : {_getprop(serial, 'ro.build.version.release')}")
    for name, present in installed_packages(serial).items():
        log(f"package {name:9s} {PACKAGES[name]}: {'installed' if present else 'not installed'}")
    print(serial)
    return 0


# ---- load / unload ----------------------------------------------------------
BUILDS = {
    # name -> (package, env for the build, argv)
    "bench": (PKG_BENCH, {"AWTO_BENCH": "1"},
              ["flutter", "build", "apk", "--debug", "--dart-define=BENCH=true"]),
    "dji": (PKG_DJI, {"AWTO_BENCH": None},        # None = removed from the environment
            ["flutter", "build", "apk", "--debug"]),
}


def apk_copy(name: str) -> Path:
    return APK_DIR / f"{name}-debug.apk"


def build_apk(name: str) -> Path:
    """Build one flavour and copy the output aside (the next build overwrites it)."""
    _pkg, env, argv = BUILDS[name]
    r = _exec(argv, why=f"flutter build ({name})", stall_s=BUILD_STALL_S,
              overall_s=BUILD_OVERALL_S, env=env, cwd=APP_DIR,
              tee=LOGS / f"build-{name}.log")
    if r.rc != 0:
        raise PhoneError(f"{name} build failed (rc={r.rc}) {r.reason}; see tmp/logs/build-{name}.log")
    if not APK_OUT.is_file():
        raise PhoneError(f"build reported success but {APK_OUT} is missing")
    APK_DIR.mkdir(parents=True, exist_ok=True)
    dst = apk_copy(name)
    shutil.copyfile(APK_OUT, dst)
    return dst


def install_apk(serial: str, name: str, apk: Path) -> None:
    pkg = BUILDS[name][0]
    log(f"apk {name}: {apk} ({apk.stat().st_size / 1e6:.1f} MB)")
    r = _adb(serial, "install", "-r", str(apk), why=f"install {name}",
             stall_s=INSTALL_STALL_S, overall_s=INSTALL_OVERALL_S)
    if r.rc != 0 or "Success" not in r.out:
        raise PhoneError(f"adb install {name} failed: {r.out.strip() or r.reason}")
    if not installed_packages(serial)[name]:
        raise PhoneError(f"installed {apk.name} but package {pkg} is not on the phone "
                         "(applicationId mismatch?)")
    log(f"installed {pkg}", "ALERT")


def load(serial: str, which: list[str], build: bool = True) -> None:
    _need_tool("adb", *(["flutter"] if build else []))
    for name in which:
        if build:
            apk = build_apk(name)
        else:
            apk = apk_copy(name)
            if not apk.is_file():
                raise PhoneError(f"--no-build but {apk} does not exist; run `./dev.py load` first")
        install_apk(serial, name, apk)


@command("build and install the bench (default) and/or DJI app; --both keeps each APK aside",
         args="[--bench|--dji|--both] [--no-build] [--serial S]")
@_guarded
def cmd_load(extra: list[str]) -> int:
    ap = _parser("load", "build and install")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--bench", action="store_true")
    g.add_argument("--dji", action="store_true")
    g.add_argument("--both", action="store_true")
    ap.add_argument("--no-build", action="store_true", help="install the copies in tmp/apk/")
    ap.add_argument("--serial")
    a, _ = _parse(ap, extra)
    which = ["bench", "dji"] if a.both else ["dji"] if a.dji else ["bench"]
    try:
        _need_tool("adb", *(["flutter"] if not a.no_build else []))
        serial = resolve_serial(a.serial)
        load(serial, which, build=not a.no_build)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    return 0


@command("uninstall the bench, DJI or superseded old-bench package",
         args="[--bench|--dji|--old-bench] [--serial S]")
@_guarded
def cmd_unload(extra: list[str]) -> int:
    ap = _parser("unload", "adb uninstall")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--bench", action="store_true")
    g.add_argument("--dji", action="store_true")
    g.add_argument("--old-bench", action="store_true",
                   help=f"remove the superseded id {PKG_OLD_BENCH}")
    ap.add_argument("--serial")
    a, _ = _parse(ap, extra)
    pkg = PKG_OLD_BENCH if a.old_bench else PKG_DJI if a.dji else PKG_BENCH
    try:
        _need_tool("adb")
        serial = resolve_serial(a.serial)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    r = _adb(serial, "uninstall", pkg, why=f"uninstall {pkg}")
    log(f"adb uninstall {pkg}: {r.out.strip()}")
    return 0 if r.rc == 0 and "Success" in r.out else 1


# ---- listen / connect / grant ----------------------------------------------
def port_in_use(port: int) -> bool:
    """True if something already listens on port (bind probe, same wildcard bench_host uses)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
        except OSError:
            return True
    return False


def port_holder(port: int) -> str:
    r = _exec(["ss", "-ltnp", f"sport = :{port}"], why="who holds the port",
              stall_s=5, overall_s=10)
    return r.out.strip() or "(ss shows no listener; may be another user's process)"


def refuse_if_busy(port: int) -> None:
    if port_in_use(port):
        raise PhoneError(f"port {port} is already in use (a listener is probably running):\n"
                         f"{port_holder(port)}\nStop it, or pick another --port.")


def bench_host_argv(*args: str) -> list[str]:
    return [sys.executable, "-I", BENCH_HOST_PY, *args]


@command("run the bench host listener (scripts/re/bench_host.py) in the foreground",
         args="[--port 9910] [--tail]")
@_guarded
def cmd_listen(extra: list[str]) -> int:
    ap = _parser("listen", "foreground bench listener")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--tail", action="store_true",
                    help="accepted for symmetry; always on, a listener without it exits at once")
    a, _ = _parse(ap, extra)
    try:
        refuse_if_busy(a.port)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    # unbounded by design: a listener runs until ^C; bench_host bounds its own waits
    return _exec(bench_host_argv("--listen", str(a.port), "--tail"), why="foreground listener",
                 echo=True).rc


def route_src(dest_ip: str) -> str:
    """Local IPv4 that routes to dest_ip, from `ip route get`."""
    r = _exec(["ip", "-4", "route", "get", dest_ip], why="local address toward the phone",
              stall_s=5, overall_s=10)
    m = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", r.out)
    if r.rc != 0 or not m:
        raise PhoneError(f"cannot derive the local address toward {dest_ip}: {r.out.strip()}; "
                         "pass --host")
    return m.group(1)


def phone_ip(serial: str) -> str:
    m = re.match(r"^(\d+\.\d+\.\d+\.\d+):\d+$", serial)
    if m:
        return m.group(1)
    # USB serial: ask the phone for the source address of its default route
    r = _adb(serial, "shell", "ip", "-4", "route", "get", "1.1.1.1", why="phone wifi address")
    m = re.search(r"\bsrc\s+(\d+\.\d+\.\d+\.\d+)", r.out)
    if not m:
        raise PhoneError("cannot find the phone's wifi address; pass --host")
    return m.group(1)


def am_start_argv(serial: str, pkg: str, host: str, port: int) -> list[str]:
    return ["adb", "-s", serial, "shell", "am", "start", "-n", f"{pkg}/{ACTIVITY}",
            "-a", BENCH_ACTION, "--es", "host", host, "--ei", "port", str(port)]


def wait_first_state(offset: int, timeout_s: float) -> str | None:
    """First `STATE ` line bench_host appended to its log after byte offset, or None."""
    deadline = time.monotonic() + timeout_s
    gate = threading.Event()
    while True:
        try:
            with BENCH_HOST_LOG.open("rb") as fh:
                fh.seek(offset)
                for ln in fh.read().decode("utf-8", "replace").splitlines():
                    if " STATE " in ln:
                        return ln.split(" STATE ", 1)[1]
        except OSError:
            pass
        if time.monotonic() >= deadline:
            return None
        gate.wait(0.25)


def connect_app(serial: str, pkg: str, host: str | None, port: int) -> str:
    """Restart the app pointed at host:port and return the first listener state line."""
    if not port_in_use(port):
        raise PhoneError(f"nothing listens on port {port}; start `./dev.py listen` first")
    host = host or route_src(phone_ip(serial))
    log(f"host {host}:{port} -> {pkg} on {serial}")
    BENCH_HOST_LOG.parent.mkdir(parents=True, exist_ok=True)
    offset = BENCH_HOST_LOG.stat().st_size if BENCH_HOST_LOG.exists() else 0
    _adb(serial, "shell", "am", "force-stop", pkg, why="force-stop (intent to a running app is a no-op)")
    r = _exec(am_start_argv(serial, pkg, host, port), why="am start", stall_s=ADB_STALL_S,
              overall_s=ADB_STALL_S * 2)
    if r.rc != 0 or "Error" in r.out:
        raise PhoneError(f"am start failed: {r.out.strip()}")
    line = wait_first_state(offset, CONNECT_WAIT_S)
    if line is None:
        tail = _adb(serial, "logcat", "-d", "-t", "60", why="logcat tail").out
        raise PhoneError(f"no state from the app within {CONNECT_WAIT_S}s "
                         f"(expected <=8s: cold start + backoff); logcat tail:\n{tail}")
    log(f"first state: {line}", "ALERT")
    print(line)
    return line


@command("start the app pointed at this PC and confirm it reached the listener",
         args="[--serial S] [--host H] [--port 9910] [--pkg bench|dji]")
@_guarded
def cmd_connect(extra: list[str]) -> int:
    ap = _parser("connect", "point the app at the listener")
    ap.add_argument("--serial")
    ap.add_argument("--host", "--hosts", dest="host", help="default: local address routing to the phone")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--pkg", choices=["bench", "dji"], default="bench")
    a, _ = _parse(ap, extra)
    try:
        _need_tool("adb")
        serial = resolve_serial(a.serial)
        connect_app(serial, PACKAGES[a.pkg], a.host, a.port)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    return 0


CTL_PY = "scripts/re/bench_ctl.py"
CTL_PORT = 6560        # the bench app's control port (BenchControlServer, benchControlPort)
CTL_STALL_S = 8        # bench_ctl bounds connect 3 s + reply 2 s itself; 8 s = stall backstop


def ctl_argv(host: str, port: int, rest: list[str]) -> list[str]:
    return [sys.executable, "-I", CTL_PY, "--host", host, "--port", str(port), *rest]


def adb_forward(serial: str, remote: int) -> int:
    """adb forward tcp:0 -> remote; returns the local port adb allocated."""
    r = _adb(serial, "forward", "tcp:0", f"tcp:{remote}", why="forward the control port")
    m = re.search(r"^(\d+)\s*$", r.out.strip(), re.M)
    if r.rc != 0 or not m:
        raise PhoneError(f"adb forward failed: {r.out.strip() or r.reason}")
    return int(m.group(1))


@command("drive the running bench app over its control port: ping|get|reset|result|mode <m> k=v..|"
         "send <hex>|raw <json>|tail <s>",
         args="[--target IP | --adb [--serial S]] [--port 6560] <sub> [args]")
@_guarded
def cmd_ctl(extra: list[str]) -> int:
    ap = _parser("ctl", "bench app control port client")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--target", help="phone wifi IP (no adb needed)")
    g.add_argument("--adb", action="store_true", help="wired/adb: forward the port (default)")
    ap.add_argument("--serial")
    ap.add_argument("--port", type=int, default=CTL_PORT)
    ap.add_argument("rest", nargs=argparse.REMAINDER, help="ping|get|reset|result|mode <m> k=v..|...")
    a, _ = _parse(ap, extra)
    if not a.rest:
        log("ctl needs a subcommand (ping|get|reset|result|mode|send|raw|tail)", "ERROR")
        return 2
    try:
        if a.target:
            host, port = a.target, a.port
        else:
            _need_tool("adb")
            host, port = "127.0.0.1", adb_forward(resolve_serial(a.serial), a.port)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    # tail <s> legitimately stays quiet for s seconds: stall limit grows with it
    wait = float(a.rest[1]) if a.rest[0] == "tail" and len(a.rest) > 1 else 0
    r = _exec(ctl_argv(host, port, a.rest), why=f"control port {host}:{port}",
              stall_s=CTL_STALL_S + wait, overall_s=CTL_STALL_S * 2 + wait, echo=True)
    return r.rc


def _usb_dialog():
    sys.path.insert(0, str(REPO / "scripts" / "re"))
    import phone_usb_dialog
    return phone_usb_dialog


@command("answer the USB accessory permission dialog and tick 'use by default'",
         args="[--serial S]")
@_guarded
def cmd_grant(extra: list[str]) -> int:
    ap = _parser("grant", "accept the accessory dialog")
    ap.add_argument("--serial")
    a, _ = _parse(ap, extra)
    try:
        _need_tool("adb")
        serial = resolve_serial(a.serial)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    log(f"phone_usb_dialog.accept({serial!r})  [adb calls bounded 15 s each by that module]")
    os.chdir(REPO)       # accept() writes its dump under the relative tmp/
    rc = _usb_dialog().accept(serial, log=log)
    log(f"grant rc={rc} (0 granted, 1 no dialog, 2 controls not found)",
        "INFO" if rc == 0 else "ERROR")
    return rc


# ---- suite / up / rc --------------------------------------------------------
SUITE_NAMES = ["size_sweep", "zero_length", "throughput", "limits", "fuzz", "soak", "all"]
# Suites print only when a case ends, so a stall rule would fire on a healthy run; each wait
# inside bench_host is already bounded. 1800 s covers limits/throughput (not timed: backstop).
SUITE_OVERALL_S = 1800


def suite_argv(names: list[str], port: int, passthrough: list[str]) -> list[str]:
    argv = bench_host_argv("--listen", str(port))
    for n in names:
        argv += ["--suite", n]
    return argv + passthrough


def suite_overall_s(passthrough: list[str]) -> float:
    if "--soak-minutes" in passthrough:
        i = passthrough.index("--soak-minutes")
        try:
            return SUITE_OVERALL_S + float(passthrough[i + 1]) * 60
        except (IndexError, ValueError):
            pass
    return SUITE_OVERALL_S


@command("run bench_host suites against the connected app (app must be started with `connect`; "
         "stop any `listen` first, the suite owns the port)",
         args="NAME [NAME...] [--port 9910] [--fuzz-seed N --fuzz-steps N --soak-minutes N ...]")
@_guarded
def cmd_suite(extra: list[str]) -> int:
    ap = _parser("suite", "run bench suites")
    ap.add_argument("names", nargs="+", choices=SUITE_NAMES)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    # declared (not left to parse_known_args) so their values are not read as suite names
    for opt in ("--fuzz-seed", "--fuzz-steps", "--soak-minutes", "--connect-timeout"):
        ap.add_argument(opt, dest=opt[2:].replace("-", "_"))
    a, rest = _parse(ap, extra, known_only=True)
    for opt in ("--fuzz-seed", "--fuzz-steps", "--soak-minutes", "--connect-timeout"):
        v = getattr(a, opt[2:].replace("-", "_"))
        if v is not None:
            rest += [opt, v]
    try:
        refuse_if_busy(a.port)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    return _exec(suite_argv(a.names, a.port, rest), why="bench suites", echo=True,
                 overall_s=suite_overall_s(rest), tee=LOGS / "suite.log").rc


def rc_argv(mode: str, file: str | None, serial: str | None, passthrough: list[str]) -> list[str]:
    argv = [sys.executable, "-I", "scripts/re/t600_rc_emulator.py", mode]
    if file:
        argv.append(file)
    if serial:
        argv += ["--adb-serial", serial]
    return argv + passthrough


@command("play the RC toward the phone (t600_rc_emulator.py): handshake | listen | replay FILE",
         args="[--serial S] [handshake|listen|replay FILE] [--vid H --pid H --seconds N --accept-dialog]")
@_guarded
def cmd_rc(extra: list[str]) -> int:
    ap = _parser("rc", "RC emulator front")
    ap.add_argument("--serial")
    ap.add_argument("mode", nargs="?", default="handshake", choices=["handshake", "listen", "replay"])
    ap.add_argument("file", nargs="?")
    for opt in ("--vid", "--pid", "--seconds"):
        ap.add_argument(opt)
    ap.add_argument("--accept-dialog", action="store_true")
    a, rest = _parse(ap, extra, known_only=True)
    for opt in ("--vid", "--pid", "--seconds"):
        if getattr(a, opt[2:]) is not None:
            rest += [opt, getattr(a, opt[2:])]
    if a.accept_dialog:
        rest.append("--accept-dialog")
    serial = a.serial or os.environ.get("AWTO_PHONE")    # optional for the emulator: no scan
    seconds = 10.0
    if "--seconds" in rest:
        try:
            seconds = float(rest[rest.index("--seconds") + 1])
        except (IndexError, ValueError):
            pass
    # handshake re-enumerates within 5 s; listen runs --seconds; replay length is unknown.
    overall = 600 if a.mode == "replay" else seconds * 1.25 + 30
    return _exec(rc_argv(a.mode, a.file, serial, rest), why=f"rc {a.mode}", echo=True,
                 overall_s=overall, tee=LOGS / "rc.log").rc


@command("whole bench bring-up: phone -> load --bench -> listener (background) -> connect -> "
         "listener attached in the foreground",
         args="[--serial S] [--connect IP:PORT] [--no-build] [--host H] [--port 9910]")
@_guarded
def cmd_up(extra: list[str]) -> int:
    ap = _parser("up", "one-command bench bring-up")
    ap.add_argument("--serial")
    ap.add_argument("--connect", metavar="IP:PORT")
    ap.add_argument("--no-build", action="store_true")
    ap.add_argument("--host", "--hosts", dest="host")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    a, _ = _parse(ap, extra)
    try:
        _need_tool("adb", *(["flutter"] if not a.no_build else []))
        serial = resolve_serial(a.serial, a.connect)
        log(f"phone: {serial}")
        load(serial, ["bench"], build=not a.no_build)
        refuse_if_busy(a.port)
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    listener = _spawn(bench_host_argv("--listen", str(a.port), "--tail"), why="background listener")
    try:
        # the listener binds within ms (bench_host.start() allows 5 s); connect_app checks it is up
        deadline = time.monotonic() + 5
        gate = threading.Event()
        while not port_in_use(a.port) and listener.poll() is None and time.monotonic() < deadline:
            gate.wait(0.1)
        if listener.poll() is not None or not port_in_use(a.port):
            log("listener did not come up within 5 s (bench_host binds in ms)", "ERROR")
            return 1
        connect_app(serial, PKG_BENCH, a.host, a.port)
        log("attached: listener in the foreground, ^C to stop")
        return listener.wait()          # unbounded by design: interactive until ^C
    except PhoneError as e:
        log(str(e), "ERROR")
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if listener.poll() is None:
            listener.terminate()
            try:
                listener.wait(5)        # bench_host.stop() closes sockets in ms
            except subprocess.TimeoutExpired:
                listener.kill()


def usage() -> int:
    print(__doc__.split("Scaffold usage:")[0].rstrip())
    print(f"\nUsage: ./dev.py <command> [args]\n")
    # Iterate the kinds actually present, ordered - a hardcoded list silently
    # drops any new kind from --help (selftest catches this).
    order = ["aggregate", "step", "action", "meta"]
    kinds = sorted({m["kind"] for m in COMMANDS.values()},
                   key=lambda k: (order.index(k) if k in order else len(order), k))
    for kind in kinds:
        group = {n: m for n, m in COMMANDS.items() if m["kind"] == kind}
        if not group:
            continue
        print(f"  {kind}:")
        for name, meta in sorted(group.items()):
            print(f"    {name:<12} {meta['summary']}")
        print()
    print(f"Log: {LOG.relative_to(REPO)}   JSON help: ./dev.py describe")
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        return usage()
    name, *extra = argv
    meta = COMMANDS.get(name)
    if meta is None:
        print(f"unknown command: {name!r} — try ./dev.py describe", file=sys.stderr)
        return 2
    rc = meta["fn"](extra)
    return 0 if rc == SKIPPED else rc


if __name__ == "__main__":
    sys.exit(main())
