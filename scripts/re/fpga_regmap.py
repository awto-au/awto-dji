#!/usr/bin/env python3
"""Build the m0900 -> FPGA register map: static table values plus who touches each register.

Sources (all from firmware/P3X_FW_V01.11.0020_m0900.bin):
  - init tables: 0x08016260 (boards 2/4/5) and 0x08016460 (boards 6/7), 2 pages x 256 B,
    written to FPGA regs 0..0xFF by init_fpga_config (0x0800d7c6)
  - constant-register accesses: calls to spi_fpga_raw_write 0x0800ce76 / spi_fpga_raw_read
    0x0800ce9a whose r0 is loaded by an immediate within the previous few instructions

Output: docs/data/fpga-regs.tsv  (reg, table values, writers, readers)
Meaning of each register is NOT decoded here; see docs/phy-params.md for the ones tied to
AD9363 tuning (0xB0-0xBE hold channel PLL words). Interop RE only (CLAUDE.md).
Log: tmp/logs/fpga_regmap.log
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m0900_trace as t  # noqa: E402

ROOT = t.ROOT
WR, RD = 0x0800CE76, 0x0800CE9A
TABLES = {"A": 0x08016260, "B": 0x08016460}


def main():
    path = os.path.join(ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin")
    img = open(path, "rb").read()
    strings = t.find_strings(img)
    insn_at, calls, callers, _, _ = t.sweep(img, strings)
    func_start = t.make_func_start(insn_at)
    syms = t.SYMS

    def fname(a):
        f = func_start(a)
        return f"{syms.get(f, 'fn')}@{f:#x}" if f else "?"

    def imm_r0(site):
        """r0 immediate loaded within the 4 instructions before a BL (movs/mov.w r0,#imm)."""
        a = site
        for _ in range(8):
            a -= 2
            it = insn_at.get(a)
            if not it:
                continue
            _, m, ops, _sz = it
            if m in ("movs", "mov", "mov.w", "movw") and ops.startswith("r0, #"):
                try:
                    return int(ops.split("#")[1], 0)
                except ValueError:
                    return None
            if m in ("bl", "blx", "pop", "bx"):
                return None
        return None

    writers, readers, unknown = {}, {}, {"w": 0, "r": 0}
    for tgt, store, key in ((WR, writers, "w"), (RD, readers, "r")):
        for site in callers.get(tgt, []):
            reg = imm_r0(site)
            if reg is None:
                unknown[key] += 1
                continue
            store.setdefault(reg, set()).add(fname(site))

    tabs = {}
    for k, a in TABLES.items():
        o = a - t.BASE
        tabs[k] = (img[o:o + 256], img[o + 256:o + 512])

    out = os.path.join(ROOT, "docs", "data", "fpga-regs.tsv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w") as f:
        f.write("reg\tA_p1\tA_p2\tB_p1\tB_p2\twriters\treaders\n")
        for r in range(256):
            row = [f"0x{r:02X}"]
            for k in ("A", "B"):
                for pg in (0, 1):
                    row.append(f"{tabs[k][pg][r]:02X}")
            row.append(";".join(sorted(writers.get(r, ()))))
            row.append(";".join(sorted(readers.get(r, ()))))
            f.write("\t".join(row) + "\n")
    os.makedirs(os.path.join(ROOT, "tmp", "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "tmp", "logs", "fpga_regmap.log"), "w") as f:
        f.write(f"writers regs={len(writers)} readers regs={len(readers)} "
                f"non-constant sites w={unknown['w']} r={unknown['r']}\n")
    print(f"wrote {out}; constant-reg writers {len(writers)} regs, readers {len(readers)} regs; "
          f"non-constant call sites: write {unknown['w']}, read {unknown['r']}")


if __name__ == "__main__":
    main()
