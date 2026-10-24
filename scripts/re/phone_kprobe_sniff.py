#!/usr/bin/env python3
"""Non-invasive, kernel-level capture of a phone-side DJI app's OUTGOING DUML commands,
via ftrace/kprobes on the AOA accessory gadget driver's acc_write() - confirmed working
2026-10-24 against the live dji.pilot app, end to end (CRC-validated, SIMPLE-decrypted,
catalog-matched real commands).

Why this instead of strace/usbmon: strace (ptrace-based) reliably crashes dji.pilot/
dji.go.v4 once past their consent flow (confirmed this session, AppGuard anti-tamper);
this phone's kernel has no usbmon module at all (confirmed: /sys/kernel/debug/usb has
only "devices", no "usbmon" subdir, even after enabling root/SELinux permissive).
ftrace kprobes use neither - no ptrace, no usbmon - so they hit neither wall.

Only the OUTGOING direction (app -> RC) is implemented. The incoming direction
(acc_complete_out, the USB-OUT completion callback) was tried and found NOT reliable:
captured values were static/unchanging across many hits, inconsistent with real
telemetry (which changes every ~10s of ms) - almost certainly a stale/cached read
(ARM DMA cache-coherency: the kprobe's CPU read can race ahead of the driver's own
cache-invalidation step for that buffer). Not fixed in this pass - see
docs/known-telemetry-and-commands.md.

Requires: root (Magisk su) on the target device, kernel kprobe support (this session's
device: a Samsung phone, kernel 4.9.337 - confirmed via `ls /sys/kernel/debug/tracing`
and the presence of the acc_write/acc_read symbols in /proc/kallsyms). SELinux
permissive may be required if debugfs is otherwise access-denied (was on this device
before the operator set it permissive this session).

Usage:
    python3 -I scripts/re/phone_kprobe_sniff.py --device <serial> [--duration SECONDS]

Output: appends decoded frames to the SAME captures/sessions/<date>/aoa_relay_frames.log
format aoa_relay_server.py writes, so duml_pretty.py/verify.py/duml_telemetry.py's
tail_* functions all work unmodified against this capture too.
"""
import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True,
                            text=True, check=True).stdout.strip())
sys.path.insert(0, str(ROOT / "scripts" / "re"))
from duml_proto import session_log_dir  # noqa: E402
from relay_records import command_verdict  # noqa: E402

# Fixed-width byte fetch past the real frame length is harmless (just adjacent memory,
# discarded once `cnt` truncates it) - 40 covers every DUML frame length seen so far.
MAX_FETCH_BYTES = 40

SETUP_SCRIPT = f"""#!/system/bin/sh
cd /sys/kernel/debug/tracing
echo 0 > tracing_on
echo 0 > events/kprobes/enable
echo > kprobe_events
FETCH="cnt=%x2:u64"
for i in $(seq 0 {MAX_FETCH_BYTES - 1}); do FETCH="$FETCH b$i=+$i(%x1):x8"; done
echo "p:acc_w acc_write $FETCH" >> kprobe_events
echo 1 > events/kprobes/enable
echo 1 > tracing_on
echo ready
"""

TRACE_LINE_RE = re.compile(r"cnt=(\d+)\s+(b\d+=0x[0-9a-f]+(?:\s+b\d+=0x[0-9a-f]+)*)")
BYTE_RE = re.compile(r"b(\d+)=0x([0-9a-f]+)")


def adb(device, *args, check=True):
    return subprocess.run(["adb", "-s", device, *args], capture_output=True, text=True,
                           check=check)


def setup_kprobe(device: str) -> None:
    script_path = "/data/local/tmp/phone_kprobe_sniff_setup.sh"
    tmp = ROOT / "tmp" / "phone_kprobe_sniff_setup.sh"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    tmp.write_text(SETUP_SCRIPT)
    adb(device, "push", str(tmp), script_path)
    r = adb(device, "shell", "su", "-c", f"sh {script_path}", check=False)
    if "ready" not in r.stdout:
        raise SystemExit(f"kprobe setup failed - stdout={r.stdout!r} stderr={r.stderr!r}")


def parse_trace_line(line: str) -> bytes | None:
    m = TRACE_LINE_RE.search(line)
    if not m:
        return None
    cnt = int(m.group(1))
    byte_vals = {int(i): int(v, 16) for i, v in BYTE_RE.findall(m.group(2))}
    if cnt > len(byte_vals):
        return None  # fetch width too small for this frame - widen MAX_FETCH_BYTES
    return bytes(byte_vals[i] for i in range(cnt))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                  formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--device", required=True)
    ap.add_argument("--duration", type=float, default=None,
                     help="seconds to capture, then exit (default: until Ctrl-C)")
    args = ap.parse_args()

    setup_kprobe(args.device)
    log_path = Path(session_log_dir()) / "aoa_relay_frames.log"
    log_f = open(log_path, "a", buffering=1)
    print(f"capturing outgoing DUML commands (kprobe on acc_write) -> {log_path}")

    seen_offsets = set()
    start = time.time()
    try:
        while args.duration is None or time.time() - start < args.duration:
            r = adb(args.device, "shell", "su", "-c",
                    "cat /sys/kernel/debug/tracing/trace", check=False)
            for line in r.stdout.splitlines():
                key = line.strip()
                if key in seen_offsets:
                    continue  # ftrace's `trace` is a snapshot, not a tail - dedupe
                seen_offsets.add(key)
                frame = parse_trace_line(line)
                if frame is None:
                    continue
                v = command_verdict(frame)
                if not v["accepted"]:
                    continue
                ts = time.strftime("%Y-%m-%dT%H:%M:%S")
                log_f.write(f"{ts} sender={frame[4]:#04x} receiver={frame[5]:#04x} "
                            f"seq={v['sequence']} type={frame[8]:#04x} "
                            f"set={v['cmdSet']:#04x} id={v['cmdId']:#04x} "
                            f"protection={v['protection']} payload={v['payload']} "
                            f"source=kprobe_acc_write\n")
            if len(seen_offsets) > 50000:
                seen_offsets.clear()  # ftrace ring buffer wrapped - old lines are gone anyway
    except KeyboardInterrupt:
        pass
    finally:
        log_f.close()


if __name__ == "__main__":
    main()
