#!/usr/bin/env python3
"""Issue #84 Q5: every reference to radio_session_key / link_xor_key in the m0900 image.

1. Literal-pool scan of the raw image (base 0x08008000) for words in the radio_state_S (0x20001ab4),
   S+0x14 (0x20001ac8), session key (0x20001b00) and xor key (0x20001b18) ranges.
2. For each pool word, the ldr sites in the Ghidra dump, and the functions that load it.
3. In those functions, every load/store with immediate offset in S+0x4c..0x6b (key 0x4c..0x63, xor key 0x64..0x6b)
   relative to a base register: printed for manual classification (I: offset-in-range does not prove the base register).
Usage: session_key_xrefs.py   Log: ./tmp/logs/session_key_xrefs.log
"""
from __future__ import annotations

import bisect
import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402

FW = REPO / "firmware" / "P3X_FW_V01.11.0020_m0900.bin"
DUMP = REPO / "re" / "ghidra-projects" / "m0900_radio" / "m0900_dump.txt"
BASE = 0x08008000
HDR = re.compile(r"^---- (\S+) @ ([0-9a-f]+) ----$")
INS = re.compile(r"^([0-9a-f]{8}) \[([^\]]+)\]: (.*)$")
OFS = re.compile(r"\[r\d+,#0x([0-9a-f]+)\]")


def main() -> int:
    d = FW.read_bytes()
    pools = {}
    for off in range(0, len(d) - 3, 2):
        v = struct.unpack_from("<I", d, off)[0]
        if 0x20001AB4 <= v <= 0x20001AD0 or 0x20001B00 <= v <= 0x20001B3F:
            pools[BASE + off] = v
            log(f"pool {BASE + off:#010x} = {v:#010x}")
    lines = DUMP.read_text(errors="replace").splitlines()
    funcs: dict[str, list[tuple[int, str]]] = {}
    for ln in lines:
        m = INS.match(ln)
        if m:
            funcs.setdefault(m.group(2), []).append((int(m.group(1), 16), m.group(3)))
    users = {}
    for fn, ins in funcs.items():
        for a, t in ins:
            for p in pools:
                if f"[0x{p:08x}]" in t and "ldr" in t:
                    users.setdefault(fn, set()).add(pools[p])
    for fn, tg in sorted(users.items(), key=lambda kv: funcs[kv[0]][0][0]):
        log(f"func {fn} @ {funcs[fn][0][0]:#x} loads {sorted(hex(x) for x in tg)}")
        for a, t in funcs[fn]:
            for m in OFS.finditer(t):
                o = int(m.group(1), 16)
                if 0x4C <= o <= 0x6B:
                    log(f"    {a:#010x} {t}   (S+{o:#x}: {'key' if o < 0x64 else 'xor_key'} if base is S)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
