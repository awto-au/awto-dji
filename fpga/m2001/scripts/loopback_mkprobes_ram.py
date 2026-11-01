#!/usr/bin/env python3.15t
"""Write tmp/loopback/probes_ram.json: FFs in the TX playback RAM (M9K (23,62)/(23,63)) data/addr/raddr/we cones + 3 upstream FF stages (#91).

  python3.15t fpga/m2001/scripts/loopback_mkprobes_ram.py       then rebuild the sim (cycloneiv_clean_loopback_sim.py build)
"""
import json, pickle, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _repo import BOARD, PLURIBUS
from cycloneiv_clean_partition import Partition, cell_of
from cycloneiv_clean_fsm_rxdetect_trace import cone_leaves
nl = pickle.load(open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/nl.pkl"), "rb"))
ffmap = json.load(open(os.path.join(str(PLURIBUS), "tmp/image_sim_dji_push/ffmap.json")))
P = Partition(nl, [], nets_tsv=os.path.join(BOARD, "nets.tsv"))
out = {}
def ffs(cells):
    return sorted({c for c in cells if isinstance(c, str) and c in ffmap and c.startswith("ff_")})
for xy in ((23, 62), (23, 63)):
    m = P.m9k[xy]
    for grp in ("data", "addr", "raddr"):
        drv = [cell_of(p) for p in m[grp]]
        drv = [c for c in drv if c]
        leaves = set(c for c in drv if not (isinstance(c, str) and c.startswith("lc_")))
        for c in drv:
            if isinstance(c, str) and c.startswith("lc_"):
                leaves |= cone_leaves(P, c)
        out[f"pb{xy[0]}_{xy[1]}_{grp}"] = ffs(leaves)
    we = cell_of(m["we"])
    out["pb_we"] = ffs(cone_leaves(P, we))
    out["pb_we_drv"] = ffs([we])
out = {k: v for k, v in out.items() if v}
# dedupe identical groups (addr/we shared between the two RAMs)
seen, ded = set(), {}
for k, v in out.items():
    t = tuple(v)
    if t not in seen:
        seen.add(t); ded[k] = v
print({k: len(v) for k, v in ded.items()}, "total bits", sum(len(v) for v in ded.values()))
json.dump(ded, open(os.path.join(str(PLURIBUS), "tmp/loopback/probes_ram.json"), "w"), indent=1)


def add_levels(P, ffmap, groups, seed_key, levels=3, budget=560):
    """Backward FF stages from the seed group: level k = FFs in the D/ena cones of level k-1 not yet probed (#91)."""
    seen = {f for v in groups.values() for f in v}
    cur = list(groups[seed_key])
    used = 0
    for k in range(1, levels + 1):
        nxt = set()
        for f in cur:
            F = P.ff[f]
            for pin in ("d", "ena"):
                c = cell_of(F.get(pin))
                if not c:
                    continue
                nxt |= {c} if not (isinstance(c, str) and c.startswith("lc_")) else cone_leaves(P, c)
        nxt = sorted(f for f in nxt if isinstance(f, str) and f.startswith("ff_") and f in ffmap and f not in seen)
        if used + len(nxt) > budget:
            break
        groups[f"lvl{k}"] = nxt
        seen |= set(nxt)
        used += len(nxt)
        cur = nxt
        print("level", k, len(nxt))
    return groups


if __name__ == "__main__":
    allg = add_levels(P, ffmap, dict(ded, pb_all=sum(ded.values(), [])), "pb_all")
    allg.pop("pb_all")
    import cycloneiv_clean_image_sim as IS      # regfile copies: one probe group per (addr, enable), bit order = register bit 7..0
    spi = json.load(open(os.path.join(str(PLURIBUS), "tmp/dji_spi/image.json")))
    for a_, ents in IS.spi_regs(nl, spi, [0x00, 0x02, 0x08, 0x09]).items():
        for en, mem in ents:
            by = {b: f for f, b, _inv in mem if f in ffmap}
            if len(by) == 8:
                allg[f"rg{a_:02x}_{en}"] = [by[b] for b in range(7, -1, -1)]
    allg["rg_37_79"] = sorted(F["name"] for F in nl.ffs if F.get("ena") == "lc_37_82_1" and F["name"] in ffmap)
    json.dump(allg, open(os.path.join(str(PLURIBUS), "tmp/loopback/probes_ram.json"), "w"), indent=1)
    print({k: len(v) for k, v in allg.items()}, "total bits", sum(len(v) for v in allg.values()))
