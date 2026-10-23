#!/usr/bin/env python3
"""Generic static Thumb-2 tracer for headerless MCU images (derived from m0900_trace.py).

Defaults: C1 ground m1400 (LPC1765, Cortex-M3), image base 0. Interop/structural RE only
(CLAUDE.md): no keys, no signing bypass, no geofence work.

Addresses are IMAGE OFFSETS (file offset; base 0). --load LOAD = flash address of offset 0
(m1400: 0xA000, verified: reset handler + default-handler stubs); absolute pointers in the
image are translated to offsets by subtracting LOAD.
Usage: python3 scripts/re/mcu_trace.py [--img PATH] [--base 0x0] [--load 0xA000] CMD ARGS
  info                 vector table + sweep stats
  dis ADDR [N]         annotated disassembly (N insns, default 60)
  who ADDR [DEPTH]     caller chain above ADDR (BL/B.W tail calls included)
  ptr ADDR             4-byte LE occurrences of ADDR (thumb bit set/clear) with context
  lit VALUE            code sites that load raw VALUE from a literal pool (or MOVW/MOVT pair)
  litp OFFSET          code sites that load a pointer to image OFFSET (value = OFFSET+LOAD)
  str TEXT             ASCII strings containing TEXT and their ADR/literal xrefs
  tbb ADDR             decode TBB/TBH jump table at an instruction address
Log: tmp/logs/mcu_trace.log (appended)
"""
import os
import re
import subprocess
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB, CS_OP_MEM, CS_OP_IMM
from capstone.arm import ARM_REG_PC


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        top = subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = repo_root()
DEFAULT_LOAD = 0xA000
DEFAULT_IMG = os.path.join(ROOT, "firmware", "unpacked", "C1_FW_V01.06.0000",
                           "C1_FW_V01.06.0000_m1400.bin")
SYMS = {}  # addr -> name, filled from docs/symbols TSV when --syms is given
NAMED = {0x2009C000: "FAST_GPIO", 0x4009C000: "UART3", 0x40010000: "UART1",
         0x4000C000: "UART0", 0x40098000: "UART2", 0x400FC000: "SYSCON",
         0x4002C000: "PINCON", 0x40088000: "SSP0", 0x40030000: "SSP1",
         0x1FFF1FF1: "IAP_ENTRY", 0x1FFF1FF0: "IAP_ENTRY-1", 0x40024000: "FLASH?"}


class Img:
    def __init__(self, path, base, load=0):
        self.path, self.base, self.load = path, base, load
        with open(path, "rb") as f:
            self.d = f.read()

    def word(self, a):
        o = a - self.base
        return int.from_bytes(self.d[o:o + 4], "little") if 0 <= o <= len(self.d) - 4 else None

    def strings(self, minlen=4):
        out, i, n = {}, 0, len(self.d)
        while i < n:
            j = i
            while j < n and 0x20 <= self.d[j] < 0x7F:
                j += 1
            if j - i >= minlen:
                out[self.base + i] = self.d[i:j].decode("ascii", "replace")
            i = j + 1
        return out


def md_new():
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    return md


