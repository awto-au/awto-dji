#!/usr/bin/env python3
"""Statically decode the AD9363 init script that m0900 init_fpga_config (0x0800d7c6) runs.

Finding: the AD9363 base profile is NOT runtime-computed. It is a table of 4-byte records
[op, a, b, c] at 0x08016660 (2639 records = 0x293c bytes, boards 2/4/5), executed by the
interpreter at 0x0800d318. Interop/structural RE only (CLAUDE.md).

Interpreter ops (from disasm 0x0800d318, verified):
  0x05  FPGA reg write   [reg=b, val=c]                (spi_fpga_raw_write)
  0x06  AD9363 write     [0x80|hi, lo, val]            (ad936x_reg_sync_write)
  0x08  AD9363 read      [hi, lo]                      (value kept only for reg 0x0A3)
  0x0A  AD9363 poll      addr=(a&0xF)<<8|b; wait until bit (c>>4) == (c&1); 300 tries,
                         20 ms lead-in + 2 ms/try (0x0800c1dc units)
  0x0B  delay            c units (0x0800c1dc)
  0x0C/0x0D  block begin/end marker (a=0x1B). Other ops are no-ops.

Usage:  python3 scripts/re/m0900_ad_script.py [capture.txt]
Log:    tmp/logs/m0900_ad_script.log
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], cwd=HERE,
            stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return os.path.abspath(os.path.join(HERE, "..", ".."))


ROOT = repo_root()
BASE = 0x08008000
SCRIPT_A = (0x08016660, 0x293C)   # boards 2/4/5 (verified: init_fpga_config 0x0800d82c loop)
SCRIPT_B = (0x08018F9C, 0x10C)    # boards 6/7 (0x08016660 + 0x293c, limit 0x10c)
FPGA_EXTRA = (0x080190A8, 0x38)   # 14 FPGA writes, boards 4/5 and [0x200000f8]==0x01000910


def records(img, start, size):
    for off in range(0, size, 4):
        o = start + off - BASE
        yield start + off, tuple(img[o:o + 4])


def run(img, start, size, log):
    ad, fpga, polls, seq = {}, {}, [], []
    for addr, (op, a, b, c) in records(img, start, size):
        if op == 6:
            reg = ((a & 0x7F) << 8) | b
            ad[reg] = c
            seq.append(("W", reg, c))
        elif op == 5:
            fpga[b] = c
            seq.append(("F", b, c))
        elif op == 8:
            seq.append(("R", ((a & 0x7F) << 8) | b, None))
        elif op == 0x0A:
            reg = ((a & 0xF) << 8) | b
            polls.append((addr, reg, c >> 4, c & 1))
            seq.append(("P", reg, c))
        elif op == 0x0B:
            seq.append(("D", 0, c))
        log(f"  {addr:#010x}: {op:02x} {a:02x} {b:02x} {c:02x}")
    return ad, fpga, polls, seq


def main():
    with open(os.path.join(ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin"), "rb") as f:
        img = f.read()
    lines = []

    def log(s=""):
        lines.append(s)

    def p(s=""):
        lines.append(s)
        print(s)

    ad, fpga, polls, seq = run(img, *SCRIPT_A, log)
    p(f"# script A {SCRIPT_A[0]:#x} +{SCRIPT_A[1]:#x}: {SCRIPT_A[1] // 4} records, "
      f"{len(ad)} distinct AD9363 regs written, {len(polls)} poll records")
    p("## Poll records (wait until reg bit == v, else 300-try timeout)")
    for addr, reg, bit, v in polls:
        p(f"  {addr:#x}: reg {reg:#05x} bit{bit} == {v}")
    reads = [s for s in seq if s[0] == "R"]
    p(f"## Read records: {sorted({hex(s[1]) for s in reads})}")

    ad_b, _, polls_b, _ = run(img, *SCRIPT_B, log)
    p(f"\n# script B {SCRIPT_B[0]:#x} +{SCRIPT_B[1]:#x} (boards 6/7): "
      f"{len(ad_b)} regs, {len(polls_b)} polls")

    # Gain table stream: 0x130 = index, 0x131..0x133 = data, 0x137 = config strobe.
    tbl, idx = {}, None
    cur = {}
    for kind, reg, val in seq:
        if kind != "W":
            continue
        if reg == 0x130:
            idx = val
            cur = {}
        elif reg in (0x131, 0x132, 0x133):
            cur[reg] = val
        elif reg == 0x137 and idx is not None and len(cur) == 3:
            tbl[idx] = (cur[0x131], cur[0x132], cur[0x133])
    p(f"\n## Gain-table writes (0x130/0x131-3/0x137): {len(tbl)} indexes "
      f"(max index {max(tbl) if tbl else None})")

    p("\n## Effective AD9363 map from script A (last write wins)")
    for r in sorted(ad):
        p(f"  {r:#05x} = {ad[r]:#04x}")

    if len(sys.argv) > 1:
        cap = {}
        for ln in open(sys.argv[1]):
            q = ln.split()
            if len(q) >= 4 and q[0] == "W" and q[1] == "ad9363":
                cap[int(q[2], 16)] = int(q[3], 16)
        diff = {r: (ad.get(r), cap.get(r)) for r in set(ad) | set(cap) if ad.get(r) != cap.get(r)}
        p(f"\n## Script vs capture {os.path.basename(sys.argv[1])}: {len(diff)} differing regs")
        for r in sorted(diff):
            p(f"  {r:#05x} script={diff[r][0]} capture={diff[r][1]}")

    os.makedirs(os.path.join(ROOT, "tmp", "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "tmp", "logs", "m0900_ad_script.log"), "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
