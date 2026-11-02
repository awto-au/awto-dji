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
