#!/usr/bin/env python3
"""Issue #84: search every firmware image for the m0900 link-key constant and DES/3DES tables.

Patterns (all byte-exact; counts are per file):
  CONST   78 65 54 87 62 23 36 47 (plaintext 3DES-encrypted by radio_session_key_init), plus reversed order
  S1NIB   DES S1 row 0 as one-nibble-per-byte (m0900 table style, 14 4 13 1 2 15 11 8 3 10 6 12 5 9 0 7)
  S1PACK  DES S1 row 0 packed two nibbles per byte (e4 d1 2f b8 3a 6c 59 07)
  SP1     combined S+P tables, first words 0x01010400 0x00000000 0x00010000 0x01010404 (mbedtls-style), LE and BE
  SPLD    libdes-style SP table first words 0x02080800 0x00080000 0x02000002 0x02080802, LE and BE
  IPTAB   initial permutation 58 50 42 34 26 18 10 2 (1-based bytes)
  PC1TAB  PC-1 57 49 41 33 25 17 9 1 (1-based bytes)
Hits inside images that have a Ghidra dump are mapped to the containing function.
Usage: session_key_scan.py [--root firmware]   Log: ./tmp/logs/session_key_scan.log
"""
from __future__ import annotations

import bisect
import mmap
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

CONST = bytes.fromhex("7865548762233647")
PATS: dict[str, bytes] = {
    "CONST": CONST,
    "CONST_REV": CONST[::-1],
    "S1NIB": bytes([14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7]),
    "S1PACK": bytes.fromhex("e4d12fb83a6c5907"),
    "SP1_LE": struct.pack("<4I", 0x01010400, 0, 0x00010000, 0x01010404),
    "SP1_BE": struct.pack(">4I", 0x01010400, 0, 0x00010000, 0x01010404),
    "SPLD_LE": struct.pack("<4I", 0x02080800, 0x00080000, 0x02000002, 0x02080802),
    "SPLD_BE": struct.pack(">4I", 0x02080800, 0x00080000, 0x02000002, 0x02080802),
    "IPTAB": bytes([58, 50, 42, 34, 26, 18, 10, 2]),
    "PC1TAB": bytes([57, 49, 41, 33, 25, 17, 9, 1]),
}
SKIP_SUFFIX = {".txt", ".ini", ".csv", ".zip", ".md", ".json", ".tsv", ".py"}
# image name -> (dump, load base). Offsets map to function via the dump's "---- name @ addr ----" headers.
G = REPO / "re" / "ghidra-projects"
MODULES = {
    "P3X_FW_V01.11.0020_m0900.bin": (G / "m0900_radio" / "m0900_dump.txt", 0x08008000),
    "P3X_FW_V01.11.0020_m0306.bin": (G / "m0306_flight_controller" / "m0306_dump.txt", 0x08020000),
    "C1_FW_V01.06.0000_m1400.bin": (G / "m1400_radio" / "m1400_dump.txt", 0xA000),
    "P3X_FW_V01.11.0020_m0400.bin": (G / "m0400_gimbal" / "m0400_dump.txt", None),
    "C1_FW_V01.06.0000_m1601.bin": (G / "m1601_fx3" / "m1601_dump.txt", 0x90000000),
    "C1_FW_V01.06.0000_m1600.bin": (G / "m1600_fx2" / "m1600_dump.txt", 0),
    "P3X_FW_V01.11.0020_m1500.bin": (G / "m1500_fx2lp" / "m1500_dump.txt", 0),
}
HDR = re.compile(r"^---- (\S+) @ ([0-9a-fA-F]+) ----$")


def func_index(dump: Path) -> tuple[list[int], list[str]]:
    pairs = []
    for line in dump.read_text(errors="replace").splitlines():
        m = HDR.match(line)
        if m:
            pairs.append((int(m.group(2), 16), m.group(1)))
    pairs.sort()
    return [p[0] for p in pairs], [p[1] for p in pairs]


def find_all(mm: mmap.mmap, pat: bytes):
    i = mm.find(pat)
    while i != -1:
        yield i
        i = mm.find(pat, i + 1)


def main() -> int:
    root = REPO / (sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else "firmware")
    files = sorted(p for p in root.rglob("*") if p.is_file() and not p.is_symlink()
                   and p.suffix.lower() not in SKIP_SUFFIX and p.stat().st_size >= 8)
    log(f"scanning {len(files)} files under {root.relative_to(REPO)}")
    idx_cache: dict[str, tuple[list[int], list[str]]] = {}
    total = 0
    for p in files:
        rel = p.relative_to(REPO)
        with p.open("rb") as fh, mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            for name, pat in PATS.items():
                hits = list(find_all(mm, pat))
                if not hits:
                    continue
                # weak 8-byte tables are noise in big blobs: cap listing, always print the count
                shown = hits[:8]
                for off in shown:
                    fn = ""
                    mod = MODULES.get(p.name)
                    if mod and mod[1] is not None and mod[0].exists():
                        if p.name not in idx_cache:
                            idx_cache[p.name] = func_index(mod[0])
                        addrs, names = idx_cache[p.name]
                        a = mod[1] + off
                        k = bisect.bisect_right(addrs, a) - 1
                        fn = f" addr={a:#x} in={names[k] if k >= 0 else '?'}"
                    log(f"HIT {name:9} {rel} off={off:#x}{fn}")
                    total += 1
                if len(hits) > len(shown):
                    log(f"HIT {name:9} {rel} ... {len(hits)} total ({len(hits) - len(shown)} not listed)")
    log(f"done: {total} hits listed over {len(files)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
