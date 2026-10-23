#!/usr/bin/env python3.15t
"""PRIVATE (board-specific, untracked): io_table.tsv + m2001.bt -> pins.tsv + hypotheses.tsv.

Rules, each with its evidence and confidence (1=no evidence, 3=guess, 5=estimate, 8=inferred, 10=fact):
  CFG   Mistral package table marks the ball a dedicated programming pad          -> 10 (class), function 1
  DDR   HMC-annotated lines name the DDR3 signal (IOINT<sig><kind>.<n>)           -> 5
  DDRB  bank 7A/8A pad with no HMC line (HMC IO lives on top edge; x32 EMIF ~72 balls of 80) -> 3
  PLLO  tile setting PLL_SELECT=PLL on that pad (clock-output path)               -> 3 (setting noise: also on unbonded pads)
  else  no usable evidence                                                        -> 1
Fabric arcs are NOT used: pad DATAIN/DATAOUT arcs appear at the same rate on pads that exist in no package.
"""
import collections
import csv
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("PLURIBUS_REPO") or os.path.normpath(os.path.join(HERE, "..", "..", "..", "pluribus"))
sys.path.insert(0, os.path.join(REPO, "scripts"))
from cyclonev_io_report import load_package  # noqa: E402

BT = os.path.join(REPO, "tmp", "dji", "m2001.bt")
PKG = os.environ.get("E50F_PKG_TXT", os.path.join(REPO, "..", "mistral", "data", "e50f-pkg.txt"))


def hmc_signals():
    """ball -> {sig: set(bit)} using bit = DIN//4 = DOUT//4 = OE//2 (checked: DQ bits agree across kinds)."""
    out = collections.defaultdict(lambda: collections.defaultdict(set))
    for ln in open(BT):
        if ln[0] not in "ris":
            continue
        f = [x.strip() for x in ln.rstrip("\n").split(" ; ")]
        if len(f) < 2:
            continue
        ball = f[1].split()[0]
        if not re.fullmatch(r"[A-Z]{1,2}\d+", ball):
            continue
        for h in re.finditer(r"HMC\.\d+\.\d+(?:\.\d)?:(?:IOINT|PHYDDIO)([A-Z]+?)(DIN|DOUT|OE|ACLR)\.(\d+)", ln):
            sig, kind, n = h.groups()
            n = int(n)
            if kind in ("DIN", "DOUT"):
                out[ball][sig].add(n // 4)
            elif kind == "OE":
                out[ball][sig].add(n // 2)
    return out


def main():
    rows = list(csv.DictReader(open(os.path.join(HERE, "io_table.tsv")), delimiter="\t"))
    by_ball = {r["ball"]: r for r in rows if r["ball"]}
    pkg = load_package(PKG, "u19")
    sigs = hmc_signals()
    pll = set(re.findall(r"PLL_SELECT\.\d+ PLL ; (\w+)", open(BT).read()))
    out, hyp = [], []
    for ball in sorted(pkg, key=lambda b: (len(re.match(r"[A-Z]+", b).group(0)), b, int(re.search(r"\d+", b).group(0)))):
        v = pkg[ball]
        r = by_ball.get(ball)
        if v["type"]:      # power/GND/NC ball (F3, F17 carry a stray gpio/ded tag in Mistral's table)
            continue
        if v["ded"]:
            rec = (ball, "CFG", f"dedicated programming pad {v['ded']} (Mistral package table)", 10,
                   "config/JTAG pin; function by pad index needs Intel pin-out table",
                   "not in bitstream routing")
        elif not v["gpio"]:
            continue
        elif r is None:
            rec = (ball, "UNUSED", "GPIO ball with no routing/settings in the bitstream", 3,
                   "not touched by this design (or tile data absent)", "no pad entry")
        elif ball in sigs:
            s = sigs[ball]
            name = "/".join(f"{k}{'' if k in ('CASN','RASN','WEN','CK','CKN','RESETN') else sorted(b)}"
                            .replace(" ", "") for k, b in sorted(s.items()))
            name = re.sub(r"\[0\]$", "", name) if name.startswith(("CASN", "CK", "RESETN")) else name
            rec = (ball, "DDR3", f"DDR3 {name} via HMC", 5,
                   "HMC IOINT/PHYDDIO node names on this ball in .bt; bit=n//4 (DOUT/DIN), n//2 (OE)",
                   f"bank {v['ioblock']}")
        elif v["ioblock"] in ("7A", "8A"):
            rec = (ball, "DDR3?", "DDR3 bank (unmapped signal)", 3,
                   "top-edge bank holding the HMC IO; no HMC line names this ball", f"bank {v['ioblock']}")
        elif ball in pll:
            rec = (ball, "PLLOUT?", "clock-output path (PLL_SELECT=PLL)", 3,
                   "tile setting PLL_SELECT=PLL; setting also present on unbonded pads, may be noise",
                   f"bank {v['ioblock']}")
        else:
            rec = (ball, "?", "no evidence", 1,
                   "fabric arcs unusable (unbonded pads show same arc rate)", f"bank {v['ioblock']}")
        cls, fn, conf, ev, note = rec[1], rec[2], rec[3], rec[4], rec[5]
        x = r["x"] if r else ""
        y = r["y"] if r else ""
        bi = r["bi"] if r else ""
        out.append((ball, x, y, bi, "unknown", cls, fn, conf, "", "", "", "", "", f"{ev}; {note}"))
        hyp.append((ball, cls, fn, conf, ev, v["ioblock"], r["lut_real"] if r else "", r["hmc_lines"] if r else ""))
    with open(os.path.join(HERE, "pins.tsv"), "w") as fh:
        fh.write("# PRIVATE. device: 5CEBA4U19C8   package: U19   (pin column = BGA ball)\n"
                 "# generated by classify.py from io_table.tsv + m2001.bt; every row: class, evidence, confidence\n"
                 "# COLUMNS: ball x y bi dir class function confidence chip_ref chip_pin chip_signal net_in net_out note\n"
                 "# confidence: 1=no evidence 3=guess 5=estimate 8=inferred 10=fact\n")
        for o in out:
            fh.write("\t".join(str(c) for c in o) + "\n")
    with open(os.path.join(HERE, "hypotheses.tsv"), "w") as fh:
        fh.write("ball\tclass\tfunction\tconf\tevidence\tbank\tlut_real\thmc_lines\n")
        for h in hyp:
            fh.write("\t".join(str(c) for c in h) + "\n")
    print(collections.Counter(o[5] for o in out))
    print(collections.Counter((o[5], o[7]) for o in out))


main()
