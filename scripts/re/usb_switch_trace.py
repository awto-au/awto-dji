#!/usr/bin/env python3
"""Trace the camera's A9<->DM368 USB-mode switch (issue #25): MCCTRL_SetUsbMode,
DjiMsgStUsbSwitchStatusSet, DjiUegDm368StreamControl in P3X V01.11.0020 sys (m0100).

Scope (CLAUDE.md): static interoperability analysis. Firmware is untrusted data, never
run. No key/cipher/signing values are read or printed.

Usage: python3 -I scripts/re/usb_switch_trace.py              (canned report, logged)
       python3 -I scripts/re/usb_switch_trace.py dis ADDR N
       python3 -I scripts/re/usb_switch_trace.py xref ADDR
Method/helpers (pool_xrefs/bl_callers/fn_start/dis) copied from fpga_write_path.py,
same sys image and base address - kept as a separate file since this trace is a
distinct function cluster, not a continuation of that one.
Output: tmp/logs/usb_switch_trace.log
"""
import os
import re
import struct
import subprocess
import sys

from capstone import Cs, CS_ARCH_ARM, CS_MODE_ARM


def repo_root():
    env = os.environ.get("AWTO_DJI_REPO")
    if env and os.path.isdir(env):
        return env
    try:
        top = subprocess.check_output(["git", "rev-parse", "--show-toplevel"],
                                      cwd=os.path.dirname(os.path.abspath(__file__)),
                                      stderr=subprocess.DEVNULL).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = repo_root()
SYS = os.path.join(ROOT, "tmp/air/amba_P3X0020/P3X_FW_V01.11.0020_m0100_part_sys.a9s")
LOG = os.path.join(ROOT, "tmp/logs/usb_switch_trace.log")
BASE = 0x0E600000
D = open(SYS, "rb").read()
END = BASE + len(D)
_log = []


def p(*a):
    s = " ".join(str(x) for x in a)
    _log.append(s)
    print(s)


def u32(addr):
    return struct.unpack_from("<I", D, addr - BASE)[0]


def cstr(addr, n=80):
    o = addr - BASE
    if not (0 <= o < len(D)):
        return None
    e = D.find(b"\0", o, o + n)
    s = D[o:e if e > 0 else o + n]
    if len(s) >= 3 and all(0x20 <= c < 0x7F for c in s):
        return s.decode()
    return None


MD = Cs(CS_ARCH_ARM, CS_MODE_ARM)


def dis(addr, n, annotate=True):
    o = addr - BASE
    out = []
    for i in MD.disasm(D[o:o + n * 4], addr):
        line = f"{i.address:#x}: {i.mnemonic} {i.op_str}"
        if annotate and i.mnemonic == "ldr" and "[pc, #" in i.op_str:
            m = re.search(r"\[pc, #(-?)(0x[0-9a-f]+|\d+)\]", i.op_str)
            if m:
                slot = i.address + 8 + int(m.group(2), 0) * (-1 if m.group(1) else 1)
                if BASE <= slot < END:
                    v = u32(slot)
                    s = cstr(v) if BASE <= v < END else None
                    line += f"    ; [{slot:#x}]={v:#x}" + (f' "{s}"' if s else "")
        out.append(line)
        if len(out) >= n:
            break
    return out


def fn_start(addr):
    a = addr - BASE
    while a > 0:
        w = struct.unpack_from("<I", D, a)[0]
        if (w & 0xFFFF0000) == 0xE92D0000 and (w & 0x4000):
            return BASE + a
        a -= 4
    return None


def pool_xrefs(target):
    res = []
    needle = struct.pack("<I", target)
    i = D.find(needle)
    while i != -1:
        if i % 4 == 0:
            slot = BASE + i
            for a in range(max(0, i - 4096), i, 4):
                w = struct.unpack_from("<I", D, a)[0]
                if (w & 0x0F7F0000) in (0x051F0000, 0x059F0000):
                    imm = w & 0xFFF
                    if BASE + a + 8 + (imm if (w >> 23) & 1 else -imm) == slot:
                        res.append(BASE + a)
        i = D.find(needle, i + 1)
    return res


def bl_callers(target):
    res = []
    for o in range(0, len(D) - 3, 4):
        w = struct.unpack_from("<I", D, o)[0]
        if (w & 0x0F000000) == 0x0B000000 and (w >> 28) != 0xF:
            off = w & 0xFFFFFF
            if off & 0x800000:
                off -= 0x1000000
            if BASE + o + 8 + off * 4 == target:
                res.append(BASE + o)
    return res


def find_str(text):
    return [BASE + m.start() for m in re.finditer(re.escape(text.encode()), D)]


def show_xrefs(target, label=""):
    px, bc = pool_xrefs(target), bl_callers(target)
    p(f"xref {label}{target:#x}: literal-pool users {[hex(x) for x in px]}; bl callers {[hex(x) for x in bc]}")


def show_fn(addr, n, title=""):
    fs = fn_start(addr)
    p(f"--- {title} {addr:#x} (fn start {fs or 0:#x}) ---")
    for line in dis(fs or addr, n):
        p("  " + line)


def gpio_like(addr):
    """Flag likely-MMIO literal values: Ambarella AHB/APB peripheral space is high,
    fixed addresses (this SoC's own code uses e.g. 0x70000000+ and 0xe0000000+ ranges
    elsewhere in this image - checked empirically here, not from a public memory map,
    since none is available locally for this exact SoC stepping)."""
    return addr is not None and (addr >> 28) in (0x6, 0x7, 0xe, 0xf) and not (BASE <= addr < END)


def trace_one(name, str_addr):
    p(f"\n## {name} (string {str_addr:#x} = {cstr(str_addr)!r})")
    show_xrefs(str_addr, "str ")
    for caller in pool_xrefs(str_addr):
        fs = fn_start(caller)
        if fs is None:
            continue
        p(f"-- function using this string, fn_start={fs:#x} --")
        lines = dis(fs, 40)
        for line in lines:
            p("  " + line)
        # Flag candidate MMIO literal loads within this function (ldr annotated with a
        # value outside the image, in a plausible peripheral range).
        for line in lines:
            m = re.search(r'; \[0x[0-9a-f]+\]=(0x[0-9a-f]+)', line)
            if m:
                v = int(m.group(1), 16)
                if gpio_like(v):
                    p(f"  ^ candidate MMIO/peripheral literal: {v:#x}")


def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    if len(sys.argv) > 1 and sys.argv[1] == "dis":
        addr, n = int(sys.argv[2], 0), int(sys.argv[3])
        for line in dis(addr, n):
            print(line)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "xref":
        show_xrefs(int(sys.argv[2], 0))
        return

    p(f"usb_switch_trace: {SYS}")
    trace_one("MCCTRL_SetUsbMode", find_str("MCCTRL_SetUsbMode")[0])
    trace_one("DjiMsgStUsbSwitchStatusSet", find_str("DjiMsgStUsbSwitchStatusSet")[0])
    trace_one("DjiUegDm368StreamControl", find_str("DjiUegDm368StreamControl")[0])

    with open(LOG, "w") as f:
        f.write("\n".join(_log) + "\n")
    print(f"\nlogged to {LOG}")


if __name__ == "__main__":
    main()
