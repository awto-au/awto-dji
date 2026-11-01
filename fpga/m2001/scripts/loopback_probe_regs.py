#!/usr/bin/env python3.15t
"""Value history of the probed regfile copies (rg* groups of probes_ram.json) from a loopback sim probe trace (#91).

  python3.15t fpga/m2001/scripts/loopback_probe_regs.py TAG      (reads tmp/loopback/probe_TAG.txt in the pluribus checkout)
"""
import json, re, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import PLURIBUS
L = os.path.join(str(PLURIBUS), "tmp", "loopback") + "/"
tag = sys.argv[1]
meta = json.load(open(L + "tb_meta.json")); pr = json.load(open(L + "probes_ram.json"))
decl = {}
for line in open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/rtl_s.v")):
    m = re.match(r"\s*reg \[(\d+):0\] (\w+) ", line)
    if m: decl[m.group(2)] = int(m.group(1)) + 1
    if line.startswith("assign") or len(decl) > 5000: break
widths = [(n, w if w else decl[n]) for n, w in meta["probes"]]
pos = sum(w for _, w in widths); fields = {}
for n, w in widths: pos -= w; fields[n] = (pos, w)
rows = [(int(t), int(v, 16)) for t, v in (l.split() for l in open(L + f"probe_{tag}.txt"))]
for g in [k for k in pr if k.startswith("rg")]:
    p, w = fields[g]; hist = []; prev = None
    for t, v in rows:
        x = (v >> p) & ((1 << w) - 1)
        if x != prev: hist.append((t, x)); prev = x
    print(g, "value history (half-cycle, hex):", [(t, f"{x:02x}") for t, x in hist][:8], "changes", len(hist) - 1)