def sweep(im, start=0x100):
    """Resyncing linear sweep. Returns insn_at, calls[(site,tgt)], litrefs{val:[site]}, adrs{target:[site]}."""
    md = md_new()
    insn_at, calls, lit, adr, litp = {}, [], {}, {}, {}
    addr, end = im.base + start, im.base + len(im.d)
    movw = {}
    while addr < end:
        got = False
        for i in md.disasm(im.d[addr - im.base:], addr):
            got = True
            insn_at[i.address] = (i.mnemonic, i.op_str, i.size)
            m = i.mnemonic
            if m.startswith("bl") or m in ("b", "b.w"):
                for op in i.operands:
                    if op.type == CS_OP_IMM:
                        calls.append((i.address, op.imm, m))
            if m.startswith("ldr"):
                for op in i.operands:
                    if op.type == CS_OP_MEM and op.mem.base == ARM_REG_PC:
                        pool = ((i.address + 4) & ~3) + op.mem.disp
                        v = im.word(pool)
                        if v is not None:
                            lit.setdefault(v, []).append(i.address)
                            if im.load and 0 <= v - im.load < len(im.d):
                                litp.setdefault(v - im.load, []).append(i.address)
            if m in ("adr", "adr.w") and "pc" in i.op_str:
                mm = re.search(r"#(0x[0-9a-f]+|\d+)", i.op_str)
                if mm and m.startswith("adr"):
                    t = ((i.address + 4) & ~3) + int(mm.group(1), 0)
                    adr.setdefault(t, []).append(i.address)
            if m == "movw":
                mm = re.match(r"(\w+), #(0x[0-9a-f]+|\d+)", i.op_str)
                if mm:
                    movw[mm.group(1)] = (int(mm.group(2), 0), i.address)
            if m == "movt":
                mm = re.match(r"(\w+), #(0x[0-9a-f]+|\d+)", i.op_str)
                if mm and mm.group(1) in movw:
                    v = (int(mm.group(2), 0) << 16) | movw[mm.group(1)][0]
                    lit.setdefault(v, []).append(i.address)
            addr = i.address + i.size
        if not got:
            addr += 2
    return insn_at, calls, lit, adr, litp


def func_start(insn_at, a, limit=0x600):
    for _ in range(limit):
        a -= 2
        if a in SYMS:
            return a
        it = insn_at.get(a)
        if it and it[0].startswith("push") and "lr" in it[1]:
            return a
    return None


def dis(im, start, n):
    md = md_new()
    strs = im.strings()
    addr, count = start, 0
    print(f"# disasm {start:#x} ({n} insns)")
    while count < n:
        got = False
        for i in md.disasm(im.d[addr - im.base:], addr):
            got = True
            note = ""
            if i.mnemonic.startswith("ldr"):
                for op in i.operands:
                    if op.type == CS_OP_MEM and op.mem.base == ARM_REG_PC:
                        pool = ((i.address + 4) & ~3) + op.mem.disp
                        v = im.word(pool)
                        if v is not None:
                            note = f"  ; =[{pool:#x}]={v:#x}"
                            if v in NAMED:
                                note += f" {NAMED[v]}"
                            elif im.load and 0 <= v - im.load < len(im.d):
                                o = v - im.load
                                note += f" ->off {o:#x}" + (f' "{strs[o][:32]}"' if o in strs else "")
            if i.mnemonic.startswith("adr"):
                mm = re.search(r"#(0x[0-9a-f]+|\d+)", i.op_str)
                if mm:
                    t = ((i.address + 4) & ~3) + int(mm.group(1), 0)
                    note = f'  ; ={t:#x}' + (f' "{strs[t][:32]}"' if t in strs else "")
            if i.address in SYMS:
                print(f"\n{SYMS[i.address]}:")
            print(f"  {i.address:#07x}: {i.mnemonic:8} {i.op_str}{note}")
            addr = i.address + i.size
            count += 1
            if count >= n:
                break
        if not got:
            print(f"  {addr:#07x}: .data word={im.word(addr & ~3)}")
            addr += 2
            count += 1


def who(im, target, depth):
    insn_at, calls, _, _, _ = sweep(im)
    callers = {}
    for s, t, m in calls:
        callers.setdefault(t, []).append((s, m))
    seen = set()

    def walk(fn, lvl):
        if lvl > depth or fn in seen:
            return
        seen.add(fn)
        cl = callers.get(fn, [])
        print(f"{'  ' * lvl}fn {fn:#x}: {len(cl)} site(s)")
        par = {}
        for s, m in cl:
            par.setdefault(func_start(insn_at, s), []).append(f"{s:#x}{'(b)' if not m.startswith('bl') else ''}")
        for fs, sites in sorted(par.items(), key=lambda x: x[0] or 0):
            print(f"{'  ' * lvl}  <- {fs if fs is None else hex(fs)} [{', '.join(sites[:6])}]")
        for fs in par:
            if fs:
                walk(fs, lvl + 1)
    walk(target, 0)


