"""Regression test for phone_kprobe_sniff.py's trace-line parser, against real lines
captured 2026-10-24 from the live dji.pilot app. Run:
python3 -I scripts/re/test_phone_kprobe_sniff.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from phone_kprobe_sniff import parse_trace_line  # noqa: E402
from relay_records import command_verdict  # noqa: E402

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


# Real ftrace line captured live from dji.pilot (GetParams/DM368, CRC/SIMPLE-confirmed
# 2026-10-24 - see docs/dji-app-protocol-pipeline.md's sibling capture doc).
real_line = (
    "    Thread-16126-2651  [007] d... 12241.957379: acc_w: (acc_write+0x0/0x2d4) "
    "cnt=14 b0=0x55 b1=0xe b2=0x4 b3=0x66 b4=0x2 b5=0x28 b6=0xbc b7=0x6 b8=0x43 "
    "b9=0xfb b10=0x31 b11=0x89 b12=0xc1 b13=0xf b14=0x0 b15=0x0 b16=0x1 b17=0x80 "
    "b18=0x0 b19=0x0 b20=0x0 b21=0x0 b22=0xee b23=0xe2 b24=0x0 b25=0x0 b26=0x0 "
    "b27=0x0 b28=0x0 b29=0x0 b30=0x0 b31=0x0 b32=0x50 b33=0x15 b34=0xe6 b35=0x14 "
    "b36=0xe b37=0x15 b38=0x34 b39=0x14"
)
frame = parse_trace_line(real_line)
check("parses to exactly cnt=14 bytes, trailing fetch-width padding discarded",
      frame, bytes.fromhex("550e04660228bc0643fb3189c10f"))

verdict = command_verdict(frame)
check("decrypts (SIMPLE) to a real, catalog-matched command",
      (verdict["accepted"], verdict["cmdSet"], verdict["cmdId"], verdict["protection"]),
      (True, 0x08, 0x04, 3))

check("non-matching line (no cnt=/bN= fields) returns None",
      parse_trace_line("some unrelated trace line with no fields"), None)

check("cnt larger than fetched bytes returns None (fetch width too narrow, not a crash)",
      parse_trace_line("cnt=99 b0=0x55 b1=0xe"), None)

if FAILURES:
    print(f"{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(" ", f)
    sys.exit(1)
print("all checks passed")
