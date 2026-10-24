#!/usr/bin/env python3
"""Full Ghidra ARM disassembly pass over m0100 Linux userland ELF binaries.

Issue #37: go past strings-only fragments of cam_server (USB-net bring-up,
FX2LP version read) into the real command/control surface - function
boundaries, call sites for the `system()`/`popen()` shell-script invocations,
and xrefs for the security-relevant strings (authorized-MAC reject, FTP
credential target, FX2LP/wifi firmware upload).

Target is a dynamically-linked, stripped ARM EABI5 ELF (not raw Cortex-M
firmware like m0900/m1500) - uses Ghidra's own ELF loader (auto-detects
ARM:LE:32:v7, base addresses from the ELF program headers), not
BinaryLoader+explicit base like the earlier Cortex-M scripts.

Output: tmp/<name>_ghidra/<name>_dump.txt (function list, filtered string
xrefs, full disassembly). Log: ./tmp/logs/cam_server_ghidra_disasm.log
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
from ghidra_archive import archive_project  # noqa: E402

GHIDRA_HOME = Path("/home/dan/tools/ghidra_12.2_DEV")
ANALYZE_HEADLESS = GHIDRA_HOME / "support" / "analyzeHeadless"
SCRIPT_DIR = REPO / "scripts" / "re" / "ghidra"

# String substrings worth an xref report per binary (comma-joined for the
# Java script's getScriptArgs()[1]).
STRING_FILTERS = {
    "cam_server": "ftpput,fxload,usbmod,usbsw,add_usb_net,Authorized,arp,manufacturer,"
                  "rscv_addr,bitrate,68013,wifi fw",
    "viz_tracking": "",  # no filter -> whole string table reported (smaller hit set expected)
}


def run_ghidra(binary: Path, name: str) -> Path:
    out_dir = REPO / "tmp" / f"{name}_ghidra"
    proj_dir = out_dir / "proj"
    if proj_dir.exists():
        import shutil
        shutil.rmtree(proj_dir)
    proj_dir.mkdir(parents=True)
    dump_path = out_dir / f"{name}_dump.txt"
    cmd = [
        str(ANALYZE_HEADLESS), str(proj_dir), f"{name.capitalize()}Project",
        "-import", str(binary),
        "-postScript", "DumpELF.java", str(dump_path), STRING_FILTERS.get(name, ""),
        "-scriptPath", str(SCRIPT_DIR),
    ]
    log("running: " + " ".join(cmd))
    headless_log = REPO / "tmp" / "logs" / f"{name}_ghidra_headless.log"
    with headless_log.open("w", encoding="utf-8") as fh:
        # Full auto-analysis on a <=70 KB ARM ELF - two orders smaller than
        # anything Ghidra's analyzers are slow on (see m0900 script note).
        # No timeout wrapper - headless Ghidra gives no stall-watchable
        # progress line (awto-dan agent-rules host-process note).
        proc = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    log(f"analyzeHeadless exit={proc.returncode}, log at {headless_log}")
    if proc.returncode != 0 or not dump_path.exists():
        raise RuntimeError(f"Ghidra headless run failed for {name}, see {headless_log}")
    return dump_path


def report(dump_path: Path, name: str) -> None:
    text = dump_path.read_text(encoding="utf-8", errors="replace")
    func_line = next((l for l in text.splitlines() if l.startswith("=== FUNCTIONS")), "")
    insn_line = next((l for l in text.splitlines() if l.startswith("TOTAL INSTRUCTIONS")), "")
    log(f"[{name}] {func_line}")
    log(f"[{name}] {insn_line}")
    xref_section = text.split("=== STRING XREFS", 1)[-1].split("=== FULL DISASSEMBLY", 1)[0]
    log(f"--- [{name}] STRING XREFS ---")
    for line in xref_section.splitlines():
        if line.strip():
            log(line)


def main() -> int:
    if not ANALYZE_HEADLESS.exists():
        log(f"Ghidra analyzeHeadless not found at {ANALYZE_HEADLESS}", level="ERROR")
        return 1
    rfs = REPO / "tmp" / "air" / "rfs_P3X0020_full"
    targets = ["cam_server", "viz_tracking"]
    if len(sys.argv) > 1:
        targets = sys.argv[1:]
    for name in targets:
        binary = rfs / "usr" / "bin" / name
        if not binary.exists():
            log(f"{binary} not found - run scripts/re/rfs_full_extract.py first", level="ERROR")
            return 1
        dump_path = run_ghidra(binary, name)
        report(dump_path, name)
        log(f"[{name}] full dump: {dump_path}")
        archive = archive_project(REPO, REPO / "tmp" / f"{name}_ghidra" / "proj", f"{name}_m0100")
        log(f"[{name}] project archived (not deleted): {archive}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
