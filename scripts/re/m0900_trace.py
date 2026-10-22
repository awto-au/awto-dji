#!/usr/bin/env python3
"""Static trace of m0900 (DJI P3 air MCU, STM32F103) to find what gates AD9363 bring-up.

Context: m0900 boots byte-exact in Renode but issues ZERO AD9363 SPI transactions
(awto-au/awto-dji#2, docs/phy-params.md). This locates, in the real firmware, the SPI
driver + AD9363 config path and the condition that guards it, so the emulation can supply
whatever the firmware waits on. Interop/structural RE only (see CLAUDE.md): no keys, no
geofence.

Headerless Thumb-2 blob loaded at the app base. No ELF/symbols in our image; function
names come from dji-firmware-tools' V01.11.0030 .map (one patch above our 0020), ported
here by content (string/const xrefs), not by trusting 0030 addresses.

Reproducible, deterministic (capstone linear sweep + literal-pool xref resolution).
Usage:  python3 scripts/re/m0900_trace.py [firmware.bin]
Log:    tmp/logs/m0900_trace.log
"""
import os
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
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        if top:
            return top
    except Exception:
        pass
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


ROOT = repo_root()
BASE = 0x08008000  # app base; bootloader occupies 0x08000000..0x08008000

# Symbols from dji-firmware-tools P3X_FW_V01.11.0030_m0900.map. Our image is 0020, one
# patch earlier, but the .rodata strings land at identical addresses (Phantom@0x0800DCA8,
# Fpga*@0x0800DCD4..), so this region is address-aligned; names annotated below are from
# 0030 and flagged for spot-verification, not trusted blindly.
SYMS = {
    0x0800B500: "SPI_UsrWaitTransferComplete",
    0x0800B5E8: "spi_fpga_or_tcx_transfer_mark",
    0x0800B5F6: "spi_fpga_or_tcx_transfer_clear",
    0x0800C142: "get_board_version",
    0x0800C2B8: "nullsub_1",
    0x0800CE76: "spi_fpga_raw_write",
    0x0800CE9A: "spi_fpga_raw_read",
    0x0800CEBE: "ad936x_reg_sync_write",
    0x0800CF00: "ad936x_reg_sync_read",
    0x0800D7C6: "init_fpga_config",
    0x0800F0BC: "tcx_config_update1",
    0x0800FDC2: "tcx_config_power_zone",
    0x08011320: "send_func",
    0x080118D0: "packet_send",
    0x08011D66: "packet_make_response",
    0x08012122: "cmd_exec_set09_cmd06",
    0x080121B4: "cmd_exec_set09_cmd12",
}
# RAM/MMIO constants worth flagging when they appear in literal pools.
SPI1_BASE = 0x40013000
SPI2_BASE = 0x40003800
NAMED_CONSTS = {
    SPI1_BASE: "SPI1",
    SPI2_BASE: "SPI2",
    0x40013004: "SPI1_DR", SPI1_BASE + 0x0C: "SPI1_DR",
    SPI2_BASE + 0x0C: "SPI2_DR",
    0x40010800: "GPIOA", 0x40010C00: "GPIOB", 0x40011000: "GPIOC",
    0x40011400: "GPIOD", 0x40011800: "GPIOE",
    0x40021000: "RCC", 0x40022000: "FLASH_ACR",
    0x40003000: "IWDG/SPI2region", 0x40006600: "bxCAN?",
    0xE000E010: "SysTick",
}


def load():
    arg = sys.argv[1] if len(sys.argv) > 1 else None
    path = arg if (arg and arg not in ("dis", "who", "ptr")) else os.path.join(
        ROOT, "firmware", "P3X_FW_V01.11.0020_m0900.bin")
    with open(path, "rb") as f:
        return path, f.read()


def find_strings(img, minlen=4):
    """addr -> text for printable-ASCII runs."""
    out = {}
    i, n = 0, len(img)
    while i < n:
        j = i
        while j < n and 0x20 <= img[j] < 0x7F:
            j += 1
        if j - i >= minlen:
            out[BASE + i] = img[i:j].decode("ascii", "replace")
        i = j + 1
    return out


def word(img, addr):
    o = addr - BASE
    if 0 <= o <= len(img) - 4:
        return int.from_bytes(img[o:o + 4], "little")
    return None