def ptr(im, target):
    target += im.load
    for want in sorted({target | 1, target & ~1}):
        needle = want.to_bytes(4, "little")
        off = im.d.find(needle)
        while off != -1:
            a = im.base + off
            print(f"# {want:#x} at {a:#x}")
            for w in range(-6, 7):
                wa = (a & ~3) + w * 4
                v = im.word(wa)
                if v is not None:
                    print(f"    {wa:#07x}: {v:#010x}{'  <==' if v == want else ''}")
            off = im.d.find(needle, off + 1)


def tbb(im, addr):
    md = md_new()
    i = next(md.disasm(im.d[addr - im.base:addr - im.base + 4], addr))
    print(f"{addr:#x}: {i.mnemonic} {i.op_str}")
    half = i.mnemonic.startswith("tbh")
    t = addr + 4
    n = 0
    while n < 64:
        o = t - im.base + n * (2 if half else 1)
        v = int.from_bytes(im.d[o:o + (2 if half else 1)], "little")
        print(f"  idx {n:#04x}: +{v * 2:#x} -> {t + v * 2:#x}")
        n += 1


class Tee:
    def __init__(self, f):
        self.f, self.o = f, sys.stdout

    def write(self, t):
        self.o.write(t)
        self.f.write(t)

    def flush(self):
        self.o.flush()
        self.f.flush()


def main():
    a = sys.argv[1:]
    logdir = os.path.join(ROOT, "tmp", "logs")
    os.makedirs(logdir, exist_ok=True)
    sys.stdout = Tee(open(os.path.join(logdir, "mcu_trace.log"), "a"))
    path, base, load = DEFAULT_IMG, 0, DEFAULT_LOAD
    while a and a[0] in ("--img", "--base", "--load", "--syms"):
        if a[0] == "--img":
            path = a[1]
        elif a[0] == "--base":
            base = int(a[1], 0)
        elif a[0] == "--load":
            load = int(a[1], 0)
        else:
            with open(a[1]) as f:
                for ln in list(f)[1:]:
                    c = ln.rstrip("\n").split("\t")
                    if len(c) > 2 and c[0].startswith("0x") and c[1] == "func":
                        SYMS[int(c[0], 16)] = c[2]
        a = a[2:]
    if not a:
        print(__doc__)
        return
    im = Img(path, base, load)
    cmd = a[0]
    if cmd == "info":
        sp, rs = im.word(base), im.word(base + 4)
        ia, _, lit, _, _ = sweep(im)
        print(f"{path} {len(im.d)} B base {base:#x} load {load:#x} SP {sp:#x} reset {rs:#x} insns {len(ia)}")
        for k, nm in NAMED.items():
            if k in lit:
                print(f"  {nm} {k:#x}: {len(lit[k])} literal ref(s)")
    elif cmd == "dis":
        dis(im, int(a[1], 0), int(a[2], 0) if len(a) > 2 else 60)
    elif cmd == "who":
        who(im, int(a[1], 0), int(a[2], 0) if len(a) > 2 else 3)
    elif cmd == "ptr":
        ptr(im, int(a[1], 0))
    elif cmd == "lit":
        ia, _, lit, _, litp = sweep(im)
        v = int(a[1], 0)
        for s in lit.get(v, []):
            print(f"raw {v:#x} loaded at {s:#x} (fn {func_start(ia, s) or 0:#x})")
    elif cmd == "litp":
        ia, _, lit, _, litp = sweep(im)
        v = int(a[1], 0)
        for s in litp.get(v, []):
            print(f"ptr->{v:#x} loaded at {s:#x} (fn {func_start(ia, s) or 0:#x})")
    elif cmd == "str":
        ia, _, lit, adr, litp = sweep(im)
        for sa, t in sorted(im.strings().items()):
            if a[1] in t:
                xs = litp.get(sa, []) + adr.get(sa, [])
                print(f"{sa:#x} {t[:60]!r} xrefs {[hex(x) for x in xs]}")
    elif cmd == "tbb":
        tbb(im, int(a[1], 0))


if __name__ == "__main__":
    main()
