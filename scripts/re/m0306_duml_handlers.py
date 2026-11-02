#!/usr/bin/env python3
"""Decode the m0306 DUML dispatch table and emit docs/symbols/m0306-duml-handlers.tsv (func rows + table label). Issues #40, #83.

Table: 65 x 8 B at 0x080ab43c = {u8 cmd_set, u8 cmd_id, u16 pad, u32 thumb handler} (V: key precedes its handler;
the earlier reading {handler, key} was shifted by one entry - handler log strings such as "timezone set" match key 3/0x3d only this way).
Names: (cmd_set, cmd_id) -> duml_catalog.py name [I]; STRING_NAMES override where the handler's log string names the command [V].
Run: python3 scripts/re/m0306_duml_handlers.py   Log: ./tmp/logs/m0306_duml_handlers.log
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _log import REPO, log  # noqa: E402
import duml_catalog as dc  # noqa: E402

FW = REPO / "firmware" / "unpacked" / "P3X_FW_V01.11.0020_m0306.bin"
BASE = 0x08020000
TABLE = 0x080AB43C
COUNT = 65
OUT = REPO / "docs" / "symbols" / "m0306-duml-handlers.tsv"
SETS = {1: "special", 2: "camera", 3: "flyc", 4: "gimbal", 6: "rc", 7: "wifi"}
# (cmd_set, cmd_id) -> (name, evidence) where the catalog is ambiguous/absent and a handler log string names it.
STRING_NAMES = {
    (3, 0x6A): ("set_battery_valid_state", "log: [battery]current bat barcode is legal/illegal"),
    (3, 0x9C): ("way_point_mission_set_idle_speed", "log: WP Mission: received idle vel cmd"),
    (3, 0x9D): ("way_point_mission_get_idle_speed", "log: WP Mission: received get idle vel cmd"),
    (3, 0x8D): ("api_sub_mode", "log: app API sub_mode %d"),
    (3, 0x60): ("svo_api_pure_transfer", "log: svo api pure transfer"),
    (3, 0xAB): ("atti_rcv", "log: atti_rcv"),
    (3, 0xAC): ("taillock_rcv", "log: taillock_rcv"),
    (3, 0xF5): ("real_name_info", "log: get_real_name_info / set_real_name_info"),
    (3, 0x3B): ("set_fs_action", "log: set rc lost action"),
    (3, 0x3C): ("get_fs_action", "log: get rc lost action"),
    (4, 0x47): ("power_ctrl_time", "log: gimbal power ctrl time(100ms)"),
    (3, 0x71): ("unk", ""), (3, 0x70): ("unk", ""), (3, 0x74): ("unk", ""), (3, 0x75): ("unk", ""),
    (3, 0xAA): ("unk", ""), (3, 0x50): ("unk", ""), (3, 0x54): ("unk", ""),
}


def snake(s: str) -> str:
    s = re.sub(r"#.*", "", s)
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", s)
    return s.lower()


def main() -> int:
    d = FW.read_bytes()
    inv: dict[tuple[int, int], list[str]] = {}
    for n, (s, c, _sn) in dc.CATALOG.items():
        inv.setdefault((s, c), []).append(n)
    rows = ["addr\tkind\tname\tnote\tsource",
            f"{TABLE:#010x}\ttable\tg_duml_dispatch_tbl\t[V] 65 x 8 B {{u8 cmd_set,u8 cmd_id,u16 pad,u32 handler}}; type=DumlDispatchEntry[65]; cmdsets 1,2,3(x58),4(x3),6,7; null handler = reserved id\tm0306_duml_handlers.py"]
    slots = []
    for j in range(COUNT):
        cs, cmd, _pad, ptr = struct.unpack_from("<BBHI", d, TABLE - BASE + 8 * j)
        if ptr == 0:
            log(f"{j:2d} {cs}/{cmd:#04x} null handler")
            continue
        if (cs, cmd) in STRING_NAMES and STRING_NAMES[(cs, cmd)][0] != "unk":
            nm, ev = STRING_NAMES[(cs, cmd)]
            tag = "V"
        elif (cs, cmd) in inv:
            nm, ev, tag = snake(inv[(cs, cmd)][0]), "duml_catalog name for this (set,id)", "I"
        else:
            nm, ev, tag = "unk", "no catalog name or log string", "U"
        slots.append((j, cs, cmd, ptr & ~1, f"duml_h_{SETS.get(cs, f'cs{cs}')}_{cmd:02x}_{nm}", tag, ev))
    keys = [struct.unpack_from("<BB", d, TABLE - BASE + 8 * k) for k in range(COUNT)]
    by_addr: dict[int, list] = {}
    for sl in slots:
        by_addr.setdefault(sl[3], []).append(sl)
    used: set[str] = set()
    for sl in slots:
        j, cs, cmd, addr, name, tag, ev = sl
        group = by_addr[addr]
        best = min(group, key=lambda g: (g[5] == "U", g[0]))
        if best is not sl:
            log(f"{j:2d} {cs}/{cmd:#04x} shares handler {addr:#x} with {best[4]}")
            continue
        others = [f"{g[1]}/{g[2]:#04x}" for g in group if g is not sl]
        if name in used:
            name += f"_slot{j}"
        used.add(name)
        dup = " [U] same (set,id) also at another table slot" if keys.count((cs, cmd)) > 1 else ""
        alias = f"; also keyed {','.join(others)}" if others else ""
        rows.append(f"{addr:#010x}\tfunc\t{name}\t[{tag}] DUML cmd_set {cs} cmd_id {cmd:#04x} slot {j}; {ev}{alias}{dup}\tm0306_duml_handlers.py")
        log(f"{j:2d} {cs}/{cmd:#04x} {addr:#010x} {name}")
    OUT.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log(f"wrote {len(rows) - 2} func rows -> {OUT.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