def disasm_dump(img, strings, start, n):
    """Annotated linear disasm of n instructions from `start` (resyncs over pools)."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    print(f"# disasm {start:#010x} .. ({n} insns)"
          + (f"  == {SYMS[start]}" if start in SYMS else ""))
    count = 0
    addr = start
    while count < n:
        got = False
        for insn in md.disasm(img[addr - BASE:], addr):
            got = True
            note = ""
            m, ops = insn.mnemonic, insn.op_str
            if m in ("bl", "blx"):
                for op in insn.operands:
                    if op.type == CS_OP_IMM and op.imm in SYMS:
                        note = "  -> " + SYMS[op.imm]
            if m.startswith("ldr"):
                for op in insn.operands:
                    if op.type == CS_OP_MEM and op.mem.base == ARM_REG_PC:
                        pool = ((insn.address + 4) & ~3) + op.mem.disp
                        val = word(img, pool)
                        if val is not None:
                            note = f"  ; =[{pool:#x}]={val:#x}"
                            if val in strings:
                                note += f'  "{strings[val][:32]}"'
                            elif val in NAMED_CONSTS:
                                note += f"  {NAMED_CONSTS[val]}"
                            elif val in SYMS:
                                note += f"  {SYMS[val]}"
            lbl = f"{insn.address:#010x}:"
            if insn.address in SYMS:
                lbl = f"\n{SYMS[insn.address]}:\n" + lbl
            print(f"  {lbl} {m:8} {ops}{note}")
            addr = insn.address + insn.size
            count += 1
            if count >= n:
                break
        if not got:
            w = word(img, addr & ~3)
            print(f"  {addr:#010x}: .data  (pool/non-code; word={w:#x})" if w is not None
                  else f"  {addr:#010x}: .data")
            addr += 2
            count += 1


def sweep(img, strings):
    """Resyncing linear Thumb sweep. Returns (insn_at, calls, callers, str_xrefs,
    const_xrefs). Code starts at 0x200 (reset handler); literal pools and the vector
    table are not Thumb, so capstone stops on them — skip 2 bytes and resync."""
    md = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    md.detail = True
    calls, str_xrefs, const_xrefs, insn_at = [], {}, {}, {}
    end = BASE + len(img)
    addr = BASE + 0x200
    while addr < end:
        got = False
        for insn in md.disasm(img[addr - BASE:], addr):
            got = True
            insn_at[insn.address] = (insn.id, insn.mnemonic, insn.op_str, insn.size)
            m = insn.mnemonic
            if m in ("bl", "blx"):
                for op in insn.operands:
                    if op.type == CS_OP_IMM:
                        calls.append((insn.address, op.imm))
            if m.startswith("ldr"):
                for op in insn.operands:
                    if op.type == CS_OP_MEM and op.mem.base == ARM_REG_PC:
                        pool = ((insn.address + 4) & ~3) + op.mem.disp
                        val = word(img, pool)
                        if val is None:
                            continue
                        if val in strings:
                            str_xrefs.setdefault(val, []).append(insn.address)
                        elif val in NAMED_CONSTS:
                            const_xrefs.setdefault(val, []).append(insn.address)
            addr = insn.address + insn.size
        if not got:
            addr += 2
    callers = {}
    for site, tgt in calls:
        callers.setdefault(tgt, []).append(site)
    return insn_at, calls, callers, str_xrefs, const_xrefs


def make_func_start(insn_at):
    def func_start(addr, limit=0x400):
        a = addr
        for _ in range(limit):
            a -= 2
            it = insn_at.get(a)
            if it and it[1] == "push" and "lr" in it[2]:
                return a
        return None
    return func_start


def who_chain(img, strings, target, depth=4):
    """Print the caller chain above `target` up to `depth` levels (toward main)."""
    insn_at, _, callers, _, _ = sweep(img, strings)
    func_start = make_func_start(insn_at)

    def name(a):
        return f" {SYMS[a]}" if a in SYMS else ""

    seen = set()
    def walk(fn, level):
        if level > depth or fn in seen:
            return
        seen.add(fn)
        cl = callers.get(fn, [])
        pad = "  " * level
        print(f"{pad}fn {fn:#010x}{name(fn)}: {len(cl)} caller site(s)")
        parents = {}
        for c in cl:
            fs = func_start(c)
            parents.setdefault(fs, []).append(c)
        for fs, sites in sorted((p for p in parents.items()), key=lambda x: (x[0] or 0)):
            s = ", ".join(f"{x:#x}" for x in sites[:6])
            print(f"{pad}  <- {fs if fs is None else f'{fs:#010x}'}{name(fs) if fs else ''}  [{s}]")
        for fs in parents:
            if fs:
                walk(fs, level + 1)

    print(f"# caller chain above {target:#010x}{name(target)} (depth {depth})")
    walk(target, 0)


def main():
    path, img = load()
    strings = find_strings(img)
    if len(sys.argv) > 1 and sys.argv[1] == "dis":
        start = int(sys.argv[2], 0)
        n = int(sys.argv[3], 0) if len(sys.argv) > 3 else 60
        disasm_dump(img, strings, start, n)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "who":
        target = int(sys.argv[2], 0)
        depth = int(sys.argv[3], 0) if len(sys.argv) > 3 else 4
        who_chain(img, strings, target, depth)
        return
    if len(sys.argv) > 1 and sys.argv[1] == "ptr":
        target = int(sys.argv[2], 0)
        # Find every 4-byte LE occurrence of the pointer (thumb bit set or clear) and
        # print a window of surrounding words — a dispatch table shows as records of
        # [cmdset, cmdid, flags, handler_ptr] around the hit.
        for want in (target | 1, target & ~1):
            needle = want.to_bytes(4, "little")
            off = img.find(needle)
            while off != -1:
                a = BASE + off
                print(f"\n# pointer {want:#010x} found at {a:#010x} (off {off:#x})")
                for w in range(-6, 7):
                    wa = (a & ~3) + w * 4
                    v = word(img, wa)
                    if v is None:
                        continue
                    mark = "  <== handler ptr" if v in (target | 1, target & ~1) else ""
                    sv = f'  "{strings[v][:24]}"' if v in strings else ""
                    print(f"    {wa:#010x}: {v:#010x}{mark}{sv}")
                off = img.find(needle, off + 1)
        return

    sp = int.from_bytes(img[0:4], "little")
    reset = int.from_bytes(img[4:8], "little")

    insn_at, calls, callers, str_xrefs, const_xrefs = sweep(img, strings)
    func_start = make_func_start(insn_at)

    def sym_for(addr):
        """Short label for an address region, anchored by nearby string/const xrefs."""
        fs = func_start(addr)
        return f"{addr:#010x}" + (f" (fn {fs:#010x})" if fs else "")

    log = []
    def p(*a):
        line = " ".join(str(x) for x in a)
        log.append(line)
        print(line)

    p(f"# m0900 trace  base={BASE:#x}  file={os.path.relpath(path, ROOT)}")
    p(f"# reset vector: SP={sp:#010x}  reset={reset:#010x}  (expect 0x20004cb8 / 0x08008201)")
    p(f"# image {len(img)} bytes, {len(insn_at)} insns swept, {len(strings)} strings\n")

    # --- 1. which SPI is the AD9363 bus: who references the SPI base addrs -----------
    p("## SPI base-address references (locates the SPI driver + the AD9363 bus)")
    for base_const in (SPI1_BASE, SPI2_BASE):
        sites = const_xrefs.get(base_const, [])
        p(f"  {NAMED_CONSTS[base_const]} {base_const:#010x}: {len(sites)} ref(s)")
        for s in sites:
            p(f"      at {sym_for(s)}")
    p("")

    # --- 2. anchor strings relevant to the radio bring-up ----------------------------
    anchors = ("9363", "Ar8003", "Fpga", "FPGA", "fpga", "Phantom", "phantom",
               "Ver ", "Set Alter", "Alter", "Error", "error", "Id ", "boot", "Boot")
    p("## Radio/boot-relevant strings and their code xrefs")
    shown = set()
    for saddr, text in sorted(strings.items()):
        if any(k in text for k in anchors) and saddr not in shown:
            shown.add(saddr)
            xr = str_xrefs.get(saddr, [])
            if not xr:
                continue
            p(f'  {saddr:#010x} "{text[:48]}"  <- {len(xr)} xref(s)')
            for s in xr:
                p(f"      at {sym_for(s)}")
    p("")

    # --- 3. call graph around the functions that touch SPI ---------------------------
    p("## Callers of the functions that reference the SPI base (the AD9363 driver path)")
    spi_funcs = set()
    for base_const in (SPI1_BASE, SPI2_BASE):
        for s in const_xrefs.get(base_const, []):
            fs = func_start(s)
            if fs:
                spi_funcs.add(fs)
    for fn in sorted(spi_funcs):
        p(f"  fn {fn:#010x}:")
        for c in callers.get(fn, []):
            p(f"      called from {sym_for(c)}")
        if fn not in callers:
            p("      (no direct BL caller found — may be tail-called or via table)")
    p("")

    # --- 4. callers of each named radio/boot function (trace toward the gate) --------
    p("## Callers of named radio/boot functions (0030 map, addresses verified on 0020)")
    for addr in sorted(SYMS):
        name = SYMS[addr]
        cl = callers.get(addr, [])
        if not cl:
            continue
        p(f"  {name} {addr:#010x}: {len(cl)} caller(s)")
        for c in cl:
            fs = func_start(c)
            fsname = SYMS.get(fs, "")
            p(f"      from {c:#010x}  (fn {fs:#010x}{' ' + fsname if fsname else ''})")
    p("")

    os.makedirs(os.path.join(ROOT, "tmp", "logs"), exist_ok=True)
    with open(os.path.join(ROOT, "tmp", "logs", "m0900_trace.log"), "w") as f:
        f.write("\n".join(log) + "\n")


if __name__ == "__main__":
    main()
