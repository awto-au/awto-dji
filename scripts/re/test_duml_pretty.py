"""Regression test for duml_pretty's log selection: --since is relative to the log's last
line (not wall-clock now), so finished logs replay. Run:
python3 -I scripts/re/test_duml_pretty.py
"""
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from duml_pretty import cutoff_for, iter_lines  # noqa: E402

FAILURES = []


def check(name, got, want):
    if got != want:
        FAILURES.append(f"{name}: got {got!r}, want {want!r}")


LOG = (
    "2026-10-24T12:00:00 sender=0x04 receiver=0x02 seq=1 type=0x03 set=0x04 id=0x05 payload=00\n"
    "2026-10-24T12:00:50 sender=0x04 receiver=0x02 seq=2 type=0x03 set=0x04 id=0x05 payload=00\n"
    "2026-10-24T12:01:00 sender=0x04 receiver=0x02 seq=3 type=0x03 set=0x04 id=0x05 payload=00\n"
)

check("cutoff is 60s before the last line, not wall-clock now",
      cutoff_for(io.StringIO(LOG), 60), "2026-10-24T12:00:00")

check("replay keeps lines at/after cutoff (string compare on first 19 chars)",
      [ln[:19] for ln in iter_lines(io.StringIO(LOG), follow=False)
       if ln[:19] >= "2026-10-24T12:00:00"],
      ["2026-10-24T12:00:00", "2026-10-24T12:00:50", "2026-10-24T12:01:00"])

check("replay yields a trailing partial line rather than dropping it",
      list(iter_lines(io.StringIO("a\nb"), follow=False)), ["a\n", "b"])

if FAILURES:
    print(f"{len(FAILURES)} failure(s):")
    for f in FAILURES:
        print(" ", f)
    sys.exit(1)
print("all checks passed")
